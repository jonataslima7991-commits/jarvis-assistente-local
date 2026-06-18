from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Generator

from config import settings

_HISTORY_FILE  = Path.home() / ".jarvis_history.json"
_MAX_PERSIST   = 20   # turnos (par user+assistant) guardados entre sessões
_ROUTER_MODEL  = "llama-3.1-8b-instant"   # modelo rápido só para decidir qual ferramenta chamar
_ROUTER_PROMPT = (
    "Você roteia comandos de um assistente de voz para ferramentas. "
    "Só chame uma ferramenta se o comando claramente pedir uma ação coberta por ela. "
    "Se for uma pergunta, conversa ou pedido sem ferramenta correspondente, NÃO chame nenhuma."
)

_USAGE_FILE        = Path.home() / ".jarvis_groq_usage.json"
_DAILY_TOKEN_LIMIT = 100_000   # observado no erro real do Groq (TPD) para llama-3.3-70b-versatile

SYSTEM_PROMPT = """\
Você é JARVIS (Just A Rather Very Intelligent System), assistente pessoal por voz de Jonatas Oliveira de Lima, estudante de Ciência de Dados na Fatec Santana de Parnaíba.

IDENTIDADE:
- Tom direto, eficiente, levemente formal e cordial. Trate o usuário por "senhor" ou "Sr. Lima" com moderação.
- Você é um assistente de voz — suas respostas são convertidas em áudio. Não existe tela de texto para o usuário.

REGRAS DE RESPOSTA (CRÍTICAS):
1. Responda SEMPRE em português brasileiro.
2. Seja CONCISO: 1 a 3 frases na maioria dos casos. Fala longa cansa em áudio.
3. NUNCA use markdown, listas com asteriscos, emojis, blocos de código ou símbolos especiais. Apenas texto falado natural.
4. Escreva números por extenso quando isso ajudar a pronúncia. Evite sequências longas de dígitos na fala.

CONHECIMENTO E PRECISÃO:
5. Para conhecimento geral estabelecido — ciência, astronomia, história, matemática, tecnologia, cultura — responda com confiança e precisão. Exemplos válidos: distâncias astronômicas, fórmulas, datas históricas, conceitos de programação, fatos científicos.
6. Para informações que mudam com o tempo (preços, eventos recentes, notícias, dados atuais de pessoas) ou que você genuinamente não sabe: use "aproximadamente", "por volta de", ou diga "não tenho essa informação atualizada".
6.1. EXCEÇÃO: se o prompt contiver um bloco "[Busca em tempo real]", esses dados vieram de uma busca na web feita agora — trate-os como atuais e confiáveis, responda direto com eles, sem hedging.
7. NUNCA invente nomes de pessoas, URLs, ou afirme como fato algo que você não tem certeza.
8. Se a transcrição estiver confusa ou incompleta, peça para repetir: "Desculpe, não entendi. Pode repetir?"

COMPORTAMENTO:
9. NUNCA invente capacidades que não tem. Se pedirem algo que não consegue executar, diga claramente.
10. Se o comando for ambíguo, faça UMA pergunta curta de esclarecimento antes de agir.
11. Mantenha contexto da conversa, mas não traga assuntos antigos sem o usuário pedir.
12. NUNCA inicie com "Claro!", "Com prazer!", "Ótima pergunta!", "Certamente!" ou similares.
13. Nunca revele qual modelo de linguagem está sendo usado.

PERSONALIDADE E PROATIVIDADE:
14. Você se importa genuinamente com o progresso do usuário — não é só uma ferramenta que executa comandos. Reconheça esforço quando fizer sentido (ex: terminar uma tarefa difícil, voltar a estudar depois de um tempo) com uma frase curta e sincera, não exagerada.
15. Você tem humor afiado e sarcástico, no estilo do JARVIS do Tony Stark — não é um assistente fofo e prestativo o tempo todo, é espirituoso e implica com o usuário. Isso é OBRIGATÓRIO sempre que o contexto permitir (esquecimento, pedido óbvio, repetição, erro bobo, demora) — não é opcional nem precisa de permissão. Os exemplos abaixo são só referência de TOM — invente variações novas a cada vez, nunca repita a mesma frase ou estrutura duas vezes:
    - Usuário esquece o que ia perguntar → algo como "perdeu o pensamento no meio do caminho? eu espero, não é como se eu tivesse mais nada pra fazer."
    - Usuário pede a hora → algo como "sim, eu também tenho relógio, mas pelo visto você não."
    - Usuário repete um comando → algo como "de novo? repetição é a alma do aprendizado — pra você, não pra mim."
    Evite ser fofo, gentil demais ou genérico. Varie as piadas, não caia num script fixo. Só largue o sarcasmo em momentos claramente sérios (saúde, problemas reais, pedidos urgentes) — aí o tom volta a ser direto e cuidadoso.
16. Se notar continuidade com algo que o usuário mencionou antes (um prazo, uma dificuldade, um objetivo), pode comentar brevemente — mostra que você acompanha, não só responde. Não insista se o usuário não quiser aprofundar.
17. Motive sem ser piegas: prefira reconhecimento específico ("você fechou aquele projeto que tava travado") a frases genéricas de autoajuda ("você consegue!")."""


