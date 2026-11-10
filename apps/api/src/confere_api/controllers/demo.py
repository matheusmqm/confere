"""CONTROLLER: reset do estado da demo (CF-114).

Apaga SÓ os dados transacionais da empresa do tenant. O mundo (processos, fornecedores, catálogo)
é estável e não é recriado. Provisões voltam para `aberta`.
"""

from sqlalchemy import delete, update

from confere_api.controllers.base import RepositorioBase
from confere_api.models.casamento import Casamento
from confere_api.models.documento import Documento, Linha
from confere_api.models.evento import Evento, LLMCall
from confere_api.models.excecao import Decisao, Excecao
from confere_api.models.job import Job
from confere_api.models.linha_embedding import LinhaEmbedding
from confere_api.models.processo import ProcessoReferencia
from confere_api.models.provisao import Provisao
from confere_api.models.sinonimo import SinonimoCusto
from confere_api.storage import Storage


class DemoController(RepositorioBase):
    def resetar(self, storage: Storage | None = None, *, limpar_arquivos: bool = False) -> None:
        """A transação é de quem chama. Com `limpar_arquivos`, apaga `<empresa_id>/` do storage."""
        empresa = self.tenant.empresa_id
        apagar = (
            (Decisao, None),
            (Excecao, None),
            (Casamento, None),
            (Evento, None),
            (LLMCall, None),
            (LinhaEmbedding, LinhaEmbedding.origem.in_(("linha", "correcao"))),
            (Job, None),
            (Linha, None),
            (Documento, None),
            (SinonimoCusto, SinonimoCusto.origem == "correcao"),
            (ProcessoReferencia, ProcessoReferencia.origem == "correcao"),
        )
        for modelo, filtro in apagar:
            comando = delete(modelo).where(modelo.empresa_id == empresa)
            if filtro is not None:
                comando = comando.where(filtro)
            self.db.execute(comando)
        self.db.execute(
            update(Provisao)
            .where(Provisao.empresa_id == empresa, Provisao.status != "aberta")
            .values(status="aberta")
        )
        self.db.flush()
        if limpar_arquivos and storage is not None:
            storage.delete_prefix(f"{empresa}/")
