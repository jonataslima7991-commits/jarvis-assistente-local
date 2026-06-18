"""Autenticação OAuth compartilhada para integrações Google (Calendar + Gmail).

Um único consentimento cobre todos os escopos abaixo — Calendar e Gmail
reaproveitam o mesmo token, sem precisar logar duas vezes.
"""
from __future__ import annotations

from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

_CREDS_FILE = Path(__file__).parent.parent / "credentials.json"
_TOKEN_FILE = Path.home() / ".jarvis_google_token.json"

_creds = None


def is_configured() -> bool:
    return _CREDS_FILE.exists()


def get_credentials():
    """Retorna credenciais válidas, autenticando ou renovando sob demanda."""
    global _creds
    if _creds is not None and _creds.valid:
        return _creds

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)

    has_all_scopes = bool(creds) and set(SCOPES).issubset(set(creds.scopes or []))

    if not creds or not creds.valid or not has_all_scopes:
        if creds and creds.expired and creds.refresh_token and has_all_scopes:
            creds.refresh(Request())
        else:
            if not _CREDS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json não encontrado em {_CREDS_FILE}. "
                    "Baixe no Google Cloud Console e salve nesse caminho."
                )
            # Escopo incompleto ou token ausente — pede consentimento (de novo, se necessário)
            flow  = InstalledAppFlow.from_client_secrets_file(str(_CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    _creds = creds
    return _creds
