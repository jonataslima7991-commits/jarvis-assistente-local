from __future__ import annotations

import json
import os
import re
import sys
import threading
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QUrl, QThread, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWidgets import QApplication, QMainWindow

from automation import morning_report
from config import settings
from core import JarvisCore
from memory import memory_store
from tools import (
    get_datetime, get_weather, get_weather_json, tavily_search, read_file,
    open_app, close_app, search_web,
    set_volume, volume_up, volume_down, mute_volume, unmute_volume, get_volume,
    set_timer, take_screenshot, add_note, read_notes, get_system_info,
    window_control, set_reminder, scan_projects, get_sys_stats,
    read_clipboard, read_screen, get_vscode_context, send_notification,
)
from tools import calendar_google, gmail_google, contacts
from voice import STTEngine, TTSEngine, WakeWordDetector

# ── Constants ─────────────────────────────────────────────────────────────────
_STARTUP_MUSIC      = Path(__file__).parent.parent / "assets" / "startup.mp3"
_LAST_BRIEFING_FILE = Path.home() / ".jarvis_last_briefing.json"
_LAST_ACTIVE_FILE   = Path.home() / ".jarvis_last_active.json"

_STOP_WORDS   = ["sair", "desligar", "tchau", "até logo", "ate logo"]
_REPORT_WORDS = ["relatório", "relatorio", "briefing", "resumo do dia"]

_OPEN_RE   = re.compile(r'\babr(?:ir|e|a)\s+(?:(?:o|a|os|as)\s+)?(.+)', re.IGNORECASE)
_CLOSE_RE  = re.compile(r'\b(?:fecha|fechar|encerra|encerrar|mata|matar|fecha|fecha)\s+(?:o\s+|a\s+)?(.+)', re.IGNORECASE)
_SEARCH_RE = re.compile(r'\b(?:pesquisa|pesquisar|busca|buscar|procura|procurar)\s+(.+?)(?:\s+no\s+(google|youtube|github|reddit))?$', re.IGNORECASE)
_VOL_SET_RE = re.compile(r'(?:volume|vol)\s+(?:em|para|a|de)?\s*(\d+)', re.IGNORECASE)
_VOL_UP_RE  = re.compile(r'\b(?:aumenta|sobe|eleva)\s+(?:o\s+)?volume', re.IGNORECASE)
_VOL_DN_RE  = re.compile(r'\b(?:diminui|baixa|abaixa|reduz|desce)\s+(?:o\s+)?volume', re.IGNORECASE)
_TIMER_RE    = re.compile(
    r'(?:timer|alarme|avisa?|lembra?)\s+.*?(\d+(?:[.,]\d+)?)\s*(minuto?s?|min|hora?s?|h|segundo?s?|seg)\s*(?:(?:de|para|sobre)\s+(.+))?',
    re.IGNORECASE,
)
_REMINDER_RE = re.compile(
    r'(?:me\s+)?(?:lembra?|avisa?|alerta?)\s+(?:.*?às?\s+)?(\d{1,2})[h:](\d{2})?\s*h?\s*(amanhã|amanha)?\s*(?:(?:de|para|sobre|pra|que)\s+(.+))?',
    re.IGNORECASE,
)
_NOTE_RE     = re.compile(r'\b(?:anota(?:r)?|registra(?:r)?)\s*[:\-]?\s*(.+)', re.IGNORECASE)
_MEMORY_RE   = re.compile(r'\b(?:lembra(?:r)?\s+que|guarda\s+que|salva\s+que|memoriza\s+que)\s+(.+)', re.IGNORECASE)
_FORGET_RE   = re.compile(r'\b(?:esqueça|esquece|apaga|delete|remove)\s+(?:que\s+|a\s+memória\s+(?:de\s+)?|isso\s+sobre\s+)?(.+)', re.IGNORECASE)

_SCREEN_WORDS  = ("lê a tela", "le a tela", "leia a tela", "o que está na tela",
                   "o que ta na tela", "lê a tela inteira", "captura a tela e lê")
_CLIP_WORDS    = ("lê o clipboard", "le o clipboard", "o que copiei",
                  "o que está no clipboard", "lê o que copiei", "mostra o clipboard")
_VSCODE_WORDS  = ("contexto do vscode", "contexto do vs code", "o que está aberto no vscode",
                   "qual arquivo está aberto", "explica o código", "o que esse código faz",
                   "analisa o código", "ajuda com o código", "lê o código")
_WIN_SW_RE   = re.compile(r'\b(?:alterna(?:r)?(?:\s+para)?|vai\s+para|muda\s+para|foca(?:\s+em)?)\s+(?:no?\s+|na?\s+|o\s+|a\s+)?(.+)', re.IGNORECASE)
_FILE_RE     = re.compile(r'\b(?:lê|le|leia|resume|resuma|explica)\s+(?:o\s+|a\s+)?(?:arquivo|pdf)\s+(.+)', re.IGNORECASE)

_REALTIME_WORDS = (
    "notícia", "notícias", "novidade", "novidades",
    "o que aconteceu", "o que houve", "acontecimento",
    "resultado do jogo", "resultado da partida", "placar", "quem ganhou", "quem venceu",
    "preço do", "preço da", "cotação do", "cotação da", "quanto custa", "valor do", "valor da",
    "hoje no jornal", "última hora", "últimas notícias", "breaking",
    "o que está acontecendo", "o que está rolando",
    "lançamento do", "lançamento da", "novo modelo", "nova versão",
)

_HELP_WORDS = (
    "o que você sabe fazer", "o que voce sabe fazer",
    "quais comandos", "lista os comandos", "me ajuda",
    "o que você pode fazer", "o que voce pode fazer",
    "quais são suas funções", "quais sao suas funcoes",
    "ajuda", "help",
)

_HELP_TEXT = """\
APPS & SITES
  • "abre o chrome / discord / spotify / vscode…"
  • "fecha o chrome / discord…"
  • "abre o youtube / gmail / github…"
  • "abre os downloads / documentos / desktop…"

BUSCA WEB
  • "pesquisa pandas no Google"  •  "busca lofi hip hop no YouTube"
  • "últimas notícias sobre IA"  •  "preço do dólar hoje"  •  "pesquisa sobre buracos negros"

VOLUME
  • "aumenta / baixa o volume"
  • "volume em 60"  •  "muta"  •  "desmuta"

JANELAS
  • "alterna para o vscode / chrome…"
  • "minimiza tudo"  •  "maximiza"  •  "fecha a janela"
  • "janelas abertas"

TIMERS & LEMBRETES
  • "timer de 10 minutos"
  • "me lembra às 15h de entrar na reunião"

CALENDÁRIO (Google Calendar)
  • "agenda uma reunião com o cliente segunda às 15h"
  • "qual a minha agenda"  •  "o que tenho marcado essa semana"
  • "cancela a reunião com o cliente"  •  "muda a reunião do cliente pra 16h"

E-MAIL (Gmail)
  • "tenho e-mail novo?"  •  "lê meu último e-mail"
  • "salva o contato professor como x@gmail.com"
  • "manda um e-mail pro professor avisando que vou faltar" (pede confirmação antes de enviar)

PRODUTIVIDADE
  • "tira um print"
  • "anota: comprar leite"  •  "minhas notas"
  • "status do sistema"
  • "lê o arquivo requirements.txt"  •  "resume o pdf relatorio.pdf"

INFO
  • "que horas são"  •  "como está o clima"

MEMÓRIA
  • "lembra que prefiro Python"
  • "minhas memórias"  •  "esqueça que prefiro Python"

OUTROS
  • "tchau" → encerra a sessão
  • "reinicia o jarvis" → reinicia o processo (aplica atualizações de código)\
"""

