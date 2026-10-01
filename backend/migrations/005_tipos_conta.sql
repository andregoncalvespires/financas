-- Tipos de conta editáveis. Cada tipo tem um nome livre (ex.: "Ticket refeição") e um comportamento (classe):
--   corrente/dinheiro/terceiros entram no "disponível de verdade"; poupanca/investimento são reservas (ocultas por padrão);
--   beneficio (ticket/vale) tem saldo próprio, mostrado à parte e fora do disponível.
ALTER TABLE conta DROP CONSTRAINT IF EXISTS conta_tipo_check;
ALTER TABLE conta ADD CONSTRAINT conta_tipo_check CHECK (tipo IN ('corrente','poupanca','dinheiro','investimento','terceiros','beneficio'));

CREATE TABLE tipo_conta (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dono_id uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  nome text NOT NULL,
  nome_norm text NOT NULL,
  classe text NOT NULL CHECK (classe IN ('corrente','poupanca','dinheiro','investimento','terceiros','beneficio')),
  inativo boolean NOT NULL DEFAULT false,
  criado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (dono_id, nome_norm)
);
ALTER TABLE tipo_conta ENABLE ROW LEVEL SECURITY;
CREATE POLICY tc_sel ON tipo_conta FOR SELECT USING (dono_id = app_uid() OR cadastro_visivel(dono_id));
CREATE POLICY tc_ins ON tipo_conta FOR INSERT WITH CHECK (dono_id = app_uid());
CREATE POLICY tc_upd ON tipo_conta FOR UPDATE USING (dono_id = app_uid()) WITH CHECK (dono_id = app_uid());
CREATE POLICY tc_del ON tipo_conta FOR DELETE USING (dono_id = app_uid());
GRANT SELECT, INSERT, UPDATE (nome, nome_norm, classe, inativo), DELETE ON tipo_conta TO fin_app;

ALTER TABLE conta ADD COLUMN tipo_conta_id uuid REFERENCES tipo_conta(id) ON DELETE RESTRICT;
-- Recarga mensal (benefícios): a recorrência de receita que alimenta a conta.
ALTER TABLE conta ADD COLUMN recarga_recorrencia_id uuid REFERENCES recorrencia(id) ON DELETE SET NULL;
GRANT UPDATE (tipo_conta_id, recarga_recorrencia_id) ON conta TO fin_app;

-- Tipos padrão para quem já existe (novos usuários recebem no primeiro acesso, pela API).
INSERT INTO tipo_conta(dono_id, nome, nome_norm, classe)
SELECT u.id, t.nome, t.norm, t.classe FROM usuario u
CROSS JOIN (VALUES ('Conta corrente','conta corrente','corrente'), ('Poupança','poupanca','poupanca'), ('Investimento','investimento','investimento'),
                   ('Dinheiro','dinheiro','dinheiro'), ('Terceiros','terceiros','terceiros'), ('Ticket / Vale','ticket / vale','beneficio')) AS t(nome, norm, classe)
ON CONFLICT DO NOTHING;
UPDATE conta c SET tipo_conta_id = (SELECT tc.id FROM tipo_conta tc WHERE tc.dono_id = c.dono_id AND tc.classe = c.tipo ORDER BY tc.criado_em LIMIT 1);
GRANT UPDATE (inicio) ON recorrencia TO fin_app;
