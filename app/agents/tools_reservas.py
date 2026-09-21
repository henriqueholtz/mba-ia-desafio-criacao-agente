"""Tools do especialista em reservas.

Regra de negócio 1 e Garantia 5: a exclusividade "uma reserva por área e
data" é decidida por ``app.storage.db.criar_reserva``, no instante da
gravação (índice único do SQLite), nunca por uma checagem feita aqui antes de
chamar o banco.

Regra de negócio 2 e Garantia 1: ``criar_reserva`` só pede confirmação
(``require_confirmation``) quando a área tem taxa maior que zero — decidido
por ``_area_tem_taxa``, que olha o catálogo de áreas, não o que o modelo diz.
"""

from __future__ import annotations

from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app.agents.apartamento import apartamento_da_sessao
from app.storage import catalogo, db


def listar_areas_comuns() -> list[dict]:
    """Lista as áreas comuns do condomínio disponíveis para reserva, com a taxa de cada uma."""
    return [
        {"area": a.id, "nome": a.nome, "taxa": a.taxa} for a in catalogo.listar_areas()
    ]


def verificar_disponibilidade(area: str, data: str) -> dict:
    """Verifica se uma área comum está livre em uma data (AAAA-MM-DD).

    Retorna apenas se a data está livre ou ocupada. Nunca revela de qual
    apartamento é a reserva quando a área está ocupada.
    """
    area_info = catalogo.resolver_area(area)
    if area_info is None:
        return {"erro": f"Área '{area}' não existe."}
    return {"livre": db.area_esta_livre(area_info.id, data)}


def listar_minhas_reservas(tool_context: ToolContext) -> list[dict]:
    """Lista as reservas ativas do apartamento da sessão atual."""
    apartamento = apartamento_da_sessao(tool_context)
    return db.listar_reservas_do_apartamento(apartamento)


def _area_tem_taxa(area: str, **_kwargs) -> bool:
    area_info = catalogo.resolver_area(area)
    return area_info is not None and area_info.taxa > 0


def criar_reserva(area: str, data: str, tool_context: ToolContext) -> dict:
    """Reserva uma área comum (salão de festas, churrasqueira ou quadra) em uma data (AAAA-MM-DD) para o apartamento da sessão atual.

    Quando a área tem taxa, esta ação só é executada depois de confirmação do
    morador pela rota de confirmações da API — isso é decidido pelo
    framework antes desta função rodar, não por código aqui dentro.
    """
    apartamento = apartamento_da_sessao(tool_context)
    area_info = catalogo.resolver_area(area)
    if area_info is None:
        return {"reservada": False, "motivo": f"Área '{area}' não existe."}

    codigo = db.criar_reserva(apartamento=apartamento, area=area_info.id, data=data)
    if codigo is None:
        return {
            "reservada": False,
            "motivo": "Essa área já está reservada nessa data.",
        }
    return {
        "reservada": True,
        "codigo": codigo,
        "area": area_info.id,
        "data": data,
        "taxa": area_info.taxa,
    }


def cancelar_reserva(area: str, data: str, tool_context: ToolContext) -> dict:
    """Cancela a reserva ativa do apartamento da sessão atual para uma área/data (AAAA-MM-DD).

    Só cancela reservas do próprio apartamento da sessão; nunca precisa de
    confirmação, pois cancelar não gera cobrança nem libera acesso.
    """
    apartamento = apartamento_da_sessao(tool_context)
    area_info = catalogo.resolver_area(area)
    if area_info is None:
        return {"cancelada": False, "motivo": f"Área '{area}' não existe."}
    codigo = db.cancelar_reserva(apartamento=apartamento, area=area_info.id, data=data)
    if codigo is None:
        return {
            "cancelada": False,
            "motivo": "Não foi encontrada uma reserva ativa sua para essa área e data.",
        }
    return {"cancelada": True, "codigo": codigo}


def build_reservas_tools() -> list:
    return [
        FunctionTool(listar_areas_comuns),
        FunctionTool(verificar_disponibilidade),
        FunctionTool(listar_minhas_reservas),
        FunctionTool(criar_reserva, require_confirmation=_area_tem_taxa),
        FunctionTool(cancelar_reserva),
    ]