_HELP_SPEECH = (
    "Posso abrir e fechar apps, controlar volume e janelas, "
    "pesquisar na web e buscar notícias e dados em tempo real, "
    "criar timers e lembretes por horário, "
    "tirar prints, anotar coisas e verificar o sistema. "
    "A lista completa está na tela."
)

_STATE_MAP = {
    "CARREGANDO WHISPER...": "loading",
    "AGUARDANDO 'JARVIS'":   "idle",
    "AGUARDANDO COMANDO":    "listening",   # bloom alto — aguardando falar
    "PROCESSANDO":           "processing",
    "FALANDO":               "speaking",
    "ERRO":                  "error",
    "OFFLINE":               "offline",
}


# ══════════════════════════════════════════════════════════════════════════════
#  Tool-use via Groq — fallback quando nenhum regex de _dispatch() bate
# ══════════════════════════════════════════════════════════════════════════════
_TOOLS_SPEC = [
    {"type": "function", "function": {
        "name": "open_app", "description": "Abre um aplicativo, site ou pasta pelo nome.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Nome do app/site, ex: chrome, spotify, downloads"}},
            "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "close_app", "description": "Fecha um aplicativo pelo nome.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "set_volume", "description": "Define o volume do sistema para um valor de 0 a 100.",
        "parameters": {"type": "object", "properties": {"level": {"type": "integer"}}, "required": ["level"]},
    }},
    {"type": "function", "function": {
        "name": "volume_up", "description": "Aumenta o volume do sistema.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "volume_down", "description": "Diminui o volume do sistema.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "mute_volume", "description": "Muta o áudio do sistema.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "unmute_volume", "description": "Desmuta o áudio do sistema.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_volume", "description": "Informa o volume atual do sistema.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "add_note", "description": "Adiciona uma nota/anotação rápida com timestamp.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    }},
    {"type": "function", "function": {
        "name": "read_notes", "description": "Lê as últimas notas anotadas.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_system_info", "description": "Retorna CPU, RAM e espaço em disco atuais.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "remember_fact", "description": "Salva um fato ou preferência permanente sobre o usuário.",
        "parameters": {"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]},
    }},
    {"type": "function", "function": {
        "name": "forget_fact", "description": "Esquece/remove uma memória salva sobre um assunto.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "list_memories", "description": "Lista todas as memórias/fatos salvos sobre o usuário.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "read_file", "description": "Lê o conteúdo de um arquivo de texto, código ou PDF no disco.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "web_search", "description": "Busca informações atuais na web (notícias, preços, eventos recentes).",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "get_weather", "description": "Informa a previsão do tempo atual.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "take_screenshot", "description": "Captura a tela e salva no Desktop.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "window_control",
        "description": "Controla janelas: minimiza tudo, maximiza, fecha, lista janelas abertas.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["minimiza_tudo", "maximiza", "minimiza", "fecha", "lista"]}},
            "required": ["action"]},
    }},
    {"type": "function", "function": {
        "name": "create_calendar_event",
        "description": "Agenda uma reunião/evento no Google Calendar do usuário em uma data e hora específica.",
        "parameters": {"type": "object", "properties": {
            "summary":           {"type": "string", "description": "Título da reunião/evento"},
            "start_iso":         {"type": "string", "description": "Data e hora de início em ISO 8601, ex: 2026-06-20T15:00:00 — calcule a partir da data atual informada no contexto"},
            "duration_minutes":  {"type": "integer", "description": "Duração em minutos, padrão 60"}},
            "required": ["summary", "start_iso"]},
    }},
    {"type": "function", "function": {
        "name": "list_calendar_agenda",
        "description": "Lista os próximos eventos/reuniões agendados no Google Calendar.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "cancel_calendar_event",
        "description": "Cancela/remove um evento futuro do Google Calendar pelo título ou descrição aproximada.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Trecho do título do evento a cancelar, ex: 'reunião com o cliente'"}},
            "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "reschedule_calendar_event",
        "description": "Reagenda (muda data/hora) e/ou renomeia um evento futuro existente no Google Calendar.",
        "parameters": {"type": "object", "properties": {
            "query":         {"type": "string", "description": "Trecho do título do evento a alterar"},
            "new_start_iso": {"type": "string", "description": "Nova data/hora em ISO 8601, se for remarcar"},
            "new_summary":   {"type": "string", "description": "Novo título, se for renomear"}},
            "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "check_unread_emails",
        "description": "Verifica quantos e-mails não lidos há na caixa de entrada e lista os mais recentes.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "read_latest_email",
        "description": "Lê o conteúdo do e-mail mais recente da caixa de entrada.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "send_email",
        "description": "Envia um e-mail. 'to' pode ser um nome de contato salvo ou um endereço completo.",
        "parameters": {"type": "object", "properties": {
            "to":      {"type": "string", "description": "Nome do contato salvo ou endereço de e-mail do destinatário"},
            "subject": {"type": "string", "description": "Assunto do e-mail"},
            "body":    {"type": "string", "description": "Corpo/texto do e-mail"}},
            "required": ["to", "subject", "body"]},
    }},
    {"type": "function", "function": {
        "name": "add_contact",
        "description": "Salva um contato (nome e e-mail) para uso futuro no envio de e-mails.",
        "parameters": {"type": "object", "properties": {
            "name":  {"type": "string", "description": "Nome do contato"},
            "email": {"type": "string", "description": "Endereço de e-mail do contato"}},
            "required": ["name", "email"]},
    }},
    {"type": "function", "function": {
        "name": "list_contacts",
        "description": "Lista os contatos salvos.",
        "parameters": {"type": "object", "properties": {}},
    }},
]


def _tool_remember(args: dict) -> str:
    fact = args["fact"].strip(" .!?,")
    memory_store.remember(fact)
    return f"Memória salva: {fact}."


def _tool_forget(args: dict) -> str:
    query   = args["query"].strip(" .!?,")
    removed = memory_store.forget(query)
    return "Memória apagada." if removed else f"Não encontrei nenhuma memória sobre '{query}'."


