"""Agenda de contatos local — mapeia nomes falados para endereços de e-mail."""
from __future__ import annotations

import difflib
import json
from pathlib import Path

_CONTACTS_FILE = Path.home() / ".jarvis_contacts.json"


def _load() -> dict[str, str]:
    try:
        if _CONTACTS_FILE.exists():
            return json.loads(_CONTACTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(data: dict[str, str]) -> None:
    try:
        _CONTACTS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    except Exception:
        pass


def add_contact(name: str, email: str) -> str:
    data = _load()
    data[name.strip().lower()] = email.strip()
    _save(data)
    return f"Contato salvo: {name} → {email}."


def resolve(name_or_email: str) -> str | None:
    """Retorna o e-mail correspondente. Se já for um e-mail, retorna direto."""
    s = (name_or_email or "").strip()
    if not s:
        return None
    if "@" in s:
        return s

    data = _load()
    key = s.lower()
    if key in data:
        return data[key]
    if not data:
        return None

    # Substring (qualquer direção) tem prioridade — cobre "Ricardo" batendo com "professor ricardo"
    for name, email in data.items():
        if key in name or name in key:
            return email

    best_name, best_ratio = None, 0.0
    for name in data:
        ratio = difflib.SequenceMatcher(None, key, name).ratio()
        if ratio > best_ratio:
            best_ratio, best_name = ratio, name
    return data[best_name] if best_ratio > 0.6 else None


def list_contacts() -> str:
    data = _load()
    if not data:
        return "Nenhum contato salvo."
    lines = [f"{name} — {email}" for name, email in data.items()]
    return "Contatos salvos:\n" + "\n".join(lines)
