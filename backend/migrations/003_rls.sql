-- 003: RLS + privilégios do usuário de runtime (fin_app: sem BYPASSRLS, não é dono das tabelas).

ALTER TABLE usuario        ENABLE ROW LEVEL SECURITY;
ALTER TABLE dispositivo    ENABLE ROW LEVEL SECURITY;
ALTER TABLE categoria      ENABLE ROW LEVEL SECURITY;
ALTER TABLE favorecido     ENABLE ROW LEVEL SECURITY;
ALTER TABLE conta          ENABLE ROW LEVEL SECURITY;
ALTER TABLE conta_acesso   ENABLE ROW LEVEL SECURITY;
ALTER TABLE cartao         ENABLE ROW LEVEL SECURITY;
ALTER TABLE plastico       ENABLE ROW LEVEL SECURITY;
ALTER TABLE fatura         ENABLE ROW LEVEL SECURITY;
ALTER TABLE recorrencia    ENABLE ROW LEVEL SECURITY;
ALTER TABLE anexo          ENABLE ROW LEVEL SECURITY;
ALTER TABLE transacao      ENABLE ROW LEVEL SECURITY;
ALTER TABLE captura        ENABLE ROW LEVEL SECURITY;
ALTER TABLE convite        ENABLE ROW LEVEL SECURITY;
ALTER TABLE otp            ENABLE ROW LEVEL SECURITY;  -- sem policy e sem grant: só via funções auth_*

-- usuario
CREATE POLICY usuario_sel ON usuario FOR SELECT USING (usuario_visivel(id));
CREATE POLICY usuario_upd ON usuario FOR UPDATE USING (id = app_uid()) WITH CHECK (id = app_uid());

-- dispositivo (criação apenas por auth_criar_dispositivo)
CREATE POLICY disp_sel ON dispositivo FOR SELECT USING (usuario_id = app_uid());
CREATE POLICY disp_upd ON dispositivo FOR UPDATE USING (usuario_id = app_uid()) WITH CHECK (usuario_id = app_uid());
CREATE POLICY disp_del ON dispositivo FOR DELETE USING (usuario_id = app_uid());

-- categoria: cadastros do dono valem para quem usa suas contas/cartões; só o dono altera
CREATE POLICY cat_sel ON categoria FOR SELECT USING (cadastro_visivel(dono_id));
CREATE POLICY cat_ins ON categoria FOR INSERT WITH CHECK (dono_id = app_uid());
CREATE POLICY cat_upd ON categoria FOR UPDATE USING (dono_id = app_uid()) WITH CHECK (dono_id = app_uid());
CREATE POLICY cat_del ON categoria FOR DELETE USING (dono_id = app_uid());

-- favorecido: quem usa o cadastro do dono pode criar novos favorecidos nele (captura)
CREATE POLICY fav_sel ON favorecido FOR SELECT USING (cadastro_visivel(dono_id));
CREATE POLICY fav_ins ON favorecido FOR INSERT WITH CHECK (cadastro_visivel(dono_id));
CREATE POLICY fav_upd ON favorecido FOR UPDATE USING (cadastro_visivel(dono_id)) WITH CHECK (cadastro_visivel(dono_id));
CREATE POLICY fav_del ON favorecido FOR DELETE USING (dono_id = app_uid());

-- conta
-- dono_id = app_uid() vem primeiro: um INSERT ... RETURNING precisa enxergar a linha recém-criada, que uma função STABLE ainda não vê
CREATE POLICY conta_sel ON conta FOR SELECT USING (dono_id = app_uid() OR pode_ver_conta(id));
CREATE POLICY conta_ins ON conta FOR INSERT WITH CHECK (dono_id = app_uid());
CREATE POLICY conta_upd ON conta FOR UPDATE USING (pode_gerir_conta(id)) WITH CHECK (pode_gerir_conta(id));
CREATE POLICY conta_del ON conta FOR DELETE USING (dono_id = app_uid());

