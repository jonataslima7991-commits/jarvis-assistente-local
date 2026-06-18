# J.A.R.V.I.S. — Assistente Pessoal por Voz

Assistente pessoal por voz em Python, com interface gráfica estilo HUD futurista, integração com Google Calendar e Gmail, busca em tempo real, tool-use via LLM e personalidade própria (sarcástica, no estilo do JARVIS do Tony Stark).

Desenvolvido por **Jonatas Oliveira de Lima**.

![status](https://img.shields.io/badge/status-em%20desenvolvimento-yellow)
![python](https://img.shields.io/badge/python-3.14-blue)
![platform](https://img.shields.io/badge/platform-Windows-lightgrey)

---

## ✨ Funcionalidades

### Voz e conversa
- **Wake word** "hey jarvis" via [openWakeWord](https://github.com/dscripka/openWakeWord) — detecção contínua de baixíssimo custo de CPU, sem precisar de Whisper rodando o tempo todo
- **STT** com [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (modelo configurável: tiny/base/small/medium)
- **TTS** com [edge-tts](https://github.com/rany2/edge-tts) (voz pt-BR), com efeito de voz robótica e cache local de áudio para frases repetidas
- **LLM** via [Groq](https://groq.com) (`llama-3.3-70b-versatile`), com fallback para Ollama local
- Retentativa automática quando o reconhecimento de voz falha, sem precisar repetir a wake word
- Histórico de conversa persistido entre sessões

### Inteligência e personalidade
- **Tool-use**: um modelo rápido decide qual ferramenta chamar (abrir app, agendar evento, enviar e-mail, etc.) quando o comando não bate com nenhum padrão fixo
- **Busca web em tempo real** via [Tavily](https://tavily.com) para notícias, preços e eventos recentes
- Contexto temporal sempre presente (data/hora atual) para respostas precisas
- Personalidade sarcástica e proativa — comenta progresso, sugere pausas, fecha ciclos de conversas anteriores
- Memória de fatos/preferências do usuário, persistente entre sessões

### Produtividade
- **Google Calendar**: criar, listar, cancelar e reagendar eventos por voz, com detecção de conflito de horário e avisos proativos (15 min e 1 dia antes)
- **Gmail**: verificar não lidos, ler e-mails (resumidos naturalmente, sem ler URLs/tokens em voz alta), enviar e-mails com confirmação verbal antes de disparar
- **Agenda de contatos** local — resolve nomes falados para endereços de e-mail
- Controle de volume, janelas, abertura/fechamento de apps e sites
- Timers, lembretes por horário, anotações rápidas
- Leitura de arquivos de texto, código e PDF
- Captura de tela com OCR, leitura de clipboard, contexto do VS Code
- Relatório de projetos ativos (scan de diretórios com status do git)

### Interface (HUD)
- Visualização 3D (Three.js) de uma esfera de partículas/circuitos reativa ao estado (ouvindo, processando, falando)
- Painéis de status: relógio, clima, sistema (CPU/RAM/disco/temperatura), próxima agenda, e-mails não lidos, uso estimado da cota do Groq
- Feedback visual claro de estado (ouvindo / processando / falando / erro) com cores e animações distintas
- Detecção de atualização no código-fonte com oferta de reinício automático por voz

---

## 🏗️ Arquitetura

```
jarvis_main.py        → ponto de entrada (modo GUI por padrão, ou CLI texto/voz)
├── gui/               → janela PySide6 + WebEngine, lógica de diálogo e dispatch de comandos
│   └── interface.html → HUD (Three.js + GSAP), renderizado dentro da QWebEngineView
├── core/               → JarvisCore: chat com LLM (Groq/Ollama), tool-use, histórico
├── voice/              → STTEngine, TTSEngine, WakeWordDetector
├── tools/               → integrações: sistema, apps, janelas, calendário, Gmail, contatos, busca web
├── memory/             → memória persistente de fatos do usuário
├── automation/          → relatório matinal (clima, cotações)
└── config/              → configurações via .env
```

**Fluxo de comando:** wake word → captura de áudio → Whisper → regex de padrões conhecidos (abrir app, volume, timer...) → se nada bater, tool-use via LLM rápido → se nenhuma ferramenta se aplica, conversa livre com o LLM principal.

---

## 🚀 Instalação

### Pré-requisitos
- Python 3.14, Windows 10+
- Conta gratuita no [Groq](https://console.groq.com) para a chave de API do LLM

### Passos

```bash
git clone https://github.com/jonataslima7991-commits/jarvis-assistente-local.git
cd jarvis-assistente-local
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Copie `.env.example` para `.env` e configure:

```env
GROQ_API_KEY=sua_chave_aqui
GROQ_MODEL=llama-3.3-70b-versatile
TAVILY_API_KEY=sua_chave_aqui          # opcional, busca em tempo real
JARVIS_CITY=Sua+Cidade
WHISPER_MODEL=small                     # tiny | base | small | medium
```

### Integrações opcionais

**Google Calendar + Gmail**: crie um projeto no [Google Cloud Console](https://console.cloud.google.com), ative as APIs Calendar e Gmail, crie credenciais OAuth (tipo "App para computador") e salve o JSON baixado como `credentials.json` na raiz do projeto. Na primeira vez que usar um comando de calendário/e-mail, vai abrir o navegador pedindo autorização.

**Monitoramento de temperatura da CPU**: instale o [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) e deixe-o em execução — o Windows não expõe sensores de temperatura sem isso.

### Executar

```bash
JARVIS.bat
```

ou diretamente:

```bash
.venv\Scripts\python jarvis_main.py
```

---

## 🗣️ Comandos de exemplo

```
"hey jarvis, abre o chrome"
"hey jarvis, agenda uma reunião com o cliente segunda às 15h"
"hey jarvis, tenho e-mail novo?"
"hey jarvis, manda um e-mail pro professor avisando que vou faltar"
"hey jarvis, últimas notícias sobre inteligência artificial"
"hey jarvis, timer de 10 minutos"
"hey jarvis, status do sistema"
"hey jarvis, lembra que prefiro Python"
"hey jarvis, reinicia o jarvis"
```

Diga **"o que você sabe fazer"** para a lista completa de comandos.

---

## 🛠️ Stack técnica

| Categoria | Tecnologia |
|---|---|
| LLM | Groq API (Llama 3.3 70B) / Ollama |
| STT | faster-whisper |
| TTS | edge-tts |
| Wake word | openWakeWord |
| Interface | PySide6 + QWebEngineView |
| Visualização 3D | Three.js + GSAP |
| Calendário/E-mail | Google Calendar API, Gmail API |
| Busca web | Tavily API |
| Métricas de sistema | psutil, pycaw, pygetwindow |

---

## ⚠️ Segurança

Nunca commite `.env` ou `credentials.json` — ambos contêm segredos e já estão no `.gitignore`. Dados pessoais (histórico, memória, contatos, tokens OAuth) são salvos na pasta do usuário do Windows, fora do repositório.
