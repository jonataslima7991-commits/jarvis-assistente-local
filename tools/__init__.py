from __future__ import annotations

import concurrent.futures
import datetime
import difflib
import glob
import os
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

import requests

from config import settings

_WEEKDAYS = [
    "segunda-feira", "terça-feira", "quarta-feira",
    "quinta-feira", "sexta-feira", "sábado", "domingo",
]
_MONTHS = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def get_datetime() -> str:
    now = datetime.datetime.now()
    return (
        f"Hoje é {_WEEKDAYS[now.weekday()]}, {now.day} de "
        f"{_MONTHS[now.month - 1]} de {now.year}. "
        f"Agora são {now.strftime('%H:%M')}."
    )


def get_weather() -> str:
    try:
        city = settings.city.replace(" ", "+")
        r = requests.get(f"https://wttr.in/{city}?format=3&lang=pt", timeout=5)
        r.raise_for_status()
        return r.text.strip()
    except Exception:
        return "Clima indisponível no momento."


def get_weather_json() -> dict | None:
    """Clima estruturado (temp/descrição) para o painel da UI — busca server-side,
    evitando o bloqueio de CORS que ocorre ao buscar wttr.in direto do JS em origem file://."""
    try:
        city = settings.city.replace(" ", "+")
        r = requests.get(f"https://wttr.in/{city}?format=j1&lang=pt", timeout=5)
        r.raise_for_status()
        data = r.json()
        c = data["current_condition"][0]
        desc = (c.get("lang_pt", [{}])[0].get("value")
                or c["weatherDesc"][0]["value"]).lower()
        return {"temp": c["temp_C"], "desc": desc}
    except Exception:
        return None


def tavily_search(query: str, max_results: int = 3) -> str:
    """Busca informações em tempo real via Tavily. Retorna string vazia se sem chave ou sem resultado."""
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return ""
    try:
        from tavily import TavilyClient
        client  = TavilyClient(api_key=api_key)
        resp    = client.search(query, max_results=max_results, search_depth="basic")
        snippets: list[str] = []
        for item in resp.get("results", []):
            title   = item.get("title", "")
            content = (item.get("content") or "")[:350].strip()
            if content:
                snippets.append(f"• {title}: {content}")
        return "\n".join(snippets)
    except Exception as exc:
        print(f"[TAVILY] Erro: {exc}", flush=True)
        return ""


# ── Alias: nome falado → nome canônico do Start Menu ──────────────────────────
_ALIASES: dict[str, str] = {
    # Navegadores
    "chrome":                  "Google Chrome",
    "google chrome":           "Google Chrome",
    "navegador":               "Google Chrome",
    "browser":                 "Google Chrome",
    "firefox":                 "Firefox",
    "edge":                    "Microsoft Edge",
    "internet":                "Microsoft Edge",

    # Microsoft Office
    "word":                    "Word",
    "excel":                   "Excel",
    "planilha":                "Excel",
    "powerpoint":              "PowerPoint",
    "apresentação":            "PowerPoint",
    "apresentacao":            "PowerPoint",
    "slides":                  "PowerPoint",
    "slide":                   "PowerPoint",
    "outlook":                 "Outlook",
    "email":                   "Outlook",
    "e-mail":                  "Outlook",
    "teams":                   "Microsoft Teams",
    "onenote":                 "OneNote",
    "access":                  "Access",
    "publisher":               "Publisher",

    # Sistema Windows
    "explorador de arquivos":  "File Explorer",
    "explorador":              "File Explorer",
    "explorer":                "File Explorer",
    "arquivos":                "File Explorer",
    "gerenciador de arquivos": "File Explorer",
    "pasta":                   "File Explorer",
    "calculadora":             "Calculator",
    "calc":                    "Calculator",
    "bloco de notas":          "Notepad",
    "bloco":                   "Notepad",
    "notepad":                 "Notepad",
    "notepad++":               "Notepad++",
    "paint":                   "Paint",
    "paint 3d":                "Paint 3D",
    "configurações":           "Settings",
    "configuracoes":           "Settings",
    "configuracao":            "Settings",
    "painel de controle":      "Control Panel",
    "painel":                  "Control Panel",
    "gerenciador de tarefas":  "Task Manager",
    "tarefa":                  "Task Manager",
    "tarefas":                 "Task Manager",
    "task manager":            "Task Manager",
    "terminal":                "Windows Terminal",
    "windows terminal":        "Windows Terminal",
    "powershell":              "Windows PowerShell",
    "power shell":             "Windows PowerShell",
    "cmd":                     "Command Prompt",
    "prompt":                  "Command Prompt",
    "prompt de comando":       "Command Prompt",
    "registro":                "Registry Editor",
    "regedit":                 "Registry Editor",
    "recorte":                 "Snipping Tool",
    "snipping":                "Snipping Tool",
    "captura de tela":         "Snipping Tool",
    "wordpad":                 "WordPad",

    # Desenvolvimento
    "vscode":                  "Visual Studio Code",
    "vs code":                 "Visual Studio Code",
    "visual studio code":      "Visual Studio Code",
    "code":                    "Visual Studio Code",
    "visual studio":           "Visual Studio",
    "pycharm":                 "PyCharm",
    "intellij":                "IntelliJ IDEA",
    "eclipse":                 "Eclipse",
    "android studio":          "Android Studio",
    "github desktop":          "GitHub Desktop",
    "github":                  "GitHub Desktop",
    "git bash":                "Git Bash",
    "git":                     "Git Bash",
    "postman":                 "Postman",
    "insomnia":                "Insomnia",
    "dbeaver":                 "DBeaver Community",
    "mysql workbench":         "MySQL Workbench",
    "docker":                  "Docker Desktop",
    "putty":                   "PuTTY",
    "filezilla":               "FileZilla",

    # Mídia
    "spotify":                 "Spotify",
    "vlc":                     "VLC media player",
    "media player":            "Windows Media Player",
    "potplayer":               "PotPlayer 64-bit",
    "obs":                     "OBS Studio",
    "obs studio":              "OBS Studio",
    "audacity":                "Audacity",
    "davinci":                 "DaVinci Resolve",
    "davinci resolve":         "DaVinci Resolve",

    # Comunicação
    "discord":                 "Discord",
    "whatsapp":                "WhatsApp",
    "telegram":                "Telegram",
    "slack":                   "Slack",
    "zoom":                    "Zoom",
    "skype":                   "Skype",
    "anydesk":                 "AnyDesk",
    "teamviewer":              "TeamViewer",
    "signal":                  "Signal",

    # Games / Launchers
    "steam":                   "Steam",
    "epic":                    "Epic Games Launcher",
    "epic games":              "Epic Games Launcher",
    "gog":                     "GOG Galaxy",
    "origin":                  "EA App",
    "ea":                      "EA App",

    # Produtividade / Outros
    "notion":                  "Notion",
    "obsidian":                "Obsidian",
    "figma":                   "Figma",
    "photoshop":               "Adobe Photoshop",
    "illustrator":             "Adobe Illustrator",
    "premiere":                "Adobe Premiere Pro",
    "after effects":           "Adobe After Effects",
    "lightroom":               "Adobe Lightroom",
    "acrobat":                 "Adobe Acrobat",
    "pdf":                     "Adobe Acrobat",
    "7zip":                    "7-Zip File Manager",
    "7-zip":                   "7-Zip File Manager",
    "winrar":                  "WinRAR",
    "bitwarden":               "Bitwarden",
    "keepass":                 "KeePass",
    "anki":                    "Anki",
    "qbittorrent":             "qBittorrent",
    "ccleaner":                "CCleaner",
}

