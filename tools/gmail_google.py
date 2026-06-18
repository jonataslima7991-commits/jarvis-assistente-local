"""Integração com Gmail — leitura e envio de e-mails (compartilha auth com o Calendar)."""
from __future__ import annotations

import base64
import re
from email.mime.text import MIMEText

from tools.google_auth import get_credentials, is_configured

_service = None  # cache do client autenticado, criado sob demanda


def _get_service():
    global _service
    if _service is not None:
        return _service
    from googleapiclient.discovery import build
    _service = build("gmail", "v1", credentials=get_credentials())
    return _service


def _get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _sender_name(raw_from: str) -> str:
    """Extrai só o nome de exibição de um header 'From', descartando o e-mail cru."""
    m = re.match(r'^"?([^"<]+)"?\s*<', raw_from)
    if m:
        return m.group(1).strip()
    return raw_from.split("@")[0] if "@" in raw_from else raw_from


def _decode_body(payload: dict) -> str:
    """Extrai recursivamente o corpo em texto simples de um payload de mensagem Gmail."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        text = _decode_body(part)
        if text:
            return text
    return ""


def get_unread_count() -> int:
    """Conta e-mails não lidos na caixa de entrada, para exibição no HUD."""
    try:
        service = _get_service()
        result = service.users().messages().list(
            userId="me", labelIds=["INBOX", "UNREAD"], maxResults=99,
        ).execute()
        return len(result.get("messages", []))
    except Exception:
        return 0


def list_unread(max_results: int = 5) -> str:
    """Lista os e-mails não lidos mais recentes da caixa de entrada."""
    try:
        service = _get_service()
        result = service.users().messages().list(
            userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results,
        ).execute()
        msgs = result.get("messages", [])
        if not msgs:
            return "Nenhum e-mail não lido."

        lines = []
        for m in msgs:
            msg = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
            headers = msg["payload"]["headers"]
            sender  = _sender_name(_get_header(headers, "From"))
            subject = _get_header(headers, "Subject") or "(sem assunto)"
            lines.append(f"{subject} — de {sender}")

        return f"Você tem {len(msgs)} e-mails não lidos:\n" + "\n".join(lines)
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Não consegui verificar os e-mails: {e}"


def read_latest_email() -> str:
    """Lê o conteúdo do e-mail mais recente da caixa de entrada."""
    try:
        service = _get_service()
        result = service.users().messages().list(
            userId="me", labelIds=["INBOX"], maxResults=1,
        ).execute()
        msgs = result.get("messages", [])
        if not msgs:
            return "Nenhum e-mail na caixa de entrada."

        msg     = service.users().messages().get(userId="me", id=msgs[0]["id"], format="full").execute()
        headers = msg["payload"]["headers"]
        sender  = _sender_name(_get_header(headers, "From"))
        subject = _get_header(headers, "Subject") or "(sem assunto)"
        body    = _decode_body(msg["payload"]).strip()[:1000]

        return f"E-mail de {sender}, assunto '{subject}':\n{body or '(sem corpo em texto simples)'}"
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Não consegui ler o e-mail: {e}"


def send_email(to: str, subject: str, body: str) -> str:
    """Envia um e-mail a partir da conta autenticada."""
    try:
        service = _get_service()
        message = MIMEText(body)
        message["to"]      = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"E-mail enviado para {to}."
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Não consegui enviar o e-mail: {e}"
