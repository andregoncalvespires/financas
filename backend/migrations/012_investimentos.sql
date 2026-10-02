-- Contas de investimento: subtipo, rendimento, aniversário e vencimento. A poupança deixa de ser um tipo de conta à parte:
-- vira "Investimento › Poupança". Só acrescenta; as contas e lançamentos existentes não mudam de valor.

-- rendimentos previstos/confirmados pelo app passam a ter origem própria
ALTER TABLE transacao DROP CONSTRAINT transacao_origem_check;
ALTER TABLE transacao ADD CONSTRAINT transacao_origem_check CHECK (origem IN ('manual','foto','fatura','recorrencia','notificacao','rendimento'));

CREATE TABLE investimento (
  conta_id uuid PRIMARY KEY REFERENCES conta(id) ON DELETE CASCADE,
  subtipo text NOT NULL CHECK (subtipo IN ('poupanca','tesouro_selic','tesouro_prefixado','tesouro_ipca','cdb','lci','lca','lc','la',
                                           'debenture','cri_cra','fundo_rf','previdencia','renda_variavel','outro')),
  indexador text NOT NULL CHECK (indexador IN ('prefixado','cdi','selic','ipca','poupanca','manual')),
  taxa numeric(9,4),                       -- prefixado: % a.a. | cdi: % do CDI | selic e ipca: taxa a.a. somada ao índice
  data_aplicacao date,
  dia_aniversario smallint CHECK (dia_aniversario BETWEEN 1 AND 31),
  data_vencimento date,
  isento_ir boolean NOT NULL DEFAULT false,
  alerta_dias smallint NOT NULL DEFAULT 30 CHECK (alerta_dias BETWEEN 0 AND 365),
  aviso_enviado_para date,                 -- vencimento para o qual o e-mail de aviso já foi enviado
  atualizado_em timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE investimento ENABLE ROW LEVEL SECURITY;
CREATE POLICY inv_sel ON investimento FOR SELECT USING (EXISTS (SELECT 1 FROM conta c WHERE c.id = conta_id));
CREATE POLICY inv_ins ON investimento FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM conta c WHERE c.id = conta_id AND c.dono_id = app_uid()));
CREATE POLICY inv_upd ON investimento FOR UPDATE USING (EXISTS (SELECT 1 FROM conta c WHERE c.id = conta_id AND c.dono_id = app_uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM conta c WHERE c.id = conta_id AND c.dono_id = app_uid()));
CREATE POLICY inv_del ON investimento FOR DELETE USING (EXISTS (SELECT 1 FROM conta c WHERE c.id = conta_id AND c.dono_id = app_uid()));
GRANT SELECT, INSERT, UPDATE, DELETE ON investimento TO fin_app;

-- poupança vira investimento (tipos e contas); primeiro registramos quais contas eram poupança
INSERT INTO investimento(conta_id, subtipo, indexador, data_aplicacao, dia_aniversario, isento_ir)
SELECT c.id, 'poupanca', 'poupanca', c.data_saldo_inicial, LEAST(extract(day FROM c.data_saldo_inicial)::int, 28), true
FROM conta c WHERE c.tipo = 'poupanca'
ON CONFLICT DO NOTHING;
UPDATE tipo_conta SET classe = 'investimento' WHERE classe = 'poupanca';
UPDATE conta SET tipo = 'investimento' WHERE tipo = 'poupanca';

-- aviso de vencimento por e-mail: funções para a rotina diária (não dependem de um usuário logado)
CREATE FUNCTION investimentos_a_avisar(p_hoje date)
RETURNS TABLE (conta_id uuid, conta_nome text, dono_nome text, dono_email text, data_vencimento date, alerta_dias integer, saldo_centavos bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$
  SELECT c.id, c.nome, u.nome, u.email::text, i.data_vencimento, i.alerta_dias::int,
         (c.saldo_inicial_centavos + COALESCE((SELECT SUM(t.valor_centavos) FROM transacao t
            WHERE t.conta_id = c.id AND t.estado IN ('confirmado','conciliado') AND t.data_caixa >= c.data_saldo_inicial), 0))::bigint
  FROM investimento i JOIN conta c ON c.id = i.conta_id JOIN usuario u ON u.id = c.dono_id
  WHERE NOT c.inativa AND i.data_vencimento IS NOT NULL
    AND i.data_vencimento >= p_hoje AND i.data_vencimento <= p_hoje + i.alerta_dias
    AND i.aviso_enviado_para IS DISTINCT FROM i.data_vencimento
$$;
CREATE FUNCTION investimento_avisado(p_conta uuid, p_vencimento date) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS
$$ UPDATE investimento SET aviso_enviado_para = p_vencimento WHERE conta_id = p_conta AND data_vencimento = p_vencimento $$;
