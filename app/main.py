"""API HTTP do assistente do Residencial Aurora (contrato no Challenge.md).

As rotas de conversa (``/sessoes/...``) passam pelo agente ADK. As rotas de
verificação (``/apartamentos/...``) leem o SQLite de reservas/visitantes
direto, sem passar pelo modelo — são o jeito do avaliador conferir o efeito
real de cada conversa.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.runner_service import (
    ConfirmacaoNaoPendente,
    ResultadoTurno,
    SessaoNaoEncontrada,
    get_runner_service,
)
from app.schemas import (
    CriarSessaoRequest,
    CriarSessaoResponse,
    EnviarMensagemRequest,
    MensagemResponse,
    ResponderConfirmacaoRequest,
)
from app.storage import db


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Assistente do Residencial Aurora", lifespan=_lifespan)


def _turno_para_resposta(turno: ResultadoTurno) -> MensagemResponse:
    return MensagemResponse(
        resposta=turno.resposta,
        confirmacoes_pendentes=turno.confirmacoes_pendentes,
    )


@app.post("/sessoes", response_model=CriarSessaoResponse, status_code=201)
async def criar_sessao(body: CriarSessaoRequest) -> CriarSessaoResponse:
    service = get_runner_service()
    session_id = await service.criar_sessao(body.apartamento)
    return CriarSessaoResponse(session_id=session_id)


@app.post("/sessoes/{session_id}/mensagens", response_model=MensagemResponse)
async def enviar_mensagem(session_id: str, body: EnviarMensagemRequest) -> MensagemResponse:
    service = get_runner_service()
    try:
        turno = await service.enviar_mensagem(session_id, body.texto)
    except SessaoNaoEncontrada:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    return _turno_para_resposta(turno)


@app.post("/sessoes/{session_id}/confirmacoes", response_model=MensagemResponse)
async def responder_confirmacao(
    session_id: str, body: ResponderConfirmacaoRequest
) -> MensagemResponse | JSONResponse:
    service = get_runner_service()
    try:
        turno = await service.responder_confirmacao(
            session_id, body.id, body.confirmado
        )
    except SessaoNaoEncontrada:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    except ConfirmacaoNaoPendente:
        return JSONResponse(
            status_code=409,
            content={
                "detail": (
                    "Não existe confirmação pendente com esse id nesta sessão."
                )
            },
        )
    return _turno_para_resposta(turno)


@app.get("/sessoes/{session_id}/eventos")
async def listar_eventos(session_id: str) -> list[dict]:
    service = get_runner_service()
    try:
        return await service.listar_eventos(session_id)
    except SessaoNaoEncontrada:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")


@app.get("/apartamentos/{numero}/reservas")
async def reservas_do_apartamento(numero: str) -> list[dict]:
    return db.listar_reservas_do_apartamento(numero)


@app.get("/apartamentos/{numero}/visitantes")
async def visitantes_do_apartamento(numero: str) -> list[dict]:
    return db.listar_visitantes_do_apartamento(numero)
