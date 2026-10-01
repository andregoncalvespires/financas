-- 001: esquema base. Valores sempre em centavos (bigint). Datas de competência e de caixa separadas.
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE usuario (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext UNIQUE NOT NULL,
  nome text NOT NULL,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dispositivo (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  nome text NOT NULL,
  criado_em timestamptz NOT NULL DEFAULT now(),
  ultimo_uso timestamptz NOT NULL DEFAULT now(),
  revogado_em timestamptz
);

CREATE TABLE otp (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext NOT NULL,
  codigo_hash text NOT NULL,
  ip text,
  criado_em timestamptz NOT NULL DEFAULT now(),
  expira_em timestamptz NOT NULL,
  tentativas int NOT NULL DEFAULT 0,
  usado_em timestamptz
);
CREATE INDEX otp_email_idx ON otp(email, criado_em DESC);

-- Kit padrão de categorias (global, somente leitura para o app). Cada usuário recebe uma cópia.
CREATE TABLE kit_categoria (
  codigo text PRIMARY KEY,
  grupo_codigo text NOT NULL,
  grupo_nome text NOT NULL,
  nome text NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('receita','despesa')),
  ordem int NOT NULL DEFAULT 0
);

CREATE TABLE categoria (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dono_id uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  pai_id uuid REFERENCES categoria(id) ON DELETE CASCADE,
  nome text NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('receita','despesa')),
  codigo_origem text,
  ativa boolean NOT NULL DEFAULT true,
  ordem int NOT NULL DEFAULT 0,
  criado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX categoria_dono_idx ON categoria(dono_id);
CREATE INDEX categoria_origem_idx ON categoria(dono_id, codigo_origem);

CREATE TABLE favorecido (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dono_id uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  nome text NOT NULL,
  nome_norm text NOT NULL,
  categoria_padrao_id uuid REFERENCES categoria(id) ON DELETE SET NULL,
  criado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (dono_id, nome_norm)
);

CREATE TABLE conta (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dono_id uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  nome text NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('corrente','poupanca','dinheiro','investimento','terceiros')),
  saldo_inicial_centavos bigint NOT NULL DEFAULT 0,
  data_saldo_inicial date NOT NULL DEFAULT current_date,
  inativa boolean NOT NULL DEFAULT false,
  criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE conta_acesso (
  conta_id uuid NOT NULL REFERENCES conta(id) ON DELETE CASCADE,
  usuario_id uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  papel text NOT NULL CHECK (papel IN ('leitor','editor','gestor')),
  concedido_por uuid REFERENCES usuario(id) ON DELETE SET NULL,
  criado_em timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (conta_id, usuario_id)
);