# ── Comandos diretos do Windows (não dependem do Start Menu) ──────────────────
_DIRECT_CMDS: dict[str, str] = {
    "File Explorer":          "explorer.exe",
    "Calculator":             "calc.exe",
    "Notepad":                "notepad.exe",
    "Paint":                  "mspaint.exe",
    "WordPad":                "write.exe",
    "Control Panel":          "control.exe",
    "Task Manager":           "taskmgr.exe",
    "Registry Editor":        "regedit.exe",
    "Snipping Tool":          "snippingtool.exe",
    "Command Prompt":         'start "" cmd.exe',
    "Windows PowerShell":     'start "" powershell.exe',
    "Settings":               "start ms-settings:",
}

_OFFICE_ROOTS = [
    r"C:\Program Files\Microsoft Office\root",
    r"C:\Program Files (x86)\Microsoft Office\root",
    r"C:\Program Files\Microsoft Office",
    r"C:\Program Files (x86)\Microsoft Office",
]

_OFFICE_EXES: dict[str, str] = {
    "word":       "WINWORD.EXE",
    "excel":      "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE",
    "outlook":    "OUTLOOK.EXE",
    "onenote":    "ONENOTE.EXE",
    "access":     "MSACCESS.EXE",
    "publisher":  "MSPUB.EXE",
}

_START_MENU_DIRS = [
    Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")),
    Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
]

_DESKTOP_DIRS = [
    Path(os.path.expandvars(r"%USERPROFILE%\Desktop")),
    Path(r"C:\Users\Public\Desktop"),
]

_FOLDER_MAP: dict[str, Path] = {
    "downloads":          Path.home() / "Downloads",
    "documentos":         Path.home() / "Documents",
    "documents":          Path.home() / "Documents",
    "desktop":            Path.home() / "Desktop",
    "área de trabalho":   Path.home() / "Desktop",
    "area de trabalho":   Path.home() / "Desktop",
    "imagens":            Path.home() / "Pictures",
    "pictures":           Path.home() / "Pictures",
    "fotos":              Path.home() / "Pictures",
    "música":             Path.home() / "Music",
    "musica":             Path.home() / "Music",
    "vídeos":             Path.home() / "Videos",
    "videos":             Path.home() / "Videos",
    "onedrive":           Path.home() / "OneDrive",
    "disco":              Path("C:/"),
    "disco c":            Path("C:/"),
}


def _find_office(key: str) -> str | None:
    exe = _OFFICE_EXES.get(key)
    if not exe:
        return None
    for root in _OFFICE_ROOTS:
        for path in glob.glob(os.path.join(root, "**", exe), recursive=True):
            if os.path.isfile(path):
                return path
    return None


_SHORTCUT_CACHE: dict[str, tuple[Path | None, float]] = {}
_SHORTCUT_CACHE_TTL = 120.0  # segundos


