from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


class SolicitarIn(BaseModel):
    email: EmailStr


class VerificarIn(BaseModel):
    email: EmailStr
    codigo: str = Field(min_length=6, max_length=6)
    dispositivo: str = "Dispositivo"


class PerfilIn(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=80)
    config: Optional[dict] = None


CLASSES_CONTA = Literal["corrente", "poupanca", "dinheiro", "investimento", "terceiros", "beneficio"]


class TipoContaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    classe: CLASSES_CONTA = "corrente"


class TipoContaPatch(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=60)
    classe: Optional[CLASSES_CONTA] = None
    inativo: Optional[bool] = None


class RecargaIn(BaseModel):
    valor_centavos: int = Field(gt=0)
    dia_mes: int = Field(ge=1, le=31)
    ativa: bool = True


class ContaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    tipo: CLASSES_CONTA = "corrente"      # usado só quando tipo_conta_id não é informado
    tipo_conta_id: Optional[UUID] = None
    recarga_valor_centavos: Optional[int] = Field(default=None, gt=0)
    recarga_dia: Optional[int] = Field(default=None, ge=1, le=31)
    saldo_inicial_centavos: int = 0
    data_saldo_inicial: Optional[date] = None


class ContaPatch(BaseModel):
    nome: Optional[str] = None
    tipo_conta_id: Optional[UUID] = None
    saldo_inicial_centavos: Optional[int] = None
    data_saldo_inicial: Optional[date] = None
    inativa: Optional[bool] = None


class ConviteContaIn(BaseModel):
    email: EmailStr
    papel: Literal["leitor", "editor", "gestor"] = "editor"


class ConvitePortadorIn(BaseModel):
    email: EmailStr


class CategoriaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    pai_id: Optional[UUID] = None                      # sem pai = novo grupo (então `tipo` é obrigatório)
    tipo: Optional[Literal["receita", "despesa"]] = None


class CategoriaPatch(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=80)
    ativa: Optional[bool] = None
    pai_id: Optional[UUID] = None                      # mover para outro grupo do mesmo tipo


class MesclarIn(BaseModel):
    destino_id: UUID


class OrcamentoItem(BaseModel):
    categoria_id: UUID
    valor_centavos: int = Field(ge=0)
    # vigência: sem `modo`/`mes` = padrão de todos os meses (compatível com a versão anterior); `mes` = ajuste de um mês
    mes: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    modo: Optional[Literal["continuo", "ocorrencias", "meses", "mes"]] = None
    inicio: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    fim: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    ocorrencias: Optional[int] = Field(default=None, ge=1, le=240)
    meses: Optional[list[int]] = Field(default=None, min_length=1, max_length=12)

    @model_validator(mode="after")
    def _coerente(self):
        if self.mes:
            self.modo, self.inicio = "mes", self.mes
        if self.modo is None:
            self.modo = "continuo"
        if self.modo == "mes" and not self.inicio:
            raise ValueError("informe o mês")
        if self.modo == "ocorrencias" and not self.ocorrencias:
            raise ValueError("informe o número de ocorrências")
        if self.modo == "meses":
            if not self.meses or any(m < 1 or m > 12 for m in self.meses):
                raise ValueError("informe os meses do ano (1 a 12)")
            self.meses = sorted(set(self.meses))
        if self.fim and self.modo not in ("continuo", "meses"):
            raise ValueError("término só vale para 'sem término' e 'meses do ano'")
        if self.fim and self.inicio and self.fim < self.inicio:
            raise ValueError("o término é anterior ao início")
        return self


class OrcamentoIn(BaseModel):
    itens: list[OrcamentoItem] = Field(min_length=1, max_length=300)


class FavorecidoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    dono_id: Optional[UUID] = None
    categoria_padrao_id: Optional[UUID] = None


class CartaoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    bandeira: Optional[str] = None
    dia_fechamento: int = Field(ge=1, le=31)
    dia_vencimento: int = Field(ge=1, le=31)
    conta_pagamento_id: Optional[UUID] = None
    limite_centavos: Optional[int] = None
    final_principal: Optional[str] = Field(default=None, pattern=r"^\d{4}$")


class CartaoPatch(BaseModel):
    nome: Optional[str] = None
    bandeira: Optional[str] = None
    dia_fechamento: Optional[int] = Field(default=None, ge=1, le=31)
    dia_vencimento: Optional[int] = Field(default=None, ge=1, le=31)
    conta_pagamento_id: Optional[UUID] = None
    limite_centavos: Optional[int] = None
    inativo: Optional[bool] = None


class PlasticoIn(BaseModel):
    final: str = Field(pattern=r"^\d{4}$")
    rotulo: str = Field(min_length=1, max_length=60)
    tipo: Literal["plastico", "virtual"] = "plastico"


