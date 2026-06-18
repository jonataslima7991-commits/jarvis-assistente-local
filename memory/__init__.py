from __future__ import annotations

import json
from pathlib import Path

_MEM_FILE = Path.home() / ".jarvis_memory.json"


class MemoryStore:
    """Persiste fatos que o usuário pede para JARVIS lembrar entre sessões."""

    def __init__(self) -> None:
        self._facts: list[str] = self._load()

    def _load(self) -> list[str]:
        try:
            if _MEM_FILE.exists():
                data = json.loads(_MEM_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [str(f) for f in data]
        except Exception:
            pass
        return []

    def _save(self) -> None:
        try:
            _MEM_FILE.write_text(
                json.dumps(self._facts, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def remember(self, fact: str) -> None:
        fact = fact.strip(" .!?,")
        if fact and fact not in self._facts:
            self._facts.append(fact)
            self._save()

    def clear(self) -> None:
        self._facts = []
        self._save()

    def forget(self, query: str) -> int:
        """Remove fatos que contenham o texto do query. Retorna quantos foram removidos."""
        q = query.strip().lower()
        before = len(self._facts)
        self._facts = [f for f in self._facts if q not in f.lower()]
        removed = before - len(self._facts)
        if removed:
            self._save()
        return removed

    def list_all(self) -> str:
        if not self._facts:
            return "Não tenho nenhuma memória salva, senhor."
        items = "; ".join(self._facts)
        return f"Lembro de: {items}."

    def to_prompt_section(self) -> str:
        if not self._facts:
            return ""
        lines = ["[Fatos que o Sr. Lima pediu para lembrar]"]
        for f in self._facts:
            lines.append(f"- {f}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._facts)


memory_store = MemoryStore()