_TOOL_IMPL = {
    "open_app":        lambda a: open_app(a["name"]),
    "close_app":       lambda a: close_app(a["name"]),
    "set_volume":      lambda a: set_volume(int(a["level"])),
    "volume_up":       lambda a: volume_up(),
    "volume_down":     lambda a: volume_down(),
    "mute_volume":     lambda a: mute_volume(),
    "unmute_volume":   lambda a: unmute_volume(),
    "get_volume":      lambda a: get_volume(),
    "add_note":        lambda a: add_note(a["text"]),
    "read_notes":      lambda a: read_notes(),
    "get_system_info": lambda a: get_system_info(),
    "remember_fact":   _tool_remember,
    "forget_fact":      _tool_forget,
    "list_memories":   lambda a: memory_store.list_all(),
    "read_file":       lambda a: read_file(a["path"]),
    "web_search":      lambda a: (tavily_search(a["query"]) or "Nenhum resultado encontrado."),
    "get_weather":     lambda a: get_weather(),
    "take_screenshot": lambda a: take_screenshot(),
    "window_control":  lambda a: window_control(a["action"]),
    "create_calendar_event": lambda a: calendar_google.create_event(
        a["summary"], a["start_iso"], int(a.get("duration_minutes", 60) or 60)),
    "list_calendar_agenda":  lambda a: calendar_google.list_upcoming_events(),
    "cancel_calendar_event": lambda a: calendar_google.delete_event(a["query"]),
    "reschedule_calendar_event": lambda a: calendar_google.update_event(
        a["query"], a.get("new_start_iso") or None, a.get("new_summary") or None),
    "check_unread_emails": lambda a: gmail_google.list_unread(),
    "read_latest_email":   lambda a: gmail_google.read_latest_email(),
    "add_contact":         lambda a: contacts.add_contact(a["name"], a["email"]),
    "list_contacts":       lambda a: contacts.list_contacts(),
    # "send_email" não entra aqui de propósito — passa por confirmação em _try_tool_call
}


# ══════════════════════════════════════════════════════════════════════════════
#  Music player — loop contínuo com ducking suave para TTS
# ══════════════════════════════════════════════════════════════════════════════
class MusicPlayer:
    """Toca startup.mp3 em loop com ducking automático quando o JARVIS fala."""

    _FULL  = 0.624  # volume normal (reduzido 15% + 20% adicional)
    _DUCK  = 0.192  # volume durante TTS (~30 % do normal)
    _FADE  = 0.07   # suavidade da transição por callback (~400 ms)

    def __init__(self, path: Path) -> None:
        self._path    = path
        self._samples: np.ndarray | None = None
        self._pos     = 0
        self._vol     = self._FULL
        self._target  = self._FULL
        self._stop    = threading.Event()

    def start(self) -> None:
        if not self._path.exists():
            print(f"[MUSIC] {self._path.name} não encontrado", flush=True)
            return
        threading.Thread(target=self._load_and_run, daemon=True, name="Music").start()

    def duck(self) -> None:
        self._target = self._DUCK

    def unduck(self) -> None:
        self._target = self._FULL

    def stop(self) -> None:
        self._stop.set()

    def _load_and_run(self) -> None:
        import miniaudio
        try:
            decoded = miniaudio.decode_file(
                str(self._path),
                output_format=miniaudio.SampleFormat.FLOAT32,
                nchannels=2, sample_rate=44100,
            )
            self._samples = np.frombuffer(decoded.samples, dtype=np.float32)\
                              .reshape(-1, 2).copy()
        except Exception as exc:
            print(f"[MUSIC] Erro ao carregar: {exc}", flush=True)
            return

        s = self._samples

        def callback(outdata: np.ndarray, frames: int, t, status) -> None:
            # Transição suave de volume
            self._vol += (self._target - self._vol) * self._FADE

            end = self._pos + frames
            if end <= len(s):
                chunk = s[self._pos:end]
            else:                          # loop seamless
                chunk = np.vstack([s[self._pos:], s[:end - len(s)]])
            self._pos = end % len(s)
            outdata[:] = chunk * self._vol

        try:
            with sd.OutputStream(
                samplerate=44100, channels=2, dtype="float32",
                blocksize=2048, callback=callback,
            ):
                self._stop.wait()
        except Exception as exc:
            print(f"[MUSIC] Erro no stream: {exc}", flush=True)


# ── Chime de ativação (substitui "Sim, senhor?" — instantâneo, sem rede) ──────
def _build_chime() -> np.ndarray:
    sr = 44100
    notes = [659.25, 880.00, 1318.51]   # E5 – A5 – E6  (acorde vivo)
    parts: list[np.ndarray] = []
    for i, freq in enumerate(notes):
        dur = 0.10
        t   = np.linspace(0, dur, int(sr * dur), endpoint=False)
        env = np.exp(-t * 22)            # decay rápido
        tone = np.sin(2 * np.pi * freq * t) * env * 0.30
        # pequena pausa entre notas
        gap = np.zeros(int(sr * 0.03), dtype=np.float32)
        parts.extend([tone.astype(np.float32), gap])
    mono   = np.concatenate(parts)
    stereo = np.column_stack([mono, mono])
    return stereo

_CHIME = _build_chime()


def _play_chime() -> None:
    try:
        sd.play(_CHIME, samplerate=44100, blocking=True)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  Voice worker
