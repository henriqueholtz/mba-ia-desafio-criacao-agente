"""Camada que liga a API HTTP ao Runner do ADK.

Concentra as três garantias que dependem diretamente do runtime do ADK:

- Garantia 1 (confirmação): ``confirmacoes_pendentes`` é sempre calculada
  lendo os eventos reais da sessão (``_confirmacoes_pendentes``), nunca o que
  o modelo diz em texto. ``responder_confirmacao`` só resolve um `id` que
  aparece nessa lista; qualquer outro id vira ``ConfirmacaoNaoPendente``
  (409), e o Runner só é acionado depois dessa checagem.
- Garantia 2 (sessão pertence a um apartamento): ``criar_sessao`` grava o
  apartamento uma única vez no ``state`` da sessão do ADK. Nada aqui nem nas
  tools aceita um apartamento diferente depois disso.
- Garantia 3 (nada se perde no reinício): o `session_service` é o
  `DatabaseSessionService` (SQLite), construído uma vez neste módulo; todas
  as sessões e eventos são lidos de volta do arquivo em disco, nunca de
  memória do processo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from app.agents.apartamento import APARTAMENTO_STATE_KEY
from app.agents.root_agent import build_app
from app.config import APP_NAME, SESSIONS_DB_URL

logger = logging.getLogger(__name__)

REQUEST_CONFIRMATION_NAME = "adk_request_confirmation"

# Todas as sessões do ADK vivem sob o mesmo "usuário" lógico: quem identifica
# o morador é o apartamento gravado no state da sessão (Garantia 2), não o
# user_id do ADK. Usar um único user_id fixo permite localizar qualquer
# sessão só pelo session_id, como o contrato da API exige.
ADK_USER_ID = "residencial-aurora"


class SessaoNaoEncontrada(Exception):
    pass


class ConfirmacaoNaoPendente(Exception):
    pass


@dataclass
class ResultadoTurno:
    resposta: str
    confirmacoes_pendentes: list[dict[str, Any]] = field(default_factory=list)


class RunnerService:
    def __init__(self) -> None:
        self.session_service = DatabaseSessionService(db_url=SESSIONS_DB_URL)
        self.app = build_app()
        self.runner = Runner(app=self.app, session_service=self.session_service)

    async def criar_sessao(self, apartamento: str) -> str:
        session = await self.session_service.create_session(
            app_name=APP_NAME,
            user_id=ADK_USER_ID,
            state={APARTAMENTO_STATE_KEY: apartamento},
        )
        return session.id

    async def _obter_sessao(self, session_id: str):
        session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id
        )
        if session is None:
            raise SessaoNaoEncontrada(session_id)
        return session

    async def listar_eventos(self, session_id: str) -> list[dict]:
        session = await self._obter_sessao(session_id)
        return [
            event.model_dump(mode="json", exclude_none=True)
            for event in session.events
        ]

    async def enviar_mensagem(self, session_id: str, texto: str) -> ResultadoTurno:
        await self._obter_sessao(session_id)
        content = types.Content(role="user", parts=[types.Part(text=texto)])
        return await self._rodar_turno(session_id, content)

    async def responder_confirmacao(
        self, session_id: str, confirmacao_id: str, confirmado: bool
    ) -> ResultadoTurno:
        session = await self._obter_sessao(session_id)
        pendentes = _confirmacoes_pendentes(session.events)
        if not any(p["id"] == confirmacao_id for p in pendentes):
            raise ConfirmacaoNaoPendente(confirmacao_id)

        content = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=confirmacao_id,
                        name=REQUEST_CONFIRMATION_NAME,
                        response={"confirmed": confirmado},
                    )
                )
            ],
        )
        return await self._rodar_turno(session_id, content)

    async def _rodar_turno(self, session_id: str, content: types.Content) -> ResultadoTurno:
        eventos_do_turno = []
        try:
            async for event in self.runner.run_async(
                user_id=ADK_USER_ID, session_id=session_id, new_message=content
            ):
                eventos_do_turno.append(event)
        except Exception:
            # O Runner grava cada evento na sessão assim que ele é produzido,
            # antes de seguir para o próximo passo (ver
            # `google.adk.runners.Runner.append_event`). Uma falha do
            # provedor do modelo (rede, limite de taxa) pode acontecer DEPOIS
            # que a tool já rodou e seu resultado já foi persistido — por
            # exemplo, na chamada que resumiria a resposta em texto. Por
            # isso, em vez de estourar um 500 escondendo uma ação que já
            # aconteceu de verdade, recarregamos a sessão e respondemos com o
            # estado real e já gravado.
            logger.exception(
                "Falha do modelo durante o turno da sessão %s; respondendo"
                " com o estado já persistido.",
                session_id,
            )

        session = await self._obter_sessao(session_id)
        resposta = _texto_final(eventos_do_turno)
        pendentes = _confirmacoes_pendentes(session.events)
        return ResultadoTurno(resposta=resposta, confirmacoes_pendentes=pendentes)


def _texto_final(eventos: list) -> str:
    partes = []
    for event in eventos:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.text:
                partes.append(part.text)
    return "".join(partes).strip()


def _confirmacoes_pendentes(eventos: list) -> list[dict[str, Any]]:
    """Lê os eventos e devolve as confirmações ainda sem resposta.

    Uma confirmação é a chamada de função sintética ``adk_request_confirmation``
    que o ADK gera quando uma tool com ``require_confirmation`` é chamada
    (ver ``app/agents/tools_reservas.py`` e ``tools_visitantes.py``). Ela está
    pendente até existir, em qualquer evento posterior, uma
    ``function_response`` com o mesmo id — que é exatamente o que
    ``responder_confirmacao`` grava ao aprovar ou negar.
    """
    respondidas: set[str] = set()
    for event in eventos:
        for fr in event.get_function_responses():
            if fr.id:
                respondidas.add(fr.id)

    pendentes: dict[str, dict[str, Any]] = {}
    for event in eventos:
        for fc in event.get_function_calls():
            if fc.name != REQUEST_CONFIRMATION_NAME or not fc.id:
                continue
            if fc.id in respondidas:
                pendentes.pop(fc.id, None)
                continue
            original = (fc.args or {}).get("originalFunctionCall") or {}
            pendentes[fc.id] = {
                "id": fc.id,
                "acao": original.get("name") or "",
                "detalhes": original.get("args") or {},
            }
    return list(pendentes.values())


_service: RunnerService | None = None


def get_runner_service() -> RunnerService:
    global _service
    if _service is None:
        _service = RunnerService()
    return _service