CREATE POLICY acesso_sel ON conta_acesso FOR SELECT USING (pode_ver_conta(conta_id));
CREATE POLICY acesso_upd ON conta_acesso FOR UPDATE USING (pode_gerir_conta(conta_id)) WITH CHECK (pode_gerir_conta(conta_id));
CREATE POLICY acesso_del ON conta_acesso FOR DELETE USING (pode_gerir_conta(conta_id) OR usuario_id = app_uid());

-- cartão / plástico / fatura
CREATE POLICY cartao_sel ON cartao FOR SELECT USING (dono_id = app_uid() OR portador_cartao(id));
CREATE POLICY cartao_ins ON cartao FOR INSERT WITH CHECK (dono_id = app_uid());
CREATE POLICY cartao_upd ON cartao FOR UPDATE USING (dono_id = app_uid()) WITH CHECK (dono_id = app_uid());
CREATE POLICY cartao_del ON cartao FOR DELETE USING (dono_id = app_uid());

CREATE POLICY plast_sel ON plastico FOR SELECT USING (dono_cartao(cartao_id) OR (portador_id = app_uid() AND ativo));
CREATE POLICY plast_ins ON plastico FOR INSERT WITH CHECK (dono_cartao(cartao_id));
CREATE POLICY plast_upd ON plastico FOR UPDATE USING (dono_plastico(id)) WITH CHECK (dono_cartao(cartao_id));
CREATE POLICY plast_del ON plastico FOR DELETE USING (dono_plastico(id));

-- fatura: só o dono do cartão (portador enxerga apenas as próprias compras, nunca o total)
CREATE POLICY fat_sel ON fatura FOR SELECT USING (dono_cartao(cartao_id));
CREATE POLICY fat_upd ON fatura FOR UPDATE USING (dono_cartao(cartao_id)) WITH CHECK (dono_cartao(cartao_id));

-- recorrência
CREATE POLICY rec_sel ON recorrencia FOR SELECT USING (pode_ver_alvo(conta_id, plastico_id));
CREATE POLICY rec_ins ON recorrencia FOR INSERT WITH CHECK (criado_por = app_uid() AND pode_editar_alvo(conta_id, plastico_id, criado_por));
CREATE POLICY rec_upd ON recorrencia FOR UPDATE USING (pode_editar_alvo(conta_id, plastico_id, criado_por)) WITH CHECK (pode_editar_alvo(conta_id, plastico_id, criado_por));
CREATE POLICY rec_del ON recorrencia FOR DELETE USING (pode_editar_alvo(conta_id, plastico_id, criado_por));

-- anexo: quem criou, ou quem enxerga a transação que o referencia (RLS de transacao se aplica à subconsulta)
CREATE POLICY anexo_sel ON anexo FOR SELECT USING (criado_por = app_uid() OR EXISTS (SELECT 1 FROM transacao t WHERE t.anexo_id = anexo.id));
CREATE POLICY anexo_ins ON anexo FOR INSERT WITH CHECK (criado_por = app_uid());
CREATE POLICY anexo_del ON anexo FOR DELETE USING (criado_por = app_uid());

-- transação
CREATE POLICY tr_sel ON transacao FOR SELECT USING (pode_ver_alvo(conta_id, plastico_id));
CREATE POLICY tr_ins ON transacao FOR INSERT WITH CHECK (
  criado_por = app_uid() AND pode_editar_alvo(conta_id, plastico_id, criado_por)
  AND (plastico_id IS NULL OR dono_plastico(plastico_id) OR fatura_editavel(fatura_id)));
CREATE POLICY tr_upd ON transacao FOR UPDATE USING (
  pode_editar_alvo(conta_id, plastico_id, criado_por)
  AND (estado <> 'conciliado' OR (conta_id IS NOT NULL AND pode_gerir_conta(conta_id)) OR (plastico_id IS NOT NULL AND dono_plastico(plastico_id)))
  AND (plastico_id IS NULL OR dono_plastico(plastico_id) OR fatura_editavel(fatura_id)))