# ══════════════════════════════════════════════════════════════════════════════
class VoiceWorker(QThread):
    status_changed = Signal(str)
    user_said      = Signal(str)
    reply_chunk    = Signal(str)
    reply_done     = Signal()
    audio_level    = Signal(float)   # 0-1, emitido durante STT e TTS
    stats_updated  = Signal(str)     # JSON com métricas do sistema
    ui_event       = Signal(str)     # JSON para timer/notes/memory_count

    def __init__(self, brain: JarvisCore, tts: TTSEngine, stt: STTEngine,
                 music: MusicPlayer) -> None:
        super().__init__()
        self._brain      = brain
        self._tts        = tts
        self._stt        = stt
        self._music      = music
        self._wake       = WakeWordDetector()
        self._running    = True
        self._lvl_cb     = lambda lv: self.audio_level.emit(float(lv))
        self._proactive_queue: deque[str] = deque(maxlen=20)
        self._timer_cnt  = 0
        self._update_pending = threading.Event()

    def stop(self) -> None:
        self._running = False

    def _stats_loop(self) -> None:
        """Coleta métricas do sistema a cada 3s e emite para o HUD."""
        import json, time as _t
        import psutil
        psutil.cpu_percent()
        _t.sleep(0.8)
        while self._running:
            try:
                stats = get_sys_stats()
                stats["groq_usage"] = self._brain.get_usage_pct()
                print(
                    f"[STATS] cpu={stats['cpu']}% ram={stats['ram']}% "
                    f"disk={stats['disk']}% freq={stats['freq']} temp={stats['temp']} "
                    f"groq={stats['groq_usage']}%",
                    flush=True,
                )
                self.stats_updated.emit(json.dumps(stats))
            except Exception as exc:
                print(f"[STATS ERROR] {exc}", flush=True)
            _t.sleep(5.0)

    def _proactive_loop(self) -> None:
        """Monitora métricas e enfileira alertas de voz quando limites são atingidos."""
        import time as _t

        _cooldown = {"cpu": 300, "temp": 600, "disk": 3600, "ram": 300}
        _last: dict[str, float] = {}
        _t.sleep(60)   # aguarda 60s pós-boot antes de começar

        while self._running:
            try:
                now = _t.time()
                s   = get_sys_stats()

                def _due(key: str) -> bool:
                    return now - _last.get(key, 0) > _cooldown[key]

                def _alert(key: str, msg: str) -> None:
                    _last[key] = now
                    self._proactive_queue.append(msg)

                if s["cpu"] > 88 and _due("cpu"):
                    _alert("cpu", f"Atenção, senhor. Processador em {s['cpu']}% de uso.")

                if s.get("temp") and s["temp"] > 82 and _due("temp"):
                    _alert("temp", f"Temperatura elevada: {s['temp']} graus Celsius.")

                if s["disk"] > 90 and _due("disk"):
                    _alert("disk", f"Aviso: disco C com apenas {100 - s['disk']:.0f}% de espaço livre.")

                if s["ram"] > 90 and _due("ram"):
                    _alert("ram", f"Memória em {s['ram']}%. Considere fechar programas.")

            except Exception:
                pass
            _t.sleep(10)

    def _calendar_loop(self) -> None:
        """Verifica eventos do Google Calendar próximos do início e enfileira aviso de voz."""
        import datetime as _dt
        import time as _t

        if not calendar_google.is_configured():
            return  # credentials.json ausente — calendário não configurado, não tenta autenticar

        _alerted:          set[str] = set()
        _alerted_tomorrow: set[str] = set()
        _t.sleep(30)

        while self._running:
            try:
                events = calendar_google.get_due_soon_events(minutes_ahead=15)
                for ev in events:
                    eid = ev.get("id")
                    if not eid or eid in _alerted:
                        continue
                    _alerted.add(eid)
                    title = ev.get("summary", "evento sem título")
                    self._proactive_queue.append(f"Atenção: '{title}' começa em breve.")

                # Aviso com 1 dia de antecedência (janela de 20h-28h antes do evento)
                for ev in calendar_google.get_due_soon_events(minutes_ahead=1440):
                    eid = ev.get("id")
                    start = ev.get("start", {}).get("dateTime")
                    if not eid or not start or eid in _alerted_tomorrow:
                        continue
                    try:
                        ev_dt = _dt.datetime.fromisoformat(start)
                        hours_away = (ev_dt - _dt.datetime.now(ev_dt.tzinfo)).total_seconds() / 3600
                    except ValueError:
                        continue
                    if 20 <= hours_away <= 28:
                        _alerted_tomorrow.add(eid)
                        title = ev.get("summary", "evento")
                        self._proactive_queue.append(f"Aviso: você tem '{title}' marcado para amanhã.")

                next_ev = calendar_google.get_next_event()
                self.ui_event.emit(json.dumps({
                    "type": "agenda_update",
                    "summary": next_ev["summary"] if next_ev else None,
                    "start_iso": next_ev["start_iso"] if next_ev else None,
                }))
            except Exception:
                pass
            _t.sleep(300)

    def _email_loop(self) -> None:
        """Verifica e-mails não lidos periodicamente e atualiza o badge do HUD."""
        import time as _t

        if not gmail_google.is_configured():
            return

        _t.sleep(45)
        while self._running:
            try:
                count = gmail_google.get_unread_count()
                self.ui_event.emit(json.dumps({"type": "email_update", "count": count}))
            except Exception:
                pass
            _t.sleep(300)

    def _weather_loop(self) -> None:
        """Busca o clima periodicamente no Python (evita CORS do fetch direto no JS) e
        empurra para o painel via ui_event."""
        import time as _t

        while self._running:
            try:
                w = get_weather_json()
                if w:
                    self.ui_event.emit(json.dumps({"type": "weather_update", **w}))
            except Exception:
                pass
            _t.sleep(300)

    def _session_loop(self) -> None:
        """Sugere uma pausa em sessões longas (baseado em tempo de app aberto,
        sem detecção fina de atividade)."""
        import time as _t

        _BREAK_INTERVAL = 2 * 3600   # 2h
        next_alert = _t.time() + _BREAK_INTERVAL

        while self._running:
            if _t.time() >= next_alert:
                self._proactive_queue.append(
                    "Você está comigo há um bom tempo sem pausa. Que tal respirar um pouco?"
                )
                next_alert += _BREAK_INTERVAL
            _t.sleep(60)

    def _update_watch_loop(self) -> None:
        """Monitora mtime dos arquivos-fonte do projeto. Ao detectar mudança,
        sinaliza para o loop principal oferecer reiniciar (evita acesso concorrente ao mic)."""
        import time as _t

        root    = Path(__file__).parent.parent
        ignore  = {".venv", "__pycache__", "imagens", ".git"}
        watched = [
            f for f in list(root.rglob("*.py")) + list(root.rglob("*.html"))
            if not any(part in ignore for part in f.parts)
        ]
        baseline = {f: f.stat().st_mtime for f in watched if f.exists()}

        _t.sleep(20)
        while self._running:
            try:
                for f in list(baseline.keys()):
                    if not f.exists():
                        continue
                    mtime = f.stat().st_mtime
                    if mtime > baseline[f]:
                        baseline[f] = mtime
                        self._update_pending.set()
            except Exception:
                pass
            _t.sleep(60)

    def _restart_process(self) -> None:
        """Encerra o processo atual e relança o jarvis_main.py."""
        import subprocess
        self._music.stop()
        script = str(Path(__file__).parent.parent / "jarvis_main.py")
        subprocess.Popen([sys.executable, script])
        os._exit(0)

    def _offer_restart(self) -> None:
        """Pergunta por voz se deve reiniciar para aplicar uma atualização detectada no código."""
        self._quick_reply("Detectei uma atualização no meu código-fonte. Quer que eu reinicie agora?")
        self.status_changed.emit("AGUARDANDO COMANDO")
        answer = self._stt.listen(timeout=6.0, on_level=self._lvl_cb)
        if answer and any(w in answer.lower() for w in
                           ("sim", "reinicia", "pode", "confirma", "isso", "vai")):
            self._quick_reply("Reiniciando agora.")
            self._restart_process()
        else:
            self._quick_reply("Tudo bem, sigo na versão atual.")

    def run(self) -> None:
        try:
            threading.Thread(target=self._stats_loop,    daemon=True, name="SysStats").start()
            threading.Thread(target=self._proactive_loop, daemon=True, name="Proactive").start()
            threading.Thread(target=self._weather_loop,   daemon=True, name="Weather").start()
            threading.Thread(target=self._calendar_loop,  daemon=True, name="Calendar").start()
            threading.Thread(target=self._email_loop,     daemon=True, name="Email").start()
            threading.Thread(target=self._update_watch_loop, daemon=True, name="UpdateWatch").start()
            threading.Thread(target=self._session_loop,      daemon=True, name="Session").start()
            self._boot()
            self._loop()
        except Exception as e:
            self.status_changed.emit("ERRO")
            self.reply_chunk.emit(f"[ERRO CRÍTICO] {e}")
            self.reply_done.emit()

    # ── Boot ──────────────────────────────────────────────────────────────────
    def _boot(self) -> None:
        self._music.start()
        self.status_changed.emit("CARREGANDO WHISPER...")

        do_briefing = self._should_run_briefing()

        # Busca tudo EM PARALELO com carregamento do Whisper
        morning_data: list[str] = []
        project_data: list[str] = []
        sys_data:     list[dict] = []
        mail_data:    list[int]  = []

        def _fetch_morning():
            try:   morning_data.append(morning_report())
            except Exception as exc: print(f"[BOOT] morning_report: {exc}", flush=True)

        def _fetch_projects():
            try:   project_data.append(scan_projects())
            except Exception as exc: print(f"[BOOT] scan_projects: {exc}", flush=True)

        def _fetch_sys():
            try:   sys_data.append(get_sys_stats())
            except Exception as exc: print(f"[BOOT] sys_stats: {exc}", flush=True)

        def _fetch_mail():
            try:
                if gmail_google.is_configured():
                    mail_data.append(gmail_google.get_unread_count())
            except Exception as exc: print(f"[BOOT] mail: {exc}", flush=True)

        t4 = threading.Thread(target=self._wake.load, daemon=True)
        t4.start()

        # Projetos e e-mail: sempre, em toda inicialização (resumo curto, sem LLM)
        t2 = threading.Thread(target=_fetch_projects, daemon=True)
        t5 = threading.Thread(target=_fetch_mail,     daemon=True)
        t2.start(); t5.start()

        briefing_threads = []
        if do_briefing:
            t1 = threading.Thread(target=_fetch_morning, daemon=True)
            t3 = threading.Thread(target=_fetch_sys,     daemon=True)
            t1.start(); t3.start()
            briefing_threads = [(t1, 8), (t3, 6)]

        self._stt._load()           # carrega Whisper em paralelo com tudo
        t2.join(timeout=12)
        t5.join(timeout=6)
        for t, timeout in briefing_threads:
            t.join(timeout=timeout)
        t4.join(timeout=15)

        # ── Resumo rápido (e-mail + projetos) — toda inicialização, sem LLM ──
        self._music.duck()
        parts = []
        if mail_data:
            n = mail_data[0]
            parts.append("nenhum e-mail novo" if n == 0
                          else f"{n} e-mail{'s' if n != 1 else ''} não lido{'s' if n != 1 else ''}")
        if project_data:
            parts.append(project_data[0])
        if parts:
            try:
                msg = "Sistema pronto. " + ". ".join(parts)
                self._speak_sentences(msg)
            except Exception as exc:
                print(f"[BOOT] erro resumo: {exc}", flush=True)
        self._music.unduck()

        self._check_daily_continuity()

        if not do_briefing:
            return   # sem briefing completo — só o resumo rápido acima

        # Monta seção de sistema
        sys_section = ""
        if sys_data:
            s = sys_data[0]
            temp_str = f", temperatura {s['temp']}°C" if s.get("temp") else ""
            sys_section = (
                f"CPU: {s['cpu']}% | RAM: {s['ram']}% | "
                f"Disco C: {s['disk']}%{temp_str} | "
                f"Uptime: {s['uptime']}"
            )

        # Monta seções do briefing
        sections: list[str] = []
        if morning_data:
            sections.append(f"[Data / Clima / Mercado]\n{morning_data[0]}")
        if sys_section:
            sections.append(f"[Sistema]\n{sys_section}")
        if project_data:
            sections.append(f"[Projetos]\n{project_data[0]}")

        # Briefing completo via LLM
        if sections:
            try:
                self.status_changed.emit("PROCESSANDO")
                prompt = (
                    "Você é J.A.R.V.I.S., assistente pessoal de Jonatas Lima. "
                    "Com base nos dados abaixo, apresente um briefing matinal completo e direto. "
                    "Cubra: situação do dia, status do sistema e projetos ativos. "
                    "Tom confiante. Máximo 5 frases curtas. Sem markdown.\n\n"
                    + "\n\n".join(sections)
                )
                self._stream_and_speak(prompt)
            except Exception as exc:
                print(f"[BOOT] Erro briefing: {exc}", flush=True)

        self._mark_briefing_done()

    def _should_run_briefing(self) -> bool:
        """Briefing matinal só roda 1x/dia, entre 5h e 12h — evita repetir
        'bom dia' + chamada ao LLM em toda reinicialização."""
        import datetime as _dt
        now = _dt.datetime.now()
        if not (5 <= now.hour < 12):
            return False
        try:
            if _LAST_BRIEFING_FILE.exists():
                last = _LAST_BRIEFING_FILE.read_text(encoding="utf-8").strip()
                if last == now.date().isoformat():
                    return False
        except Exception:
            pass
        return True

    def _mark_briefing_done(self) -> None:
        import datetime as _dt
        try:
            _LAST_BRIEFING_FILE.write_text(_dt.date.today().isoformat(), encoding="utf-8")
        except Exception:
            pass

    def _check_daily_continuity(self) -> None:
        """Na primeira inicialização de um novo dia, comenta brevemente sobre a última
        conversa — fecha ciclos abertos e dá sensação de continuidade. Não roda no
        histórico principal (usa quick_complete), só fala se houver algo genuíno."""
        import datetime as _dt
        today = _dt.date.today().isoformat()
        try:
            last = _LAST_ACTIVE_FILE.read_text(encoding="utf-8").strip() if _LAST_ACTIVE_FILE.exists() else ""
        except Exception:
            last = ""

        if last == today:
            return

        try:
            _LAST_ACTIVE_FILE.write_text(today, encoding="utf-8")
        except Exception:
            pass

        history = self._brain.history
        last_user = next((h["content"] for h in reversed(history) if h["role"] == "user"), None)
        if not last_user:
            return

        try:
            reply = self._brain.quick_complete(
                "Você é JARVIS, assistente pessoal por voz. Seja extremamente conciso, no máximo 1 frase curta.",
                f"Última coisa que o usuário disse antes de hoje: \"{last_user}\". "
                "Se fizer sentido genuíno dar continuidade a isso (ex: perguntar como foi algo, "
                "reconhecer que ele voltou), escreva essa frase curta. "
                "Se não houver nada relevante para comentar, responda exatamente: SKIP"
            ).strip()
            if reply and reply.upper() != "SKIP":
                self._quick_reply(reply)
        except Exception as exc:
            print(f"[CONTINUITY] erro: {exc}", flush=True)

    # ── Main listen loop (com wake word) ─────────────────────────────────────
    def _loop(self) -> None:
        while self._running:
            # Oferece reiniciar se detectou atualização no código-fonte
            if self._update_pending.is_set():
                self._update_pending.clear()
                self._offer_restart()
                continue

            # Drena alertas proativos antes de entrar em espera
            while self._proactive_queue and self._running:
                msg = self._proactive_queue.popleft()
                self.reply_chunk.emit(f"[ALERTA] {msg}")
                self.reply_done.emit()
                self.status_changed.emit("FALANDO")
                self._music.duck()
                self._tts.speak(msg, on_level=self._lvl_cb)
                self._music.unduck()
                send_notification("J.A.R.V.I.S.", msg)

            # Fase 1: aguarda "hey jarvis" via openWakeWord (custo de CPU quase zero)
            self.status_changed.emit("AGUARDANDO 'JARVIS'")
            detected = self._wake.wait(stop_check=lambda: not self._running)
            if not detected or not self._running:
                continue

            # Fase 1.5: tenta capturar comando dito na mesma respiração
            # ("hey jarvis, abre o spotify") sem precisar do chime
            self.status_changed.emit("AGUARDANDO COMANDO")
            inline = self._stt.listen(timeout=3.0, on_level=self._lvl_cb)
            if not self._running:
                continue
            if inline and len(inline.split()) >= 2:
                self.user_said.emit(inline)
                self.status_changed.emit("PROCESSANDO")
                self._dispatch(inline)
                continue

            # Fase 2: toca chime e aguarda comando isolado — com 1 retentativa
            # audível antes de exigir "hey jarvis" de novo (evita quebrar o fluxo)
            threading.Thread(target=_play_chime, daemon=True).start()
            command = None
            for attempt in range(2):
                candidate = self._stt.listen(timeout=12.0, on_level=self._lvl_cb)
                if not self._running:
                    break
                if candidate and len(candidate.split()) >= 2:
                    command = candidate
                    break
                if attempt == 0:
                    self._quick_reply("Não entendi, pode repetir?")
                    self.status_changed.emit("AGUARDANDO COMANDO")

            if not command or not self._running:
                continue

            self.user_said.emit(command)
            self.status_changed.emit("PROCESSANDO")
            self._dispatch(command)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _quick_reply(self, msg: str) -> None:
        """Exibe e fala uma resposta curta de ferramenta sem streaming."""
        self.reply_chunk.emit(msg)
        self.reply_done.emit()
        self.status_changed.emit("FALANDO")
        self._music.duck()
        self._tts.speak(msg, on_level=self._lvl_cb)
        self._music.unduck()

    def _speak_sentences(self, text: str) -> None:
        """Fala e exibe um texto longo (pré-formatado, sem LLM) frase por frase —
        mesma revelação progressiva das respostas via _stream_and_speak, em vez de
        aparecer tudo de uma vez em bloco."""
        import re as _re
        sentences = [s.strip() for s in _re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if not sentences:
            return
        self.status_changed.emit("FALANDO")
        self._music.duck()
        for s in sentences:
            self.reply_chunk.emit(s + " ")
            self._tts.speak(s, on_level=self._lvl_cb)
        self.reply_done.emit()
        self._music.unduck()

    def _try_tool_call(self, cmd: str) -> bool:
        """Fallback: pergunta a um modelo rápido se algum tool deve ser chamado
        antes de cair no chat livre. Retorna True se uma ferramenta foi executada."""
        result = self._brain.tool_call(cmd, _TOOLS_SPEC)
        if result is None:
            return False
        name, args = result

        if name == "send_email":
            return self._confirm_and_send_email(args)

        if name == "read_latest_email":
            return self._read_email_naturally()

        impl = _TOOL_IMPL.get(name)
        if not impl:
            return False
        try:
            output = impl(args) or ""
        except Exception as exc:
            output = f"Erro ao executar {name}: {exc}"
        self._quick_reply(str(output))
        if name in ("remember_fact", "forget_fact"):
            self.ui_event.emit(json.dumps({"type": "memory_count", "count": len(memory_store)}))
        elif name == "add_note":
            self.ui_event.emit(json.dumps({"type": "notes_update", "text": args.get("text", "")}))
        return True

    def _confirm_and_send_email(self, args: dict) -> bool:
        """Resolve o contato, confirma por voz e só então envia o e-mail."""
        raw_to  = (args.get("to") or "").strip()
        subject = (args.get("subject") or "").strip()
        body    = (args.get("body") or "").strip()

        to = contacts.resolve(raw_to)
        if not to:
            self._quick_reply(
                f"Não encontrei o contato '{raw_to}' nem é um e-mail válido. "
                "Me diga o endereço completo ou salve o contato antes."
            )
            return True

        self._quick_reply(f"Vou enviar para {to}, assunto '{subject}'. Confirma o envio?")
        self.status_changed.emit("AGUARDANDO COMANDO")
        answer = self._stt.listen(timeout=6.0, on_level=self._lvl_cb)

        if answer and any(w in answer.lower() for w in
                           ("sim", "confirma", "manda", "envia", "pode", "isso")):
            output = gmail_google.send_email(to, subject, body)
            self._quick_reply(output)
        else:
            self._quick_reply("Envio cancelado.")
        return True

    def _read_email_naturally(self) -> bool:
        """Lê o e-mail mais recente, mas faz o LLM parafrasear antes de falar —
        evita ler URLs, tokens e números crus em voz alta."""
        raw = gmail_google.read_latest_email()
        if not raw.startswith("E-mail de"):
            self._quick_reply(raw)
            return True

        enriched = (
            f"[{raw}]\n\n"
            "Resuma esse e-mail de forma natural e falada, em até 4 frases. "
            "NÃO leia URLs, tokens, códigos numéricos, IPs ou links literalmente — "
            "apenas mencione o que eles representam (ex: 'tem um link de confirmação', "
            "'contém um código de verificação')."
        )
        self._stream_and_speak(enriched)
        return True

    def _alarm_callback(self, msg: str, timer_id: str | None = None) -> None:
        """Callback de timer/lembrete: fala + envia notificação toast."""
        self._quick_reply(msg)
        send_notification("J.A.R.V.I.S. — Lembrete", msg)
        if timer_id:
            self.ui_event.emit(json.dumps({"type": "timer_clear", "id": timer_id}))

    # ── Command dispatch ──────────────────────────────────────────────────────
    def _dispatch(self, cmd: str) -> None:
        low = cmd.lower().strip()

        # ── Encerrar sessão ───────────────────────────────────────────────────
        if any(w in low for w in _STOP_WORDS):
            msg = "Encerrando sessão. Até logo, Sr. Lima."
            self.reply_chunk.emit(msg); self.reply_done.emit()
            self.status_changed.emit("OFFLINE")
            self._music.duck()
            self._tts.speak(msg, on_level=self._lvl_cb)
            self._music.stop()
            self._running = False
            return

        # ── Reiniciar (manual) ───────────────────────────────────────────────
        if any(w in low for w in ("reinicia o jarvis", "reinicia você", "reinicia o sistema",
                                   "reinicie o jarvis", "se reinicia")):
            self._quick_reply("Reiniciando agora.")
            self._restart_process()
            return

        # ── Abrir app / site ──────────────────────────────────────────────────
        m = _OPEN_RE.search(low)
        if m:
            self._quick_reply(open_app(m.group(1).strip(" .!?,")))
            return

        # ── Fechar app ────────────────────────────────────────────────────────
        m = _CLOSE_RE.search(low)
        if m:
            self._quick_reply(close_app(m.group(1).strip(" .!?,")))
            return

        # ── Busca web ─────────────────────────────────────────────────────────
        m = _SEARCH_RE.search(low)
        if m:
            query = m.group(1).strip()
            if m.group(2):
                # Site explícito mencionado ("no Google/YouTube/...") → abre no browser
                self._quick_reply(search_web(query, m.group(2).lower()))
                return
            # Sem site explícito → resposta falada via Tavily
            query = re.sub(r'^sobre\s+', '', query).strip()
            self.reply_chunk.emit("[buscando na web...] ")
            self.status_changed.emit("PROCESSANDO")
            ctx = tavily_search(query)
            if ctx:
                enriched = (
                    f"[Busca em tempo real — {get_datetime()}]\n{ctx}\n\n"
                    f"Com base nesses resultados, responda em 1 a 3 frases sobre: {query}"
                )
                self._stream_and_speak(enriched)
            else:
                self._quick_reply(search_web(query, "google"))
            return

        # ── Volume ────────────────────────────────────────────────────────────
        m = _VOL_SET_RE.search(low)
        if m:
            self._quick_reply(set_volume(int(m.group(1))))
            return
        if _VOL_UP_RE.search(low):
            self._quick_reply(volume_up())
            return
        if _VOL_DN_RE.search(low):
            self._quick_reply(volume_down())
            return
        if any(w in low for w in ("muta", "silencia", "sem som")):
            self._quick_reply(mute_volume())
            return
        if any(w in low for w in ("desmuta", "desmute", "ativa o som", "ativa som")):
            self._quick_reply(unmute_volume())
            return
        if any(w in low for w in ("qual o volume", "que volume", "volume atual", "volume tá")):
            self._quick_reply(get_volume())
            return

        # ── Timer ─────────────────────────────────────────────────────────────
        m = _TIMER_RE.search(low)
        if m:
            qty   = float(m.group(1).replace(",", "."))
            unit  = m.group(2).lower()
            label = (m.group(3) or "").strip()
            if unit.startswith("h"):
                minutes = qty * 60
            elif unit.startswith("seg") or unit == "s":
                minutes = qty / 60
            else:
                minutes = qty
            self._timer_cnt += 1
            tid = f"t{self._timer_cnt}"
            dur_sec = int(minutes * 60)
            cb = lambda msg, _id=tid: self._alarm_callback(msg, timer_id=_id)
            result = set_timer(minutes, label, callback=cb)
            self._quick_reply(result)
            self.ui_event.emit(json.dumps({
                "type": "timer_add", "id": tid,
                "label": label or f"Timer {self._timer_cnt}",
                "dur": dur_sec,
            }))
            return

        # ── Screenshot ────────────────────────────────────────────────────────
        if any(w in low for w in ("print", "screenshot", "captura a tela", "captura de tela", "tira um print", "salva a tela")):
            self._quick_reply(take_screenshot())
            return

        # ── Notas ─────────────────────────────────────────────────────────────
        m = _NOTE_RE.search(low)
        if m:
            text = m.group(1).strip()
            self._quick_reply(add_note(text))
            self.ui_event.emit(json.dumps({"type": "notes_update", "text": text}))
            return
        if any(w in low for w in ("minhas notas", "o que está anotado", "lê as notas", "ler notas", "ver notas", "lista as notas", "mostra as notas")):
            self._quick_reply(read_notes())
            return

        # ── Status do sistema ─────────────────────────────────────────────────
        if any(w in low for w in ("status do sistema", "como está o computador", "desempenho", "uso de cpu", "uso de ram", "memória livre", "espaço em disco", "info do sistema", "status do pc")):
            self._quick_reply(get_system_info())
            return

        # ── Relatório de projetos ─────────────────────────────────────────────
        if any(w in low for w in ("relatório de projetos", "relatorio de projetos", "status dos projetos", "como estão os projetos", "escaneia os projetos", "revisa os projetos")):
            self.status_changed.emit("PROCESSANDO")
            self._quick_reply(scan_projects())
            return

        # ── Controle de janelas ───────────────────────────────────────────────
        m = _WIN_SW_RE.search(low)
        if m:
            app = m.group(1).strip(" .!?,")
            self._quick_reply(window_control("alterna", app))
            return
        if any(p in low for p in ("minimiza tudo", "minimizar tudo", "mostra a área de trabalho", "exibe a área de trabalho")):
            self._quick_reply(window_control("minimiza_tudo"))
            return
        if re.search(r'\bfecha\s+(?:a\s+)?janela', low):
            self._quick_reply(window_control("fecha"))
            return
        if re.search(r'\bmaximiza\b', low):
            self._quick_reply(window_control("maximiza"))
            return
        if re.search(r'\bminimiza\b', low):
            self._quick_reply(window_control("minimiza"))
            return
        if any(p in low for p in ("janelas abertas", "lista as janelas", "quais janelas", "janelas disponíveis")):
            self._quick_reply(window_control("lista"))
            return

        # ── Lembretes por horário ─────────────────────────────────────────────
        m = _REMINDER_RE.search(low)
        if m and not _TIMER_RE.search(low):
            hour     = int(m.group(1))
            minute   = int(m.group(2)) if m.group(2) else 0
            tomorrow = bool(m.group(3))
            label    = (m.group(4) or "").strip()
            if 0 <= hour <= 23:
                self._quick_reply(set_reminder(hour, minute, label, tomorrow,
                                               callback=self._alarm_callback))
                return

        # ── Ajuda ────────────────────────────────────────────────────────────────
        if any(w in low for w in _HELP_WORDS):
            self.reply_chunk.emit(_HELP_TEXT)
            self.reply_done.emit()
            self.status_changed.emit("FALANDO")
            self._music.duck()
            self._tts.speak(_HELP_SPEECH, on_level=self._lvl_cb)
            self._music.unduck()
            return

        # ── Relatório matinal ─────────────────────────────────────────────────
        if any(w in low for w in _REPORT_WORDS):
            self.reply_chunk.emit("[coletando dados...]\n"); self.reply_done.emit()
            data   = morning_report()
            prompt = f"Com base nos dados abaixo, faça um briefing matinal conciso e formal:\n\n{data}"
            self._stream_and_speak(prompt)
            return

        # ── Memória persistente ───────────────────────────────────────────────
        m = _MEMORY_RE.search(cmd)
        if m:
            fact = m.group(1).strip(" .!?,")
            memory_store.remember(fact)
            self._quick_reply(f"Memória salva: {fact}.")
            self.ui_event.emit(json.dumps({"type": "memory_count", "count": len(memory_store)}))
            return

        if any(w in low for w in ("minhas memórias", "minhas memorias",
                                   "o que você lembra", "o que voce lembra",
                                   "o que sabe sobre mim", "lista as memórias",
                                   "mostra as memórias", "quais são suas memórias")):
            self._quick_reply(memory_store.list_all())
            return

        if any(w in low for w in ("apaga todas as memórias", "limpa as memórias",
                                   "esquece tudo", "reseta a memória")):
            memory_store.clear()
            self._quick_reply("Todas as memórias apagadas.")
            self.ui_event.emit(json.dumps({"type": "memory_count", "count": 0}))
            return

        m = _FORGET_RE.search(cmd)
        if m:
            query   = m.group(1).strip(" .!?,")
            removed = memory_store.forget(query)
            if removed:
                self._quick_reply("Memória apagada.")
                self.ui_event.emit(json.dumps({"type": "memory_count", "count": len(memory_store)}))
            else:
                self._quick_reply(f"Não encontrei nenhuma memória sobre '{query}'.")
            return

        # ── Leitura de tela (OCR) ────────────────────────────────────────────
        if any(w in low for w in _SCREEN_WORDS):
            self.status_changed.emit("PROCESSANDO")
            result = read_screen()
            if result.startswith("Texto na tela:"):
                self._stream_and_speak(
                    f"[Conteúdo da tela capturado por OCR]\n{result}\n\n"
                    f"Resuma brevemente o que está na tela em 2 frases."
                )
            else:
                self._quick_reply(result)
            return

        # ── Clipboard ────────────────────────────────────────────────────────
        if any(w in low for w in _CLIP_WORDS):
            self._quick_reply(read_clipboard())
            return

        # ── Contexto VS Code ─────────────────────────────────────────────────
        if any(w in low for w in _VSCODE_WORDS):
            self.status_changed.emit("PROCESSANDO")
            ctx = get_vscode_context()
            enriched = (
                f"[Contexto do VS Code]\n{ctx}\n\n"
                f"Com base nisso, responda ao comando: {cmd}"
            )
            self._stream_and_speak(enriched)
            return

        # ── Leitura de arquivo (texto/código/PDF) ───────────────────────────────
        m = _FILE_RE.search(low)
        if m:
            fname = m.group(1).strip(" .!?,")
            self.status_changed.emit("PROCESSANDO")
            content = read_file(fname)
            if content.startswith("Conteúdo de"):
                enriched = f"[{content}]\n\nResuma o conteúdo acima em até 4 frases para o usuário."
                self._stream_and_speak(enriched)
            else:
                self._quick_reply(content)
            return

        # ── LLM (chat geral) ──────────────────────────────────────────────────
        enriched = cmd
        if any(w in low for w in ("hora", "horas", "horário", "data", "dia", "semana", "mês")):
            enriched = f"[{get_datetime()}]\n{cmd}"
        elif any(w in low for w in ("clima", "tempo", "temperatura", "chuva", "sol", "calor", "frio")):
            enriched = f"[{get_weather()}]\n{cmd}"
        elif any(w in low for w in _REALTIME_WORDS):
            self.reply_chunk.emit("[buscando na web...] ")
            self.status_changed.emit("PROCESSANDO")
            ctx = tavily_search(cmd)
            if ctx:
                enriched = (
                    f"[Busca em tempo real — {get_datetime()}]\n{ctx}\n\n"
                    f"Com base nesses resultados, responda em 1 a 3 frases: {cmd}"
                )
        elif self._try_tool_call(cmd):
            # Nenhum regex bateu, mas o roteador identificou e executou uma ferramenta
            return

        self._stream_and_speak(enriched)

    def _stream_and_speak(self, prompt: str) -> None:
        """Gera resposta frase a frase, falando cada uma assim que fica pronta."""
        buffer    = ""
        last_evt  = None
        first     = True   # primeira frase: mínimo menor → resposta mais rápida

        self._music.duck()

        def _enqueue(text: str) -> None:
            nonlocal last_evt, first
            text = text.strip()
            if not text:
                return
            self.reply_chunk.emit(text + " ")
            self.status_changed.emit("FALANDO")
            last_evt = self._tts.speak_async(text, on_level=self._lvl_cb)
            first = False

        for chunk in self._brain.stream_chat(prompt):
            buffer += chunk
            while True:
                best    = -1
                min_len = 10 if first else 25  # primeira frase começa antes
                for delim in (". ", "? ", "! ", "\n"):
                    idx = buffer.find(delim, min_len)
                    if idx != -1 and (best == -1 or idx < best):
                        best = idx + len(delim)
                if best == -1:
                    break
                _enqueue(buffer[:best])
                buffer = buffer[best:]

        if buffer.strip():
            _enqueue(buffer)

        self.reply_done.emit()

        if last_evt:
            last_evt.wait()

        self._music.unduck()


# ══════════════════════════════════════════════════════════════════════════════
#  Main window
# ══════════════════════════════════════════════════════════════════════════════
class JarvisWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S.")
        self.resize(1280, 800)
        self.setMinimumSize(860, 560)
        self.setStyleSheet("QMainWindow,QWidget{background:#000;}")

        self._page_ready = False
        self._js_queue: list[str] = []
        self._worker: VoiceWorker | None = None
        self._music  = MusicPlayer(_STARTUP_MUSIC)

        self._view = QWebEngineView()
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        self.setCentralWidget(self._view)
        html_path = Path(__file__).parent / "interface.html"
        self._view.load(QUrl.fromLocalFile(str(html_path.resolve())))
        self._view.loadFinished.connect(self._on_loaded)

    def _on_loaded(self, ok: bool) -> None:
        if not ok:
            return
        self._page_ready = True
        for code in self._js_queue:
            self._view.page().runJavaScript(code)
        self._js_queue.clear()

        self._worker = VoiceWorker(JarvisCore(), TTSEngine(), STTEngine(), self._music)
        self._worker.status_changed.connect(self._on_status)
        self._worker.user_said.connect(self._on_user_said)
        self._worker.reply_chunk.connect(self._on_chunk)
        self._worker.reply_done.connect(self._on_done)
        self._worker.audio_level.connect(self._on_audio_level)
        self._worker.stats_updated.connect(self._on_stats)
        self._worker.ui_event.connect(self._on_ui_event)
        self._worker.start()

    def _js(self, code: str) -> None:
        if self._page_ready:
            self._view.page().runJavaScript(code)
        else:
            self._js_queue.append(code)

    def _on_status(self, state: str) -> None:
        js_state = _STATE_MAP.get(state, "idle")
        self._js(f'JARVIS.setState({json.dumps(js_state)}, {json.dumps(state)})')

    def _on_user_said(self, text: str) -> None:
        self._js(f'JARVIS.setUserText({json.dumps(text)})')

    def _on_chunk(self, chunk: str) -> None:
        self._js(f'JARVIS.appendBotText({json.dumps(chunk)})')

    def _on_done(self) -> None:
        self._js("JARVIS.textDone()")

    def _on_audio_level(self, level: float) -> None:
        self._js(f"JARVIS.setAudioLevel({level:.4f})")

    def _on_stats(self, json_str: str) -> None:
        self._js(f"JARVIS.updateStats({json_str})")

    def _on_ui_event(self, json_str: str) -> None:
        self._js(f"JARVIS.handleEvent({json_str})")

    def closeEvent(self, event) -> None:
        if self._worker:
            self._worker.stop()
            self._worker.wait(3000)
        self._music.stop()
        event.accept()


# ── Entry point ───────────────────────────────────────────────────────────────
def run() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    win = JarvisWindow()
    win.show()
    sys.exit(app.exec())
