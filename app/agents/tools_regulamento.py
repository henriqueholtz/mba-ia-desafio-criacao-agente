"""Tool do especialista em regulamento (Garantia 4).

``consultar_regulamento`` devolve o texto de UM único capítulo — o mais
relevante para a pergunta, escolhido por sobreposição de palavras-chave em
``app.storage.regulamento.buscar_capitulo``. É essa string, e só ela, que
aparece como resultado de tool nos eventos da sessão: nunca o documento
inteiro, nunca capítulos que não têm relação com a pergunta.
"""

from __future__ import annotations

from google.adk.tools.function_tool import FunctionTool

from app.storage import regulamento


def consultar_regulamento(pergunta: str) -> dict:
    """Busca no regulamento interno do condomínio o capítulo mais relevante para a pergunta do morador e devolve o texto desse capítulo."""
    capitulo = regulamento.buscar_capitulo(pergunta)
    return {"capitulo": capitulo.titulo, "texto": capitulo.texto}


def build_regulamento_tools() -> list:
    return [FunctionTool(consultar_regulamento)]