def _search_shortcuts(query: str, dirs: list[Path]) -> Path | None:
    """Retorna o atalho .lnk cujo nome melhor corresponde ao query."""
    cache_key = query.lower() + "|" + ",".join(str(d) for d in dirs)
    cached = _SHORTCUT_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[1] < _SHORTCUT_CACHE_TTL:
        return cached[0]

    query_low = query.lower()
    best_score = 0.0
    best_path: Path | None = None

    for base_dir in dirs:
        if not base_dir.exists():
            continue
        for lnk in base_dir.rglob("*.lnk"):
            stem = lnk.stem.lower()

            if query_low in stem:
                score = len(query_low) / max(len(stem), 1) + 0.5
                if score > best_score:
                    best_score, best_path = score, lnk
                continue

            ratio = difflib.SequenceMatcher(None, query_low, stem).ratio()
            if ratio > 0.72 and ratio > best_score:
                best_score, best_path = ratio, lnk

    _SHORTCUT_CACHE[cache_key] = (best_path, time.monotonic())
    return best_path


def open_app(name: str) -> str:
    """Abre aplicativo ou site pelo nome. Tenta: site → alias → cmd direto → Office → Start Menu → Desktop → fallback."""
    raw      = name.strip(" .!?,")
    key      = raw.lower()
    canonical = _ALIASES.get(key, raw)
    target   = canonical.lower()

    # 0. Site conhecido
    site_result = _try_open_site(key)
    if site_result:
        return site_result

    # 0.5. Pasta do usuário
    folder = _FOLDER_MAP.get(key)
    if folder and folder.exists():
        os.startfile(str(folder))
        return f"Pasta {raw} aberta."

    # 1. Comando direto do Windows (não depende de instalação)
    for app_name, cmd in _DIRECT_CMDS.items():
        if app_name.lower() in (key, target):
            try:
                subprocess.Popen(cmd, shell=True)
                return f"{app_name} aberto."
            except Exception as e:
                return f"Falha ao abrir {app_name}: {e}"

    # 2. Office: busca .exe em Program Files
    for office_key in _OFFICE_EXES:
        if office_key in key or office_key in target:
            path = _find_office(office_key)
            if path:
                try:
                    subprocess.Popen([path])
                    return f"{canonical} aberto."
                except Exception as e:
                    return f"Falha ao abrir {canonical}: {e}"
            break

    # 3. Start Menu (cobre a maioria dos apps instalados)
    lnk = _search_shortcuts(canonical, _START_MENU_DIRS)
    if not lnk and canonical.lower() != key:
        lnk = _search_shortcuts(key, _START_MENU_DIRS)

    # 4. Desktop
    if not lnk:
        lnk = _search_shortcuts(canonical, _DESKTOP_DIRS)
    if not lnk and canonical.lower() != key:
        lnk = _search_shortcuts(key, _DESKTOP_DIRS)

    if lnk:
        try:
            os.startfile(str(lnk))
            return f"{lnk.stem} aberto."
        except Exception as e:
            return f"Encontrei {lnk.stem} mas não consegui abrir: {e}"

    # 5. Fallback: deixa o Windows tentar resolver pelo nome
    try:
        subprocess.Popen(f'start "" "{canonical}"', shell=True)
        return f"Tentando abrir {canonical}..."
    except Exception:
        return f"Não encontrei '{raw}'. Verifique o nome ou abra pelo Start Menu."


# ══════════════════════════════════════════════════════════════════════════════
#  Sites & busca web
# ══════════════════════════════════════════════════════════════════════════════
_SITE_MAP: dict[str, str] = {
    "youtube":          "https://www.youtube.com",
    "gmail":            "https://mail.google.com",
    "google":           "https://www.google.com",
    "github":           "https://www.github.com",
    "instagram":        "https://www.instagram.com",
    "twitter":          "https://www.twitter.com",
    "x":                "https://www.x.com",
    "facebook":         "https://www.facebook.com",
    "linkedin":         "https://www.linkedin.com",
    "netflix":          "https://www.netflix.com",
    "reddit":           "https://www.reddit.com",
    "twitch":           "https://www.twitch.tv",
    "chatgpt":          "https://chat.openai.com",
    "chat gpt":         "https://chat.openai.com",
    "openai":           "https://chat.openai.com",
    "claude":           "https://claude.ai",
    "whatsapp web":     "https://web.whatsapp.com",
    "drive":            "https://drive.google.com",
    "google drive":     "https://drive.google.com",
    "maps":             "https://maps.google.com",
    "google maps":      "https://maps.google.com",
    "stackoverflow":    "https://stackoverflow.com",
    "stack overflow":   "https://stackoverflow.com",
    "amazon":           "https://www.amazon.com.br",
    "mercado livre":    "https://www.mercadolivre.com.br",
    "mercadolivre":     "https://www.mercadolivre.com.br",
    "kaggle":           "https://www.kaggle.com",
    "colab":            "https://colab.research.google.com",
    "google colab":     "https://colab.research.google.com",
    "notion":           "https://www.notion.so",
    "figma":            "https://www.figma.com",
    "trello":           "https://trello.com",
    "canva":            "https://www.canva.com",
}


def _try_open_site(key: str) -> str | None:
    url = _SITE_MAP.get(key)
    if url:
        webbrowser.open(url)
        return f"Abrindo {key} no navegador."
    return None


