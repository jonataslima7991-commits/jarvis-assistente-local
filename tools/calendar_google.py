"""Integração com Google Calendar — criação, leitura, edição e cancelamento de eventos."""
from __future__ import annotations

import datetime as _dt
import difflib
from zoneinfo import ZoneInfo

from tools.google_auth import get_credentials, is_configured

_TIMEZONE = "America/Sao_Paulo"
_TZ       = ZoneInfo(_TIMEZONE)

_service = None  # cache do client autenticado, criado sob demanda


def _localize(dt: _dt.datetime) -> _dt.datetime:
    """Garante que o datetime tenha timezone (assume America/Sao_Paulo se naive)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=_TZ)


def _get_service():
    """Retorna o client autenticado do Google Calendar, autenticando sob demanda."""
    global _service
    if _service is not None:
        return _service
    from googleapiclient.discovery import build
    _service = build("calendar", "v3", credentials=get_credentials())
    return _service


def find_conflicts(start_iso: str, duration_minutes: int = 60) -> list[dict]:
    """Retorna eventos existentes que se sobrepõem ao intervalo solicitado."""
    try:
        service = _get_service()
        start   = _localize(_dt.datetime.fromisoformat(start_iso))
        end     = start + _dt.timedelta(minutes=duration_minutes)

        result = service.events().list(
            calendarId="primary",
            timeMin=start.isoformat(), timeMax=end.isoformat(),
            singleEvents=True, orderBy="startTime",
        ).execute()
        return result.get("items", [])
    except Exception:
        return []


def create_event(summary: str, start_iso: str, duration_minutes: int = 60,
                  description: str = "") -> str:
    """Cria um evento no Google Calendar. start_iso no formato 'YYYY-MM-DDTHH:MM:SS'."""
    try:
        service = _get_service()
        start = _localize(_dt.datetime.fromisoformat(start_iso))
        end   = start + _dt.timedelta(minutes=duration_minutes)

        conflicts = find_conflicts(start_iso, duration_minutes)
        warning = ""
        if conflicts:
            other = conflicts[0].get("summary", "outro evento")
            warning = f"Atenção: você já tem '{other}' marcado nesse horário. "

        event = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": _TIMEZONE},
            "end":   {"dateTime": end.isoformat(),   "timeZone": _TIMEZONE},
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": 15}],
            },
        }
        service.events().insert(calendarId="primary", body=event).execute()

        data_str = start.strftime("%d/%m às %H:%M")
        return f"{warning}Reunião '{summary}' agendada para {data_str}."
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Não consegui agendar o evento: {e}"


def _find_event_by_query(query: str, days_ahead: int = 60) -> dict | None:
    """Busca o evento futuro cujo título melhor corresponde à query (fuzzy)."""
    try:
        service  = _get_service()
        now      = _dt.datetime.now(_TZ)
        time_max = now + _dt.timedelta(days=days_ahead)

        result = service.events().list(
            calendarId="primary", timeMin=now.isoformat(), timeMax=time_max.isoformat(),
            maxResults=50, singleEvents=True, orderBy="startTime",
        ).execute()
        events = result.get("items", [])
        if not events:
            return None

        query_low  = query.lower()
        best_score = 0.0
        best_event = None
        for ev in events:
            title = ev.get("summary", "").lower()
            if query_low in title:
                score = len(query_low) / max(len(title), 1) + 0.5
            else:
                score = difflib.SequenceMatcher(None, query_low, title).ratio()
            if score > best_score:
                best_score, best_event = score, ev

        return best_event if best_score > 0.3 else None
    except Exception:
        return None


def delete_event(query: str) -> str:
    """Cancela o evento futuro cujo título corresponda à query."""
    try:
        service = _get_service()
        ev = _find_event_by_query(query)
        if not ev:
            return f"Não encontrei nenhum evento futuro parecido com '{query}'."

        service.events().delete(calendarId="primary", eventId=ev["id"]).execute()
        return f"Evento '{ev.get('summary', query)}' cancelado."
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Não consegui cancelar o evento: {e}"


def update_event(query: str, new_start_iso: str | None = None,
                  new_summary: str | None = None) -> str:
    """Reagenda e/ou renomeia o evento futuro cujo título corresponda à query."""
    try:
        service = _get_service()
        ev = _find_event_by_query(query)
        if not ev:
            return f"Não encontrei nenhum evento futuro parecido com '{query}'."

        if new_start_iso:
            old_start = ev["start"].get("dateTime")
            old_end   = ev["end"].get("dateTime")
            duration  = _dt.timedelta(minutes=60)
            if old_start and old_end:
                duration = _dt.datetime.fromisoformat(old_end) - _dt.datetime.fromisoformat(old_start)

            new_start = _localize(_dt.datetime.fromisoformat(new_start_iso))
            new_end   = new_start + duration
            ev["start"] = {"dateTime": new_start.isoformat(), "timeZone": _TIMEZONE}
            ev["end"]   = {"dateTime": new_end.isoformat(),   "timeZone": _TIMEZONE}

        if new_summary:
            ev["summary"] = new_summary

        service.events().update(calendarId="primary", eventId=ev["id"], body=ev).execute()

        when = ""
        if new_start_iso:
            when = f" para {_dt.datetime.fromisoformat(new_start_iso).strftime('%d/%m às %H:%M')}"
        return f"Evento '{ev.get('summary', query)}' atualizado{when}."
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Não consegui atualizar o evento: {e}"


def list_upcoming_events(max_results: int = 10, days_ahead: int = 7) -> str:
    """Lista os próximos eventos do calendário."""
    try:
        service  = _get_service()
        now      = _dt.datetime.utcnow().isoformat() + "Z"
        time_max = (_dt.datetime.utcnow() + _dt.timedelta(days=days_ahead)).isoformat() + "Z"

        result = service.events().list(
            calendarId="primary", timeMin=now, timeMax=time_max,
            maxResults=max_results, singleEvents=True, orderBy="startTime",
        ).execute()
        events = result.get("items", [])

        if not events:
            return "Nenhum evento agendado nos próximos dias."

        lines = []
        for ev in events:
            start = ev["start"].get("dateTime", ev["start"].get("date"))
            try:
                dt = _dt.datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone()
                when = dt.strftime("%d/%m às %H:%M")
            except ValueError:
                when = start
            lines.append(f"{ev.get('summary', '(sem título)')} — {when}")

        return "Próximos eventos:\n" + "\n".join(lines)
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Não consegui consultar a agenda: {e}"


def get_due_soon_events(minutes_ahead: int = 15) -> list[dict]:
    """Retorna eventos que começam dentro de `minutes_ahead` minutos (para alertas proativos)."""
    try:
        service  = _get_service()
        now      = _dt.datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + _dt.timedelta(minutes=minutes_ahead)).isoformat() + "Z"

        result = service.events().list(
            calendarId="primary", timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy="startTime",
        ).execute()
        return result.get("items", [])
    except Exception:
        return []


def get_next_event() -> dict | None:
    """Retorna {summary, start_iso} do próximo evento futuro, para exibição no HUD."""
    try:
        service = _get_service()
        now     = _dt.datetime.now(_TZ)

        result = service.events().list(
            calendarId="primary", timeMin=now.isoformat(),
            maxResults=1, singleEvents=True, orderBy="startTime",
        ).execute()
        events = result.get("items", [])
        if not events:
            return None

        ev    = events[0]
        start = ev["start"].get("dateTime")
        if not start:
            return None
        return {"summary": ev.get("summary", "(sem título)"), "start_iso": start}
    except Exception:
        return None
