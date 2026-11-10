"""MODEL: tabelas SQLAlchemy, um arquivo por agregado.

Importar tudo aqui registra as tabelas em `Base.metadata` (o Alembic importa este pacote).
"""

from confere_api.models import (  # noqa: F401
    casamento,
    codigo_custo,
    documento,
    empresa,
    evento,
    excecao,
    fornecedor,
    global_,
    job,
    linha_embedding,
    processo,
    provisao,
    sinonimo,
)