def search_web(query: str, engine: str = "google") -> str:
    """Pesquisa na web no motor especificado."""
    q = query.replace(" ", "+")
    urls = {
        "google":  f"https://www.google.com/search?q={q}",
        "youtube": f"https://www.youtube.com/results?search_query={q}",
        "github":  f"https://github.com/search?q={q}",
        "reddit":  f"https://www.reddit.com/search/?q={q}",
    }
    url = urls.get(engine.lower(), urls["google"])
    try:
        webbrowser.open(url)
        return f"Pesquisando '{query}' no {engine.capitalize()}."
    except Exception as e:
        return f"Não consegui pesquisar: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  Fechar aplicativos
# ══════════════════════════════════════════════════════════════════════════════
_PROCESS_MAP: dict[str, str] = {
    "chrome":                "chrome.exe",
    "google chrome":         "chrome.exe",
    "firefox":               "firefox.exe",
    "edge":                  "msedge.exe",
    "spotify":               "Spotify.exe",
    "discord":               "Discord.exe",
    "vscode":                "Code.exe",
    "vs code":               "Code.exe",
    "visual studio code":    "Code.exe",
    "notepad":               "notepad.exe",
    "bloco de notas":        "notepad.exe",
    "notepad++":             "notepad++.exe",
    "calculadora":           "Calculator.exe",
    "paint":                 "mspaint.exe",
    "word":                  "WINWORD.EXE",
    "excel":                 "EXCEL.EXE",
    "powerpoint":            "POWERPNT.EXE",
    "outlook":               "OUTLOOK.EXE",
    "teams":                 "Teams.exe",
    "zoom":                  "Zoom.exe",
    "whatsapp":              "WhatsApp.exe",
    "telegram":              "Telegram.exe",
    "slack":                 "slack.exe",
    "steam":                 "steam.exe",
    "obs":                   "obs64.exe",
    "obs studio":            "obs64.exe",
    "vlc":                   "vlc.exe",
    "postman":               "Postman.exe",
    "docker":                "Docker Desktop.exe",
    "pycharm":               "pycharm64.exe",
    "terminal":              "WindowsTerminal.exe",
    "powershell":            "powershell.exe",
    "explorador":            "explorer.exe",
    "explorer":              "explorer.exe",
    "anydesk":               "AnyDesk.exe",
    "audacity":              "audacity.exe",
    "gimp":                  "gimp-2.10.exe",
    "inkscape":              "inkscape.exe",
    "filezilla":             "filezilla.exe",
}