class PlasticoPatch(BaseModel):
    final: Optional[str] = Field(default=None, pattern=r"^\d{4}$")
    rotulo: Optional[str] = Field(default=None, min_length=1, max_length=60)
    tipo: Optional[Literal["plastico", "virtual"]] = None
    ativo: Optional[bool] = None
    principal: Optional[bool] = None


class PagarFaturaIn(BaseModel):
    conta_id: UUID
    data: Optional[date] = None
    valor_centavos: Optional[int] = Field(default=None, gt=0)


class TransacaoIn(BaseModel):
    tipo: Literal["despesa", "receita"]
    valor_centavos: int = Field(gt=0, description="valor absoluto em centavos; o sinal vem do tipo")
    data_competencia: date
    data_caixa: Optional[date] = None
    conta_id: Optional[UUID] = None
    plastico_id: Optional[UUID] = None
    categoria_id: Optional[UUID] = None
    favorecido_id: Optional[UUID] = None
    favorecido_nome: Optional[str] = None
    descricao: Optional[str] = Field(default=None, max_length=200)
    forma_pagamento: Optional[Literal["boleto", "debito_automatico", "debito", "pix", "ted", "dinheiro", "cheque", "cartao", "outro"]] = None
    estado: Literal["previsto", "confirmado"] = "confirmado"
    parcelas: int = Field(default=1, ge=1, le=60)
    competencia_parcelas: Literal["parcela", "compra"] = "parcela"   # só vale para compras parceladas no cartão
    origem: Literal["manual", "foto", "fatura", "recorrencia", "notificacao"] = "manual"
    anexo_id: Optional[UUID] = None


class TransacaoPatch(BaseModel):
    valor_centavos: Optional[int] = Field(default=None, gt=0)
    data_competencia: Optional[date] = None
    data_caixa: Optional[date] = None
    categoria_id: Optional[UUID] = None
    favorecido_id: Optional[UUID] = None
    favorecido_nome: Optional[str] = None
    descricao: Optional[str] = None
    forma_pagamento: Optional[str] = None
    estado: Optional[Literal["previsto", "confirmado"]] = None
    conta_id: Optional[UUID] = None


class TransferenciaIn(BaseModel):
    conta_origem_id: UUID
    conta_destino_id: UUID
    valor_centavos: int = Field(gt=0)
    data: date
    descricao: Optional[str] = None
    estado: Literal["previsto", "confirmado"] = "confirmado"


class RecorrenciaIn(BaseModel):
    tipo: Literal["despesa", "receita"]
    valor_centavos: int = Field(gt=0)
    dia_mes: int = Field(ge=1, le=31)
    conta_id: Optional[UUID] = None
    plastico_id: Optional[UUID] = None
    categoria_id: Optional[UUID] = None
    favorecido_id: Optional[UUID] = None
    favorecido_nome: Optional[str] = None
    descricao: Optional[str] = None
    forma_pagamento: Optional[str] = None
    inicio: Optional[date] = None
    fim: Optional[date] = None


class RecorrenciaPatch(BaseModel):
    valor_centavos: Optional[int] = Field(default=None, gt=0)
    dia_mes: Optional[int] = Field(default=None, ge=1, le=31)
    categoria_id: Optional[UUID] = None
    favorecido_id: Optional[UUID] = None
    favorecido_nome: Optional[str] = None
    descricao: Optional[str] = None
    forma_pagamento: Optional[str] = None
    ativa: Optional[bool] = None
    fim: Optional[date] = None              # última data em que a recorrência vale
    limpar_fim: bool = False                # volta a valer sem data final
    a_partir_de: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$")   # mês (AAAA-MM) em que a mudança começa; padrão: o mês atual


class GerarRecorrenciasIn(BaseModel):
    mes: str = Field(pattern=r"^\d{4}-\d{2}$")


class LinhaFaturaIn(BaseModel):
    acao: Literal["criar", "atualizar", "conferir", "ignorar"]
    transacao_id: Optional[UUID] = None             # lançamento do app que esta linha da fatura corresponde (atualizar/conferir)
    data: date
    descricao: str = Field(max_length=200)
    favorecido_id: Optional[UUID] = None
    favorecido_nome: Optional[str] = Field(default=None, max_length=120)
    categoria_id: Optional[UUID] = None
    plastico_id: Optional[UUID] = None
    valor_centavos: int = Field(gt=0, description="valor absoluto; use eh_credito para estornos")
    eh_credito: bool = False
    parcela_atual: int = Field(default=1, ge=1, le=60)
    parcelas_total: int = Field(default=1, ge=1, le=60)
    criar_futuras: bool = False        # cria também as parcelas seguintes, como previstas nas faturas dos meses seguintes


class ImportarFaturaIn(BaseModel):
    cartao_id: UUID
    vencimento: date
    linhas: list[LinhaFaturaIn] = Field(max_length=600)