WITH CHECK (
  pode_editar_alvo(conta_id, plastico_id, criado_por)
  AND (plastico_id IS NULL OR dono_plastico(plastico_id) OR fatura_editavel(fatura_id)));
CREATE POLICY tr_del ON transacao FOR DELETE USING (
  pode_editar_alvo(conta_id, plastico_id, criado_por)
  AND (estado <> 'conciliado' OR (conta_id IS NOT NULL AND pode_gerir_conta(conta_id)) OR (plastico_id IS NOT NULL AND dono_plastico(plastico_id)))
  AND (plastico_id IS NULL OR dono_plastico(plastico_id) OR fatura_editavel(fatura_id)));

-- captura
CREATE POLICY cap_all ON captura FOR ALL USING (criado_por = app_uid()) WITH CHECK (criado_por = app_uid());

-- convite (aceitar/recusar somente via funções)
CREATE POLICY conv_sel ON convite FOR SELECT USING (criado_por = app_uid() OR email::text = meu_email());
CREATE POLICY conv_ins ON convite FOR INSERT WITH CHECK (
  criado_por = app_uid()
  AND ((tipo = 'conta' AND pode_gerir_conta(conta_id)) OR (tipo = 'portador' AND dono_plastico(plastico_id))));
CREATE POLICY conv_upd ON convite FOR UPDATE USING (criado_por = app_uid()) WITH CHECK (criado_por = app_uid() AND estado = 'cancelado');

-- ===== Privilégios =====
GRANT SELECT ON kit_categoria TO fin_app;
GRANT SELECT, UPDATE (nome, config) ON usuario TO fin_app;
GRANT SELECT, UPDATE (revogado_em), DELETE ON dispositivo TO fin_app;
GRANT SELECT, INSERT, UPDATE (nome, pai_id, ativa, ordem), DELETE ON categoria TO fin_app;
GRANT SELECT, INSERT, UPDATE (nome, nome_norm, categoria_padrao_id), DELETE ON favorecido TO fin_app;
GRANT SELECT, INSERT, UPDATE (nome, tipo, saldo_inicial_centavos, data_saldo_inicial, inativa), DELETE ON conta TO fin_app;
GRANT SELECT, UPDATE (papel), DELETE ON conta_acesso TO fin_app;
GRANT SELECT, INSERT, UPDATE (nome, bandeira, dia_fechamento, dia_vencimento, conta_pagamento_id, limite_centavos, inativo), DELETE ON cartao TO fin_app;
GRANT SELECT, INSERT, UPDATE (rotulo, ativo, principal, portador_id), DELETE ON plastico TO fin_app;
GRANT SELECT, UPDATE (status, pagamento_transacao_id) ON fatura TO fin_app;
GRANT SELECT, INSERT, UPDATE (ativa, fim, valor_centavos, dia_mes, forma_pagamento, categoria_id, favorecido_id, descricao), DELETE ON recorrencia TO fin_app;
GRANT SELECT, INSERT, DELETE ON anexo TO fin_app;
GRANT SELECT, INSERT, DELETE, UPDATE (estado, valor_centavos, data_competencia, data_caixa, data_compra, conta_id, plastico_id, fatura_id,
      forma_pagamento, categoria_id, favorecido_id, descricao, anexo_id) ON transacao TO fin_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON captura TO fin_app;
GRANT SELECT, INSERT, UPDATE (estado) ON convite TO fin_app;

DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT p.oid::regprocedure AS sig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE n.nspname = 'public'
             AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', r.sig);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO fin_app', r.sig);
  END LOOP;
END $$;
-- provisionar_usuario só é chamada por dentro de auth_upsert_usuario
REVOKE EXECUTE ON FUNCTION provisionar_usuario(uuid) FROM fin_app;