-- Cartão = contrato. Plástico = cartão físico/virtual (principal ou adicional) com portador opcional.
CREATE TABLE cartao (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dono_id uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  nome text NOT NULL,
  bandeira text,
  dia_fechamento smallint NOT NULL CHECK (dia_fechamento BETWEEN 1 AND 31),
  dia_vencimento smallint NOT NULL CHECK (dia_vencimento BETWEEN 1 AND 31),
  conta_pagamento_id uuid REFERENCES conta(id) ON DELETE SET NULL,
  limite_centavos bigint,
  inativo boolean NOT NULL DEFAULT false,
  criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE plastico (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cartao_id uuid NOT NULL REFERENCES cartao(id) ON DELETE CASCADE,
  final char(4) NOT NULL CHECK (final ~ '^[0-9]{4}$'),
  rotulo text NOT NULL,
  portador_id uuid REFERENCES usuario(id) ON DELETE SET NULL,
  principal boolean NOT NULL DEFAULT false,
  ativo boolean NOT NULL DEFAULT true,
  criado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (cartao_id, final)
);

CREATE TABLE fatura (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cartao_id uuid NOT NULL REFERENCES cartao(id) ON DELETE CASCADE,
  mes_referencia date NOT NULL,
  data_fechamento date NOT NULL,
  data_vencimento date NOT NULL,
  status text NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta','paga')),
  pagamento_transacao_id uuid,
  criado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (cartao_id, mes_referencia)
);

CREATE TABLE recorrencia (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  criado_por uuid NOT NULL REFERENCES usuario(id),
  conta_id uuid REFERENCES conta(id) ON DELETE CASCADE,
  plastico_id uuid REFERENCES plastico(id) ON DELETE CASCADE,
  tipo text NOT NULL CHECK (tipo IN ('despesa','receita')),
  valor_centavos bigint NOT NULL CHECK (valor_centavos > 0),
  dia_mes smallint NOT NULL CHECK (dia_mes BETWEEN 1 AND 31),
  forma_pagamento text,
  categoria_id uuid REFERENCES categoria(id) ON DELETE SET NULL,
  favorecido_id uuid REFERENCES favorecido(id) ON DELETE SET NULL,
  descricao text,
  inicio date NOT NULL DEFAULT current_date,
  fim date,
  ativa boolean NOT NULL DEFAULT true,
  criado_em timestamptz NOT NULL DEFAULT now(),
  CHECK ((conta_id IS NOT NULL) <> (plastico_id IS NOT NULL))
);

CREATE TABLE anexo (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  criado_por uuid NOT NULL REFERENCES usuario(id),
  caminho text NOT NULL,
  mime text NOT NULL,
  sha256 text NOT NULL,
  tamanho int NOT NULL,
  criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transacao (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  criado_por uuid NOT NULL REFERENCES usuario(id),
  tipo text NOT NULL CHECK (tipo IN ('despesa','receita','transferencia','pagamento_fatura')),
  estado text NOT NULL DEFAULT 'confirmado' CHECK (estado IN ('previsto','confirmado','conciliado')),
  valor_centavos bigint NOT NULL CHECK (valor_centavos <> 0),   -- negativo = saída
  data_competencia date NOT NULL,
  data_caixa date NOT NULL,
  data_compra date,
  conta_id uuid REFERENCES conta(id),
  plastico_id uuid REFERENCES plastico(id),
  fatura_id uuid REFERENCES fatura(id),
  forma_pagamento text CHECK (forma_pagamento IN ('boleto','debito_automatico','debito','pix','ted','dinheiro','cheque','cartao','outro')),
  categoria_id uuid REFERENCES categoria(id) ON DELETE SET NULL,
  favorecido_id uuid REFERENCES favorecido(id) ON DELETE SET NULL,
  descricao text,
  parcelamento_id uuid,
  numero_parcela int,
  total_parcelas int,
  recorrencia_id uuid REFERENCES recorrencia(id) ON DELETE SET NULL,
  transferencia_id uuid,
  origem text NOT NULL DEFAULT 'manual' CHECK (origem IN ('manual','foto','fatura','recorrencia','notificacao')),
  anexo_id uuid REFERENCES anexo(id) ON DELETE SET NULL,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  CHECK ((conta_id IS NOT NULL) <> (plastico_id IS NOT NULL)),
  CHECK ((plastico_id IS NULL) = (fatura_id IS NULL))
);
CREATE INDEX transacao_conta_idx ON transacao(conta_id, data_caixa);
CREATE INDEX transacao_plastico_idx ON transacao(plastico_id, data_caixa);
CREATE INDEX transacao_fatura_idx ON transacao(fatura_id);
CREATE INDEX transacao_comp_idx ON transacao(data_competencia);
CREATE UNIQUE INDEX transacao_recorrencia_uniq ON transacao(recorrencia_id, data_competencia) WHERE recorrencia_id IS NOT NULL;
ALTER TABLE fatura ADD CONSTRAINT fatura_pagamento_fk FOREIGN KEY (pagamento_transacao_id) REFERENCES transacao(id) ON DELETE SET NULL;

CREATE TABLE captura (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  criado_por uuid NOT NULL REFERENCES usuario(id),
  anexo_id uuid REFERENCES anexo(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente','confirmada','descartada','erro')),
  resultado jsonb,
  sugestao jsonb,
  erro text,
  modelo text,
  transacao_id uuid REFERENCES transacao(id) ON DELETE SET NULL,
  criado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX captura_usuario_idx ON captura(criado_por, criado_em DESC);

CREATE TABLE convite (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo text NOT NULL CHECK (tipo IN ('conta','portador')),
  conta_id uuid REFERENCES conta(id) ON DELETE CASCADE,
  plastico_id uuid REFERENCES plastico(id) ON DELETE CASCADE,
  email citext NOT NULL,
  papel text CHECK (papel IN ('leitor','editor','gestor')),
  descricao text NOT NULL DEFAULT '',
  criado_por uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  estado text NOT NULL DEFAULT 'pendente' CHECK (estado IN ('pendente','aceito','recusado','cancelado')),
  criado_em timestamptz NOT NULL DEFAULT now(),
  expira_em timestamptz NOT NULL DEFAULT now() + interval '14 days',
  CHECK ((tipo = 'conta' AND conta_id IS NOT NULL AND papel IS NOT NULL) OR (tipo = 'portador' AND plastico_id IS NOT NULL))
);
CREATE INDEX convite_email_idx ON convite(email);
