import csv
import os
import re
import time
from pathlib import Path
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


PASTA_PROJETO = Path(__file__).resolve().parent.parent


def carregar_env(caminho=PASTA_PROJETO / ".env"):
	"""Lê pares CHAVE=VALOR do arquivo .env para as variáveis de ambiente."""
	if not caminho.exists():
		return
	for linha in caminho.read_text(encoding="utf-8").splitlines():
		linha = linha.strip()
		if not linha or linha.startswith("#") or "=" not in linha:
			continue
		chave, valor = linha.split("=", 1)
		os.environ.setdefault(chave.strip(), valor.strip())


def aguardar_rede(page, timeout=10000):
	"""Espera a rede ficar ociosa, sem travar se o site continuar fazendo requisições."""
	try:
		page.wait_for_load_state("networkidle", timeout=timeout)
	except PlaywrightTimeoutError:
		pass


def abrir_site(page, url, tentativas=5):
	"""Abre o site tentando de novo se a conexão falhar (o Gear às vezes demora a responder)."""
	for tentativa in range(1, tentativas + 1):
		try:
			page.goto(url, wait_until="domcontentloaded", timeout=120000)
			return
		except Exception as erro:
			if tentativa == tentativas:
				raise
			print(f"Falha ao abrir o site (tentativa {tentativa}): {str(erro).splitlines()[0]}")
			page.wait_for_timeout(10000)


def fazer_login(page, usuario, senha):
	campo_usuario = page.locator("input[name=username]")
	campo_usuario.wait_for(state="visible", timeout=120000)
	campo_usuario.fill(usuario)
	page.fill("input[name=password]", senha)
	page.press("input[name=password]", "Enter")
	campo_usuario.wait_for(state="detached", timeout=60000)
	aguardar_rede(page)


def abrir_dispositivos(page):
	"""Abre o menu suspenso 'Unidades' e clica em 'Dispositivos'."""
	page.get_by_role("button", name="Unidades", exact=True).click()
	link = page.locator("a[href='/gear/unidades/dispositivos']")
	link.wait_for(state="visible", timeout=15000)
	link.click()
	page.wait_for_url("**/gear/unidades/dispositivos**", timeout=30000)
	page.get_by_placeholder(PLACEHOLDER_CONDOMINIO).wait_for(state="visible", timeout=30000)


PLACEHOLDER_CONDOMINIO = "Selecione um condomínio"
FORMATOS_EXPORTACAO = ["CSV"]
PASTA_EXPORTACOES = PASTA_PROJETO / "Exportacoes"


def nome_de_pasta(nome):
	"""Remove caracteres que o Windows não aceita em nomes de pasta."""
	limpo = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nome)
	limpo = re.sub(r"\s+", " ", limpo).strip().rstrip(". ")
	return limpo or "sem_nome"


def abrir_lista_condominios(page):
	page.get_by_placeholder(PLACEHOLDER_CONDOMINIO).click()
	opcoes = page.get_by_role("option")
	opcoes.first.wait_for(state="visible", timeout=30000)
	return opcoes


def listar_condominios(page):
	opcoes = abrir_lista_condominios(page)
	nomes = [t.strip() for t in opcoes.all_inner_texts()]
	page.keyboard.press("Escape")
	return nomes


ESTADO_JS = r"""() => {
	const visivel = e => e && e.offsetParent !== null;
	const carregando = [...document.querySelectorAll(
		'.iconify--line-md, .MuiCircularProgress-indeterminate, .MuiLinearProgress-root, .MuiSkeleton-root'
	)].some(visivel);
	const pag = document.querySelector('.MuiTablePagination-displayedRows');
	const texto = pag ? pag.innerText.trim() : null;
	const m = texto && texto.match(/de\s+(?:mais de\s+)?(\d+)/);
	const linha = document.querySelector('tbody tr');
	const th = document.querySelectorAll('thead th');
	return {
		carregando,
		paginacao: texto,
		total: m ? parseInt(m[1], 10) : null,
		primeira_linha: linha ? linha.innerText.trim() : null,
		tem_menu: th.length > 0 && !!th[th.length - 1].querySelector('button'),
	};
}"""

TEMPO_MAX_CARREGAMENTO = 600  # segundos que espera um condomínio carregar
SEGUNDOS_ESTAVEL = 3  # a tela precisa ficar parada esse tempo para considerar carregada


def ler_estado(page):
	return page.evaluate(ESTADO_JS)


def assinatura(estado):
	return (estado["paginacao"], estado["primeira_linha"])


def aguardar_tabela(page, estado_anterior):
	"""Espera a tabela do novo condomínio carregar por completo e ficar estável."""
	inicio = time.monotonic()
	mudou = estado_anterior is None or assinatura(estado_anterior) == (None, None)
	ultimo, estavel_desde = None, None
	while time.monotonic() - inicio < TEMPO_MAX_CARREGAMENTO:
		estado = ler_estado(page)
		if not mudou and assinatura(estado) != assinatura(estado_anterior):
			mudou = True
		# depois de 60s sem mudar, aceita que os dados podem ser iguais aos do anterior
		pode_aceitar = mudou or time.monotonic() - inicio > 60
		if estado["carregando"] or not pode_aceitar:
			ultimo, estavel_desde = None, None
		elif ultimo is None or assinatura(estado) != assinatura(ultimo):
			ultimo, estavel_desde = estado, time.monotonic()
		elif time.monotonic() - estavel_desde >= SEGUNDOS_ESTAVEL:
			return estado
		page.wait_for_timeout(500)
	raise RuntimeError(f"Tabela não terminou de carregar em {TEMPO_MAX_CARREGAMENTO}s")


