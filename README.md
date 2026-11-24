# 🤖 Gear Devices Report Automation

![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-2EAD33?logo=playwright&logoColor=white)
![RPA](https://img.shields.io/badge/RPA-automação_web-6E40C9)
![CSV](https://img.shields.io/badge/CSV-relatórios-217346)

Robô em Python com Playwright que entra no painel de controle de acesso GEAR e exporta, um por um, o relatório de dispositivos de cada condomínio cadastrado.

## 📌 Sobre o projeto

No painel, o relatório de dispositivos sai um condomínio por vez: escolher o condomínio na lista, esperar a tabela carregar, abrir o menu da coluna, exportar e salvar. Com mais de cem condomínios, isso toma muito tempo e é fácil pular um ou salvar o arquivo do condomínio errado.

O robô percorre a lista inteira sozinho e salva cada CSV numa pasta com o nome do condomínio.

## 🚀 Funcionalidades

- Login automático, com novas tentativas quando o site demora a responder;
- Leitura da lista completa de condomínios do painel;
- Exportação do relatório de dispositivos de cada condomínio em CSV;
- Uma pasta por condomínio em `Exportacoes/`, com nome ajustado para o Windows;
- Condomínios sem dispositivos são pulados e listados no resumo final.

## 🧠 Como garante que o arquivo está certo

- **Espera a tabela do novo condomínio:** depois de trocar o condomínio, só segue quando os indicadores de carregamento somem e a tabela fica parada por 3 segundos. Assim não exporta os dados do condomínio anterior.
- **Confere o total:** o número de registros da paginação precisa bater com o da janela de exportação e com o número de linhas do CSV baixado. Se não bater, tenta de novo até 3 vezes.
- **Confere a lista:** se a lista de condomínios mudar durante a execução, o robô para naquele item em vez de exportar o condomínio errado.
- **Uma falha não para tudo:** o erro de um condomínio é registrado e o robô segue para o próximo. No fim, mostra o resumo de exportados, pulados e falhas.

## 🛠️ Tecnologias utilizadas

- Python
- Playwright
- csv, pathlib, re

## ⚙️ Como usar

1. Instale as dependências:
   ```
   pip install -r requirements.txt
   playwright install chrome
   ```
2. Copie `.env.example` para `.env` e preencha usuário, senha e endereço do painel.
3. Rode:
   ```
   python Src/gear_dispositivos.py
   ```

O Chrome abre visível para você acompanhar. Os arquivos ficam em `Exportacoes/<condomínio>/`.

## 📂 Estrutura do projeto

gear-devices-report-automation

- Src
  - gear_dispositivos.py
- README.md
- requirements.txt
- .gitignore
- .env.example
