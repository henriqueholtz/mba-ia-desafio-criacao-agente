"""Comando de restauração: ``uv run python -m app.restore``.

Apaga reservas e visitantes gravados pelo assistente e recarrega
exatamente o conteúdo de dados/reservas.json e dados/visitantes.json.
Não altera as sessões de conversa (elas continuam existindo).
"""

from app.storage.db import restore_db


def main() -> None:
    restore_db()
    print("Dados de reservas e visitantes restaurados a partir de dados/.")


if __name__ == "__main__":
    main()
