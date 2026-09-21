"""Único ponto de leitura do apartamento da sessão (Garantia 2).

Toda tool que precisa saber "de quem é essa conversa" chama
``apartamento_da_sessao`` em vez de aceitar um parâmetro "apartamento" vindo
do modelo. O valor é lido do ``state`` da sessão do ADK, que é escrito uma
única vez em ``POST /sessoes`` (veja ``app/runner_service.py``) e nunca mais
alterado. Não existe nenhum caminho de código em que uma mensagem do morador
consiga trocar esse valor: mesmo que o modelo decida (por erro ou por texto
malicioso do morador) chamar uma tool "como se fosse" outro apartamento, a
tool ignora qualquer coisa que o modelo tenha inferido e usa só este valor.
"""

from __future__ import annotations

from google.adk.tools.tool_context import ToolContext

APARTAMENTO_STATE_KEY = "apartamento"


def apartamento_da_sessao(tool_context: ToolContext) -> str:
    apartamento = tool_context.state.get(APARTAMENTO_STATE_KEY)
    if not apartamento:
        raise RuntimeError(
            "Sessão sem apartamento associado: isso indica um bug na criação"
            " da sessão, nunca deveria acontecer em produção."
        )
    return str(apartamento)