def selecionar_condominio(page, indice, nome):
	estado_anterior = ler_estado(page)
	opcoes = abrir_lista_condominios(page)
	opcao = opcoes.nth(indice)
	if opcao.inner_text().strip() != nome:
		raise RuntimeError(f"Lista mudou: esperado '{nome}', encontrado '{opcao.inner_text()}'")
	opcao.click()
	return aguardar_tabela(page, estado_anterior)


def contar_registros_csv(caminho):
	with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
		linhas = [l for l in csv.reader(arquivo) if any(c.strip() for c in l)]
	return max(len(linhas) - 1, 0)  # desconta o cabeçalho


def registros_no_dialogo(dialogo):
	texto = dialogo.get_by_text(re.compile(r"registros? para exportar")).first.inner_text()
	m = re.search(r"(\d[\d.]*)", texto)
	return int(m.group(1).replace(".", "")) if m else None


def exportar_condominio(page, pasta, total_esperado, tentativas=3):
	"""Clica nos 3 pontinhos ao lado de 'Data de cadastro' > Exportar e baixa cada formato."""
	salvos = []
	for formato in FORMATOS_EXPORTACAO:
		for tentativa in range(1, tentativas + 1):
			page.locator("thead th").last.locator("button").click()
			page.get_by_role("menuitem", name="Exportar").click()
			dialogo = page.get_by_role("dialog")
			dialogo.wait_for(state="visible", timeout=30000)

			no_dialogo = registros_no_dialogo(dialogo)
			if total_esperado and no_dialogo != total_esperado:
				fechar_dialogo(page)
				print(f"    diálogo mostra {no_dialogo} registros, esperado {total_esperado}; aguardando...")
				page.wait_for_timeout(5000)
				continue

			with page.expect_download(timeout=TEMPO_MAX_CARREGAMENTO * 1000) as info:
				dialogo.get_by_role("button", name=formato, exact=True).click()
			download = info.value
			destino = pasta / download.suggested_filename
			download.save_as(destino)
			fechar_dialogo(page)

			if formato == "CSV" and total_esperado:
				no_arquivo = contar_registros_csv(destino)
				if no_arquivo != total_esperado:
					print(f"    CSV veio com {no_arquivo} de {total_esperado} registros (tentativa {tentativa})")
					page.wait_for_timeout(5000)
					continue
			salvos.append(destino.name)
			break
		else:
			raise RuntimeError(f"{formato} incompleto após {tentativas} tentativas")
	return salvos


def fechar_dialogo(page):
	dialogo = page.get_by_role("dialog")
	if dialogo.count() and dialogo.first.is_visible():
		page.keyboard.press("Escape")
		dialogo.first.wait_for(state="hidden", timeout=10000)


def exportar_todos(page):
	PASTA_EXPORTACOES.mkdir(exist_ok=True)
	condominios = listar_condominios(page)
	total = len(condominios)
	print(f"{total} condomínios encontrados. Salvando em: {PASTA_EXPORTACOES}")

	sem_dispositivos, falhas = [], []
	for indice, nome in enumerate(condominios):
		prefixo = f"[{indice + 1}/{total}] {nome}"
		try:
			estado = selecionar_condominio(page, indice, nome)
			if not estado["tem_menu"] or not estado["total"]:
				sem_dispositivos.append(nome)
				print(f"{prefixo}: sem dispositivos, pulado")
				continue
			pasta = PASTA_EXPORTACOES / nome_de_pasta(nome)
			pasta.mkdir(exist_ok=True)
			arquivos = exportar_condominio(page, pasta, estado["total"])
			print(f"{prefixo}: {estado['total']} registros -> {', '.join(arquivos)}")
		except Exception as erro:
			falhas.append((nome, erro))
			print(f"{prefixo}: ERRO - {erro}")
			fechar_dialogo_silencioso(page)

	print("\nResumo:")
	print(f"  Exportados: {total - len(sem_dispositivos) - len(falhas)}")
	print(f"  Sem dispositivos: {len(sem_dispositivos)}")
	print(f"  Falhas: {len(falhas)}")
	for nome, erro in falhas:
		print(f"    - {nome}: {erro}")


def fechar_dialogo_silencioso(page):
	try:
		page.keyboard.press("Escape")
		page.keyboard.press("Escape")
	except Exception:
		pass


def main():
	carregar_env()
	usuario = os.environ.get("GEAR_USUARIO")
	senha = os.environ.get("GEAR_SENHA")
	gear_url = os.environ.get("GEAR_URL")
	if not usuario or not senha or not gear_url:
		raise SystemExit("Defina GEAR_USUARIO, GEAR_SENHA e GEAR_URL no arquivo .env")

	with sync_playwright() as playwright:
		browser = playwright.chromium.launch(
			channel="chrome", headless=False, args=["--start-maximized"]
		)
		try:
			page = browser.new_page(no_viewport=True)
			abrir_site(page, gear_url)
			fazer_login(page, usuario, senha)
			print(f"Login enviado. URL atual: {page.url}")
			abrir_dispositivos(page)
			print(f"Tela de dispositivos aberta: {page.url}")
			exportar_todos(page)
			input("Concluído. Pressione Enter para encerrar...")
		finally:
			browser.close()


if __name__ == "__main__":
	main()
