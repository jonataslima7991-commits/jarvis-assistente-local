from dataclasses import dataclass, field
from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class Settings:
    ollama_host:   str = field(default_factory=lambda: os.getenv("OLLAMA_HOST",   "http://localhost:11434"))
    ollama_model:  str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL",  "llama3.2"))
    city:          str = field(default_factory=lambda: os.getenv("JARVIS_CITY",   "São Paulo"))
    voice:         str = field(default_factory=lambda: os.getenv("JARVIS_VOICE",  "pt-BR-AntonioNeural"))
    whisper_model: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL", "base"))
    # Índice ou parte do nome do dispositivo de entrada (vazio = padrão do SO)
    mic_device:    str = field(default_factory=lambda: os.getenv("MIC_DEVICE",    ""))
    projects_dir:  str = field(default_factory=lambda: os.getenv("PROJECTS_DIR", str(os.path.expandvars(r"%USERPROFILE%\Desktop"))))


settings = Settings()
