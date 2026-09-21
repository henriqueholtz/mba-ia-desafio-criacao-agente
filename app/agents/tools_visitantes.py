"""Tools do especialista em visitantes.

Regra de negócio 3 e Garantia 1: autorizar visitante sempre libera acesso,
então ``autorizar_visitante`` sempre exige confirmação
(``require_confirmation=True``), mesmo que o morador diga no texto que "já
confirmou". A confirmação real só chega pela rota de confirmações da API; o
framework não roda o corpo desta função antes disso.
"""

from __future__ import annotations

from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app.agents.apartamento import apartamento_da_sessao
from app.storage import db


def listar_meus_visitantes(tool_context: ToolContext) -> list[dict]:
    """Lista os visitantes autorizados para o apartamento da sessão atual."""
    apartamento = apartamento_da_sessao(tool_context)
    return db.listar_visitantes_do_apartamento(apartamento)


def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict:
    """Autoriza a entrada de um visitante em uma data (AAAA-MM-DD) para o apartamento da sessão atual.

    Sempre pede confirmação do morador antes de liberar o acesso, mesmo que a
    mensagem diga o contrário.
    """
    apartamento = apartamento_da_sessao(tool_context)
    db.autorizar_visitante(apartamento=apartamento, nome=nome, data=data)
    return {"autorizado": True, "nome": nome, "data": data}


def build_visitantes_tools() -> list:
    return [
        FunctionTool(listar_meus_visitantes),
        FunctionTool(autorizar_visitante, require_confirmation=True),
    ]