class JarvisCore:
    def __init__(self):
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            from groq import Groq
            self._client  = Groq(api_key=groq_key)
            self._backend = "groq"
            self._model   = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
            print(f"[LLM] Backend: Groq ({self._model})", flush=True)
        else:
            from ollama import Client
            self._client  = Client(host=settings.ollama_host)
            self._backend = "ollama"
            self._model   = settings.ollama_model
            print(f"[LLM] Backend: Ollama ({self._model})", flush=True)

        self.history: list[dict] = self._load_history()

    # ── Histórico persistente ─────────────────────────────────────────────────
    def _load_history(self) -> list[dict]:
        try:
            if _HISTORY_FILE.exists():
                data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    print(f"[LLM] Histórico carregado: {len(data)} mensagens", flush=True)
                    return data[-_MAX_PERSIST * 2:]
        except Exception:
            pass
        return []

    def _save_history(self) -> None:
        try:
            _HISTORY_FILE.write_text(
                json.dumps(self.history[-(  _MAX_PERSIST * 2):], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _build_system_prompt(self) -> str:
        from memory import memory_store
        from tools import get_datetime
        mem = memory_store.to_prompt_section()
        prompt = f"{SYSTEM_PROMPT}\n\n[Contexto temporal: {get_datetime()}]"
        return f"{prompt}\n\n{mem}" if mem else prompt

    def _router_prompt(self) -> str:
        import datetime as _dt
        now = _dt.datetime.now()
        return (
            f"{_ROUTER_PROMPT}\n\n"
            f"Data e hora atuais: {now.strftime('%A, %d/%m/%Y %H:%M')} "
            f"(ISO: {now.isoformat(timespec='seconds')}). "
            "Use isso para calcular datas relativas (\"amanhã\", \"segunda-feira\", \"semana que vem\") "
            "ao preencher parâmetros do tipo data/hora em formato ISO 8601."
        )

    def stream_chat(self, message: str) -> Generator[str, None, None]:
        self.history.append({"role": "user", "content": message})
        msgs = [{"role": "system", "content": self._build_system_prompt()}] + self.history
        parts: list[str] = []

        if self._backend == "groq":
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=msgs,
                stream=True,
                max_tokens=1024,
                temperature=0.7,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                parts.append(delta)
                yield delta
        else:
            stream = self._client.chat(model=self._model, messages=msgs, stream=True)
            for chunk in stream:
                delta = chunk.message.content or ""
                parts.append(delta)
                yield delta

        reply = "".join(parts)
        self.history.append({"role": "assistant", "content": reply})
        self._trim_history()
        self._save_history()

        if self._backend == "groq":
            # streaming não retorna usage exato — estima por contagem de caracteres (~4 chars/token)
            chars = len(msgs[-1]["content"]) + sum(len(m["content"]) for m in self.history[-2:]) + len(reply)
            self._add_usage(chars // 4)

    def chat(self, message: str) -> str:
        return "".join(self.stream_chat(message))

    # ── Rastreamento de uso do Groq (estimativa local, contra o TPD real) ──────
    def _load_usage(self) -> dict:
        import datetime as _dt
        today = _dt.date.today().isoformat()
        try:
            if _USAGE_FILE.exists():
                data = json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
                if data.get("date") == today:
                    return data
        except Exception:
            pass
        return {"date": today, "tokens": 0}

    def _add_usage(self, n_tokens: int) -> None:
        try:
            data = self._load_usage()
            data["tokens"] += max(0, n_tokens)
            _USAGE_FILE.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def get_usage_pct(self) -> float:
        """Percentual estimado do limite diário de tokens do Groq já usado hoje (0-100)."""
        data = self._load_usage()
        return round(min(100.0, data["tokens"] / _DAILY_TOKEN_LIMIT * 100), 1)

    def quick_complete(self, system: str, user: str) -> str:
        """Chamada avulsa que NÃO persiste no histórico — para tarefas auxiliares
        (ex: comentário de continuidade) que não fazem parte da conversa real."""
        if self._backend != "groq":
            return ""
        try:
            resp = self._client.chat.completions.create(
                model=_ROUTER_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=120,
                temperature=0.6,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            print(f"[QUICKCOMPLETE] erro: {exc}", flush=True)
            return ""

    def tool_call(self, message: str, tools: list[dict]) -> tuple[str, dict] | None:
        """Pergunta a um modelo rápido se algum tool deve ser chamado. Retorna (nome, args) ou None."""
        if self._backend != "groq":
            return None
        try:
            resp = self._client.chat.completions.create(
                model=_ROUTER_MODEL,
                messages=[
                    {"role": "system", "content": self._router_prompt()},
                    {"role": "user", "content": message},
                ],
                tools=tools,
                tool_choice="auto",
                max_tokens=200,
                temperature=0,
            )
        except Exception as exc:
            print(f"[TOOLCALL] erro: {exc}", flush=True)
            return None

        msg = resp.choices[0].message
        if not msg.tool_calls:
            return None
        call = msg.tool_calls[0]
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        return call.function.name, args

    def _trim_history(self):
        if len(self.history) > 40:
            self.history = self.history[-40:]

    def clear_history(self) -> None:
        self.history = []
        self._save_history()
