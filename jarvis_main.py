from __future__ import annotations

import re
import sys

from automation import morning_report
from config import settings
from core import JarvisCore
from gui import run as run_gui
from tools import get_datetime, get_weather, open_app
from voice import STTEngine, TTSEngine

_BANNER = """\
╔══════════════════════════════════════════════════════════╗
║        J.A.R.V.I.S. — Assistente Pessoal  v1.0          ║
║        Just A Rather Very Intelligent System             ║
╚══════════════════════════════════════════════════════════╝"""

_WAKE_WORDS  = ["jarvis", "javis", "jarvi", "j.a.r.v.i.s", "tá aí", "ta ai", "ei jarvis"]
_STOP_WORDS  = ["sair", "encerrar", "desligar", "tchau", "até logo", "ate logo"]
_REPORT_WORDS = ["relatório", "relatorio", "briefing", "resumo do dia"]
_OPEN_RE      = re.compile(r'\babr(?:ir|e|a)\s+(?:(?:o|a|os|as)\s+)?(.+)', re.IGNORECASE)


def _enrich(message: str) -> str:
    """Injeta contexto de ferramentas no prompt quando relevante."""
    low = message.lower()
    if any(w in low for w in ("hora", "horas", "horário", "data", "dia", "semana", "mês", "mes")):
        return f"[{get_datetime()}]\n{message}"
    if any(w in low for w in ("clima", "tempo", "temperatura", "chuva", "sol", "calor", "frio")):
        return f"[{get_weather()}]\n{message}"
    return message


def _handle(text: str, brain: JarvisCore, tts: TTSEngine, speak: bool) -> bool:
    """Processa um comando. Retorna True para encerrar a sessão."""
    if any(w in text.lower() for w in _STOP_WORDS):
        msg = "Encerrando sessão. Até logo, Sr. Lima."
        print(f"JARVIS: {msg}")
        if speak:
            tts.speak(msg)
        return True

    m = _OPEN_RE.search(text)
    if m:
        result = open_app(m.group(1).strip(" .!?,"))
        print(f"JARVIS: {result}")
        if speak:
            tts.speak(result)
        return False

    if any(w in text.lower() for w in _REPORT_WORDS):
        print("JARVIS: [Coletando dados...]\n")
        data = morning_report()
        prompt = (
            f"Com base nos dados abaixo, apresente um briefing matinal conciso e formal para o Sr. Lima:\n\n{data}"
        )
        print("JARVIS: ", end="", flush=True)
        _stream_speak(brain, tts, prompt, speak)
        return False

    enriched = _enrich(text)
    print("JARVIS: ", end="", flush=True)
    _stream_speak(brain, tts, enriched, speak)
    return False


def _stream_speak(brain: JarvisCore, tts: TTSEngine, prompt: str, speak: bool) -> None:
    """Gera texto streamando e fala frase a frase (sem esperar resposta completa)."""
    buffer   = ""
    last_evt = None

    def _enqueue(text: str) -> None:
        nonlocal last_evt
        text = text.strip()
        if not text:
            return
        print(text, end=" ", flush=True)
        if speak:
            last_evt = tts.speak_async(text)

    for chunk in brain.stream_chat(prompt):
        buffer += chunk
        while True:
            best = -1
            for delim in ('. ', '? ', '! ', '\n'):
                idx = buffer.find(delim, 25)
                if idx != -1 and (best == -1 or idx < best):
                    best = idx + len(delim)
            if best == -1:
                break
            _enqueue(buffer[:best])
            buffer = buffer[best:]

    if buffer.strip():
        _enqueue(buffer)
    print()
    if last_evt:
        last_evt.wait()


def run_text(brain: JarvisCore, tts: TTSEngine, speak: bool = False) -> None:
    print(_BANNER)
    print(f"Modo: {'texto + voz' if speak else 'texto'}  |  Modelo: {settings.ollama_model}")
    print("Comandos: 'abrir <app>', 'relatório', 'sair'. Ctrl+C para encerrar.\n")
    while True:
        try:
            text = input("Você: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not text:
            continue
        if _handle(text, brain, tts, speak):
            break


def run_voice(brain: JarvisCore, tts: TTSEngine, stt: STTEngine) -> None:
    print(_BANNER)
    print("Modo voz  |  Diga 'Jarvis' para ativar  |  Ctrl+C para sair\n")
    tts.speak("JARVIS online. Aguardando o senhor, Sr. Lima.")
    while True:
        try:
            print("Monitorando...    ", end="\r")
            text = stt.listen(timeout=30.0, fast=True)   # tiny model
            if text is None:
                continue
            if not any(w in text.lower() for w in _WAKE_WORDS):
                continue
            print(f"\n[Ativado: '{text}']")
            tts.speak("Sim, senhor?")
            command = stt.listen(timeout=12.0, fast=False)  # base model
            if not command:
                tts.speak("Não captei nenhum comando.")
                continue
            print(f"Comando: {command}")
            if _handle(command, brain, tts, speak=True):
                break
        except KeyboardInterrupt:
            print("\nEncerrando...")
            break


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "gui"

    if mode == "gui":
        run_gui()   # cria seu próprio JarvisCore/TTSEngine internamente
        return

    # Modos CLI (texto/voz) — só aqui precisamos checar Ollama e instanciar brain/tts
    import os
    if not os.getenv("GROQ_API_KEY", "").strip():
        try:
            from ollama import Client
            Client(host=settings.ollama_host).list()
        except Exception:
            print(f"[ERRO] Não foi possível conectar ao Ollama em {settings.ollama_host}")
            print("       Configure GROQ_API_KEY no .env ou inicie o Ollama.")
            sys.exit(1)

    brain = JarvisCore()
    tts = TTSEngine()

    if mode == "voice":
        run_voice(brain, tts, STTEngine())
    elif mode == "tts":
        run_text(brain, tts, speak=True)
    else:
        run_text(brain, tts, speak=False)


if __name__ == "__main__":
    main()