def close_app(name: str) -> str:
    """Fecha um aplicativo pelo nome usando taskkill."""
    key = name.lower().strip(" .!?,")
    canonical = _ALIASES.get(key, name)
    target    = canonical.lower()

    proc = _PROCESS_MAP.get(key) or _PROCESS_MAP.get(target)
    if not proc:
        for k, p in _PROCESS_MAP.items():
            if key in k or k in key:
                proc = p
                break

    if proc:
        result = subprocess.run(
            ["taskkill", "/IM", proc, "/F"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return f"{canonical} encerrado."
        return f"{canonical} não estava aberto."

    # Fallback: tenta pelo nome como exe
    exe = canonical.replace(" ", "") + ".exe"
    result = subprocess.run(
        ["taskkill", "/IM", exe, "/F"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return f"{canonical} encerrado."

    return f"Não encontrei processo de '{name}' rodando."


# ══════════════════════════════════════════════════════════════════════════════
#  Controle de volume do sistema (pycaw)
# ══════════════════════════════════════════════════════════════════════════════
def _vol_interface():
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume


def get_volume() -> str:
    try:
        v = _vol_interface()
        level = round(v.GetMasterVolumeLevelScalar() * 100)
        muted = v.GetMute()
        return f"Volume em {level}%" + (" (mutado)." if muted else ".")
    except Exception as e:
        return f"Não consegui verificar o volume: {e}"


def set_volume(level: int) -> str:
    level = max(0, min(100, level))
    try:
        v = _vol_interface()
        v.SetMasterVolumeLevelScalar(level / 100, None)
        v.SetMute(False, None)
        return f"Volume em {level}%."
    except Exception as e:
        return f"Não consegui ajustar o volume: {e}"


def volume_up(step: int = 15) -> str:
    try:
        v = _vol_interface()
        current = round(v.GetMasterVolumeLevelScalar() * 100)
        new     = min(100, current + step)
        v.SetMasterVolumeLevelScalar(new / 100, None)
        v.SetMute(False, None)
        return f"Volume aumentado para {new}%."
    except Exception as e:
        return f"Não consegui aumentar o volume: {e}"


def volume_down(step: int = 15) -> str:
    try:
        v = _vol_interface()
        current = round(v.GetMasterVolumeLevelScalar() * 100)
        new     = max(0, current - step)
        v.SetMasterVolumeLevelScalar(new / 100, None)
        return f"Volume reduzido para {new}%."
    except Exception as e:
        return f"Não consegui diminuir o volume: {e}"


def mute_volume() -> str:
    try:
        _vol_interface().SetMute(True, None)
        return "Sistema mutado."
    except Exception as e:
        return f"Não consegui mutar: {e}"


def unmute_volume() -> str:
    try:
        v = _vol_interface()
        v.SetMute(False, None)
        level = round(v.GetMasterVolumeLevelScalar() * 100)
        return f"Áudio ativado. Volume em {level}%."
    except Exception as e:
        return f"Não consegui desmutar: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  Timer
# ══════════════════════════════════════════════════════════════════════════════
def set_timer(minutes: float, label: str = "", callback=None) -> str:
    """Inicia um timer em background. Chama callback(msg) ao terminar."""
    def _run() -> None:
        time.sleep(minutes * 60)
        unit      = "minuto" if minutes == 1 else "minutos"
        label_str = f" de {label}" if label else ""
        msg       = f"Timer{label_str} finalizado! {int(minutes)} {unit} se passaram."
        if callback:
            callback(msg)

    label_str = f" '{label}'" if label else ""
    unit      = "minuto" if minutes == 1 else "minutos"
    threading.Thread(target=_run, daemon=True, name=f"Timer-{minutes}min").start()
    return f"Timer de {int(minutes)} {unit}{label_str} iniciado."


# ══════════════════════════════════════════════════════════════════════════════
#  Screenshot
# ══════════════════════════════════════════════════════════════════════════════
_SCREENSHOTS_DIR = Path.home() / "Desktop"


def take_screenshot() -> str:
    """Captura a tela e salva no Desktop."""
    try:
        import mss
        import mss.tools
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _SCREENSHOTS_DIR / f"jarvis_print_{ts}.png"
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])
            mss.tools.to_png(shot.rgb, shot.size, output=str(path))
        return f"Screenshot salvo: {path.name}"
    except Exception as e:
        return f"Não consegui capturar a tela: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  Notas rápidas
# ══════════════════════════════════════════════════════════════════════════════
_NOTES_FILE = Path(__file__).parent.parent / "notes.txt"


def add_note(text: str) -> str:
    """Adiciona uma nota com timestamp."""
    try:
        ts   = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        line = f"[{ts}] {text}\n"
        with open(_NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(line)
        return f"Anotado: {text}"
    except Exception as e:
        return f"Não consegui anotar: {e}"


def read_notes(n: int = 5) -> str:
    """Lê as últimas n notas."""
    try:
        if not _NOTES_FILE.exists():
            return "Nenhuma nota encontrada."
        lines = [l for l in _NOTES_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not lines:
            return "Nenhuma nota encontrada."
        recent = lines[-n:]
        return "Últimas notas:\n" + "\n".join(recent)
    except Exception as e:
        return f"Não consegui ler as notas: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  Info do sistema
# ══════════════════════════════════════════════════════════════════════════════
def _get_cpu_temp_windows() -> float | None:
    """Tenta ler temperatura via wmic (várias estratégias)."""
    # Estratégia 1: MSAcpi_ThermalZoneTemperature (funciona em alguns fabricantes)
    try:
        r = subprocess.run(
            ['wmic', '/namespace:\\\\root\\WMI', 'PATH',
             'MSAcpi_ThermalZoneTemperature', 'get', 'CurrentTemperature'],
            capture_output=True, text=True, timeout=2
        )
        vals = [l.strip() for l in r.stdout.splitlines() if l.strip().isdigit()]
        if vals:
            t = round((int(vals[0]) / 10) - 273.15, 1)
            if 0 < t < 120:
                return t
    except Exception:
        pass

    # Estratégia 2: OpenHardwareMonitor via WMI (se instalado)
    try:
        r = subprocess.run(
            ['wmic', '/namespace:\\\\root\\OpenHardwareMonitor', 'PATH',
             'Sensor', 'where', "SensorType='Temperature' and Name='CPU Package'",
             'get', 'Value'],
            capture_output=True, text=True, timeout=2
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            try:
                t = float(line)
                if 0 < t < 120:
                    return round(t, 1)
            except ValueError:
                pass
    except Exception:
        pass

    # Estratégia 3: LibreHardwareMonitor via WMI (fork moderno do OpenHardwareMonitor)
    try:
        r = subprocess.run(
            ['wmic', '/namespace:\\\\root\\LibreHardwareMonitor', 'PATH',
             'Sensor', 'where', "SensorType='Temperature' and Name like '%CPU Package%'",
             'get', 'Value'],
            capture_output=True, text=True, timeout=2
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            try:
                t = float(line)
                if 0 < t < 120:
                    return round(t, 1)
            except ValueError:
                pass
    except Exception:
        pass

    return None


def get_sys_stats() -> dict:
    """Retorna métricas do sistema como dict para o HUD em tempo real."""
    import psutil, time as _t, os

    cpu = psutil.cpu_percent(interval=0)
    mem = psutil.virtual_memory()

    # Disco: usa a partição do drive do sistema, fallback para qualquer raiz disponível
    sys_drive = os.environ.get("SystemDrive", "C:") + "\\"
    try:
        disk = psutil.disk_usage(sys_drive)
        disk_pct = round(disk.percent, 1)
    except Exception:
        # Tenta qualquer partição disponível
        disk_pct = 0
        for part in psutil.disk_partitions(all=False):
            try:
                disk_pct = round(psutil.disk_usage(part.mountpoint).percent, 1)
                break
            except Exception:
                continue

    freq = psutil.cpu_freq()

    # Temperatura
    temp = None
    try:
        sensors = psutil.sensors_temperatures()
        if sensors:
            for entries in sensors.values():
                if entries:
                    temp = round(entries[0].current, 1)
                    break
    except Exception:
        pass
    if temp is None:
        temp = _get_cpu_temp_windows()

    uptime = int(_t.time() - psutil.boot_time())
    h, rem = divmod(uptime, 3600)
    m, _   = divmod(rem, 60)

    return {
        "cpu":    round(cpu, 1),
        "ram":    round(mem.percent, 1),
        "disk":   disk_pct,
        "freq":   round(freq.current / 1000, 2) if freq else None,
        "temp":   temp,
        "uptime": f"{h:02d}:{m:02d}",
    }


def get_system_info() -> str:
    """Retorna CPU, RAM e espaço em disco."""
    try:
        import psutil
        cpu        = psutil.cpu_percent(interval=0)
        ram        = psutil.virtual_memory()
        disk       = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
        ram_used   = ram.used   // (1024 ** 2)
        ram_total  = ram.total  // (1024 ** 2)
        disk_free  = disk.free  // (1024 ** 3)
        disk_total = disk.total // (1024 ** 3)
        return (
            f"CPU em {cpu:.0f}%. "
            f"RAM: {ram_used} MB de {ram_total} MB ({ram.percent:.0f}% usados). "
            f"Disco C: {disk_free} GB livres de {disk_total} GB."
        )
    except Exception as e:
        return f"Não consegui verificar o sistema: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  Scan de projetos
# ══════════════════════════════════════════════════════════════════════════════

# Pastas que não são projetos e devem ser ignoradas
_IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".idea", ".vscode", "dist", "build", "target", ".mypy_cache",
    "Jogos", "Warframe Logs", "Docs",
}

# Extensões que indicam código/projeto ativo
_CODE_EXTS = {".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c",
              ".cs", ".r", ".ipynb", ".sql", ".html", ".css", ".json",
              ".yaml", ".yml", ".md", ".txt"}


def _git_status(path: Path) -> dict:
    """Retorna info do git para um repositório."""
    def _run(args):
        return subprocess.run(
            args, cwd=path, capture_output=True, text=True, timeout=5
        ).stdout.strip()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            f_mod    = ex.submit(_run, ["git", "status", "--short"])
            f_commit = ex.submit(_run, ["git", "log", "-1", "--format=%cr|%s"])
            f_ahead  = ex.submit(_run, ["git", "rev-list", "--count", "@{u}..HEAD"])

        modified_out = f_mod.result()
        last_commit  = f_commit.result()
        ahead        = f_ahead.result()

        return {
            "modified":    len([l for l in modified_out.splitlines() if l.strip()]),
            "last_commit": last_commit,
            "ahead":       int(ahead) if ahead.isdigit() else 0,
        }
    except Exception:
        return {}


def _days_since(ts: float) -> int:
    return int((time.time() - ts) / 86400)


def scan_projects(base_dir: str | None = None) -> str:
    """Escaneia projetos e retorna resumo falado para TTS."""
    from config import settings

    root = Path(base_dir or settings.projects_dir)
    if not root.exists():
        return f"Pasta de projetos não encontrada: {root}"

    projects: list[dict] = []

    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name in _IGNORE_DIRS or entry.name.startswith("."):
            continue

        # Arquivos de código na raiz e 1 nível abaixo
        code_files: list[Path] = []
        try:
            for f in entry.rglob("*"):
                if f.suffix in _CODE_EXTS and not any(p in _IGNORE_DIRS for p in f.parts):
                    code_files.append(f)
                if len(code_files) > 500:
                    break
        except PermissionError:
            continue

        if not code_files:
            continue

        # Arquivo mais recente
        newest = max(code_files, key=lambda f: f.stat().st_mtime)
        days   = _days_since(newest.stat().st_mtime)

        proj = {
            "name":       entry.name,
            "files":      len(code_files),
            "days_old":   days,
            "is_git":     (entry / ".git").exists(),
            "git":        {},
        }

        if proj["is_git"]:
            proj["git"] = _git_status(entry)

        projects.append(proj)

    if not projects:
        return "Nenhum projeto encontrado na pasta configurada."

    # Ordena por atividade recente
    projects.sort(key=lambda p: p["days_old"])

    # ── Monta relatório falado ────────────────────────────────────────────────
    total  = len(projects)
    active = [p for p in projects if p["days_old"] <= 7]

    lines: list[str] = []
    lines.append(
        f"Senhor, encontrei {total} projeto{'s' if total > 1 else ''} "
        f"({'nenhum' if not active else str(len(active))} ativo{'s' if len(active) != 1 else ''} nos últimos sete dias)."
    )

    for p in projects[:4]:  # fala no máximo 4
        name  = p["name"]
        days  = p["days_old"]
        files = p["files"]
        g     = p.get("git", {})

        if days == 0:
            when = "modificado hoje"
        elif days == 1:
            when = "modificado ontem"
        else:
            when = f"sem atividade há {days} dias"

        detail = f"{name}: {files} arquivo{'s' if files != 1 else ''}, {when}"

        if g.get("modified"):
            n = g["modified"]
            detail += f", {n} {'alterações' if n != 1 else 'alteração'} não {'salvas' if n != 1 else 'salva'}"
        if g.get("ahead"):
            n = g["ahead"]
            detail += f", {n} commit{'s' if n != 1 else ''} por enviar"

        lines.append(detail + ".")

    if total > 4:
        lines.append(f"E mais {total - 4} projeto{'s' if total - 4 != 1 else ''} sem atividade recente.")

    return " ".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  Controle de janelas
# ══════════════════════════════════════════════════════════════════════════════

# Termos de busca para cada app comum nos títulos das janelas
_WIN_SEARCH: dict[str, list[str]] = {
    "chrome":       ["chrome", "google"],
    "navegador":    ["chrome", "firefox", "edge", "opera", "browser"],
    "firefox":      ["firefox"],
    "edge":         ["edge"],
    "opera":        ["opera"],
    "vscode":       ["visual studio code"],
    "vs code":      ["visual studio code"],
    "code":         ["visual studio code"],
    "word":         ["word"],
    "excel":        ["excel"],
    "powerpoint":   ["powerpoint"],
    "outlook":      ["outlook"],
    "teams":        ["teams"],
    "discord":      ["discord"],
    "spotify":      ["spotify"],
    "whatsapp":     ["whatsapp"],
    "telegram":     ["telegram"],
    "explorer":     ["file explorer", "explorador de arquivos"],
    "explorador":   ["file explorer", "explorador de arquivos"],
    "terminal":     ["windows terminal", "cmd", "powershell"],
    "notepad":      ["notepad"],
    "bloco":        ["notepad"],
    "pycharm":      ["pycharm"],
    "steam":        ["steam"],
}


def _find_window(app_name: str):
    import pygetwindow as gw
    app_low   = app_name.lower().strip()
    terms     = _WIN_SEARCH.get(app_low, [app_low])
    all_wins  = [w for w in gw.getAllWindows() if w.title.strip()]

    # Busca por substring
    for w in all_wins:
        title_low = w.title.lower()
        if any(t in title_low for t in terms):
            return w

    # Fuzzy fallback
    best_score, best_win = 0.0, None
    for w in all_wins:
        ratio = difflib.SequenceMatcher(None, app_low, w.title.lower()).ratio()
        if ratio > best_score:
            best_score, best_win = ratio, w
    return best_win if best_score > 0.35 else None


def window_control(action: str, app_name: str = "") -> str:
    """Controla janelas: alterna, minimiza, maximiza, fecha, lista."""
    import pyautogui

    act = action.lower()

    # ── Ações globais (sem app específico) ───────────────────────────────────
    if act == "minimiza_tudo":
        pyautogui.hotkey("win", "d")
        return "Área de trabalho exibida."

    if act == "fecha":
        pyautogui.hotkey("alt", "f4")
        return "Janela atual fechada."

    if act == "maximiza" and not app_name:
        pyautogui.hotkey("win", "up")
        return "Janela maximizada."

    if act == "minimiza" and not app_name:
        pyautogui.hotkey("win", "down")
        return "Janela minimizada."

    if act == "restaura" and not app_name:
        pyautogui.hotkey("win", "down")
        return "Janela restaurada."

    if act == "alterna" and not app_name:
        pyautogui.hotkey("alt", "tab")
        return "Alternando janela."

    if act == "lista":
        import pygetwindow as gw
        titles = [w.title for w in gw.getAllWindows() if w.title.strip()][:8]
        return "Janelas abertas: " + "; ".join(titles) if titles else "Nenhuma janela encontrada."

    # ── Ações em app específico ───────────────────────────────────────────────
    if app_name:
        win = _find_window(app_name)
        if not win:
            return f"Janela de '{app_name}' não encontrada. O app está aberto?"
        try:
            if act in ("alterna", "vai_para", "foca"):
                win.restore()
                win.activate()
                return f"Alternado para: {win.title[:45]}"
            elif act == "minimiza":
                win.minimize()
                return f"Janela minimizada."
            elif act == "maximiza":
                win.maximize()
                win.activate()
                return f"Janela maximizada."
            elif act == "fecha":
                win.close()
                return f"Janela fechada."
        except Exception as e:
            return f"Não consegui controlar a janela: {e}"

    return "Comando de janela não reconhecido."


# ══════════════════════════════════════════════════════════════════════════════
#  Lembretes por horário
# ══════════════════════════════════════════════════════════════════════════════
def set_reminder(hour: int, minute: int = 0, label: str = "",
                 tomorrow: bool = False, callback=None) -> str:
    """Agenda um lembrete para uma hora específica. Chama callback quando disparar."""
    now    = datetime.datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if target <= now or tomorrow:
        target += datetime.timedelta(days=1)

    wait_secs = (target - now).total_seconds()

    def _run() -> None:
        time.sleep(wait_secs)
        label_str = f": {label}" if label else ""
        min_str   = f"{minute:02d}" if minute else ""
        msg       = f"Lembrete{label_str}. São {hour:02d}h{min_str}."
        if callback:
            callback(msg)

    threading.Thread(target=_run, daemon=True,
                     name=f"Reminder-{hour:02d}h{minute:02d}").start()

    when      = "amanhã" if target.date() > now.date() else "hoje"
    time_str  = f"{hour:02d}h{minute:02d}" if minute else f"{hour:02d}h"
    label_str = f" de '{label}'" if label else ""
    mins_away = int(wait_secs / 60)

    return f"Lembrete{label_str} para {when} às {time_str}. Faltam {mins_away} minutos."


# ══════════════════════════════════════════════════════════════════════════════
#  Notificações Windows
# ══════════════════════════════════════════════════════════════════════════════
def send_notification(title: str, message: str, timeout: int = 5) -> None:
    """Envia notificação toast do Windows sem bloquear."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="J.A.R.V.I.S.",
            timeout=timeout,
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  Leitura de arquivos
# ══════════════════════════════════════════════════════════════════════════════
_READABLE_EXTS = {
    ".txt", ".py", ".md", ".json", ".csv", ".yaml", ".yml",
    ".js", ".ts", ".html", ".css", ".log", ".ini", ".cfg",
}


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    parts  = [(p.extract_text() or "") for p in reader.pages[:20]]
    return "\n".join(parts)


def _resolve_file(name: str) -> Path | None:
    p = Path(name).expanduser()
    if p.is_absolute() and p.exists():
        return p

    candidates = [
        Path.cwd() / p,
        Path(settings.projects_dir) / p,
        Path.home() / "Desktop" / p,
        Path.home() / "Documents" / p,
    ]
    for c in candidates:
        if c.exists():
            return c

    try:
        matches = list(Path(settings.projects_dir).rglob(p.name))
        if matches:
            return matches[0]
    except Exception:
        pass
    return None


def read_file(path_or_name: str, max_chars: int = 3000) -> str:
    """Lê um arquivo de texto/código/PDF do disco e retorna prévia do conteúdo."""
    found = _resolve_file(path_or_name)
    if found is None:
        return f"Arquivo não encontrado: {path_or_name}"

    suffix = found.suffix.lower()
    try:
        if suffix == ".pdf":
            text = _read_pdf(found)
        elif suffix in _READABLE_EXTS:
            text = found.read_text(encoding="utf-8", errors="ignore")
        else:
            return f"Formato não suportado para leitura: {suffix or '(sem extensão)'}"
    except Exception as e:
        return f"Não consegui ler o arquivo: {e}"

    text = text.strip()
    if not text:
        return f"Conteúdo de {found.name}: arquivo vazio."

    preview = text[:max_chars]
    suffix_note = "..." if len(text) > max_chars else ""
    return f"Conteúdo de {found.name}:\n{preview}{suffix_note}"


# ══════════════════════════════════════════════════════════════════════════════
#  Clipboard
# ══════════════════════════════════════════════════════════════════════════════
def read_clipboard() -> str:
    """Lê o conteúdo atual da área de transferência."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        content = root.clipboard_get()
        root.destroy()
        if not content:
            return "Área de transferência vazia."
        preview = content[:600]
        suffix  = "..." if len(content) > 600 else ""
        return f"Clipboard: {preview}{suffix}"
    except Exception as e:
        return f"Não consegui ler o clipboard: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  OCR — leitura de tela
# ══════════════════════════════════════════════════════════════════════════════
def read_screen(region: str = "full") -> str:
    """Captura a tela e extrai texto via OCR (requer Tesseract instalado)."""
    try:
        import mss
        import mss.tools
        from PIL import Image
        import pytesseract

        with mss.mss() as sct:
            monitor = sct.monitors[0]   # monitor principal
            shot    = sct.grab(monitor)
            img     = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        # Reduz para metade para acelerar OCR e reduzir ruído
        w, h  = img.size
        img   = img.resize((w // 2, h // 2), Image.LANCZOS)
        text  = pytesseract.image_to_string(img, lang="por+eng", timeout=10)
        text  = " ".join(text.split())   # normaliza espaços

        if not text.strip():
            return "Nenhum texto legível encontrado na tela."

        preview = text[:700]
        suffix  = "..." if len(text) > 700 else ""
        return f"Texto na tela: {preview}{suffix}"

    except pytesseract.pytesseract.TesseractNotFoundError:
        return (
            "Tesseract não encontrado. Instale em: "
            "https://github.com/UB-Mannheim/tesseract/wiki "
            "e adicione ao PATH."
        )
    except ImportError as e:
        return f"Dependência ausente: {e}. Execute: pip install mss pytesseract Pillow"
    except Exception as e:
        return f"Erro ao ler tela: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  Contexto do VS Code
# ══════════════════════════════════════════════════════════════════════════════
def get_vscode_context() -> str:
    """Retorna arquivo/projeto aberto no VS Code + código copiado no clipboard."""
    try:
        import pygetwindow as gw

        wins = [w for w in gw.getAllWindows()
                if "Visual Studio Code" in w.title and w.title.strip()]

        file_info = ""
        if wins:
            title  = wins[0].title
            # Formato: "● arquivo.py — pasta — Visual Studio Code"
            parts  = [p.strip().lstrip("●").strip() for p in title.split("—")]
            fname  = parts[0] if parts else "?"
            proj   = parts[1].replace("Visual Studio Code", "").strip() if len(parts) > 1 else "?"
            file_info = f"Arquivo: {fname} | Projeto: {proj}"
        else:
            file_info = "VS Code não está aberto ou sem arquivo ativo."

        # Clipboard pode conter código selecionado
        try:
            import tkinter as tk
            _root = tk.Tk(); _root.withdraw()
            clipboard = _root.clipboard_get(); _root.destroy()
        except Exception:
            clipboard = ""

        parts_out = [file_info]
        if clipboard:
            preview = clipboard[:800]
            parts_out.append(f"Código no clipboard:\n{preview}")

        return "\n".join(parts_out)

    except Exception as e:
        return f"Não consegui verificar o VS Code: {e}"
