from __future__ import annotations

import requests

from tools import get_datetime, get_weather


def get_quotes() -> str:
    """Cotações de câmbio e cripto via AwesomeAPI (gratuita, sem chave)."""
    try:
        r = requests.get(
            "https://economia.awesomeapi.com.br/json/last/USD-BRL,EUR-BRL,BTC-USD",
            timeout=5,
        )
        r.raise_for_status()
        d = r.json()
        usd = float(d["USDBRL"]["bid"])
        eur = float(d["EURBRL"]["bid"])
        btc = float(d["BTCUSD"]["bid"])
        return f"Dólar: R$ {usd:.2f} | Euro: R$ {eur:.2f} | Bitcoin: US$ {btc:,.0f}"
    except Exception:
        return "Cotações indisponíveis."


def morning_report() -> str:
    """Monta o briefing matinal com data, clima e cotações."""
    sections = [
        ("Data e hora", get_datetime()),
        ("Clima",       get_weather()),
        ("Mercado",     get_quotes()),
    ]
    lines = []
    for title, content in sections:
        lines.append(f"[{title}] {content}")
    return "\n".join(lines)
