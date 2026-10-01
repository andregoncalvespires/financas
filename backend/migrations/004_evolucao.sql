-- 004: tipo de cartão (plástico/virtual), um único principal por conta de cartão, aliases de código de categoria,
-- orçamento por categoria e recálculo de faturas abertas quando muda fechamento/vencimento.

-- ===== Cartões (plásticos) =====
ALTER TABLE plastico ADD COLUMN tipo text NOT NULL DEFAULT 'plastico' CHECK (tipo IN ('plastico', 'virtual'));
ALTER TABLE plastico ADD CONSTRAINT plastico_principal_fisico CHECK (NOT principal OR tipo = 'plastico');
UPDATE plastico p SET principal = false
 WHERE principal AND id <> (SELECT q.id FROM plastico q WHERE q.cartao_id = p.cartao_id AND q.principal ORDER BY q.criado_em, q.id LIMIT 1);
CREATE UNIQUE INDEX plastico_um_principal ON plastico(cartao_id) WHERE principal;
GRANT UPDATE (final, tipo) ON plastico TO fin_app;

-- ===== Categorias: códigos absorvidos numa mesclagem continuam apontando para a categoria de destino =====
ALTER TABLE categoria ADD COLUMN codigos_alias text[] NOT NULL DEFAULT '{}';
GRANT UPDATE (codigos_alias) ON categoria TO fin_app;
CREATE INDEX categoria_alias_idx ON categoria USING gin (codigos_alias);

-- ===== Orçamento =====
-- mes NULL = valor padrão de todo mês; mes preenchido (dia 1) = ajuste apenas daquele mês.
CREATE TABLE orcamento (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dono_id uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  categoria_id uuid NOT NULL REFERENCES categoria(id) ON DELETE CASCADE,
  mes date CHECK (mes IS NULL OR mes = date_trunc('month', mes)::date),
  valor_centavos bigint NOT NULL CHECK (valor_centavos >= 0),
  atualizado_em timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX orcamento_uniq ON orcamento(categoria_id, COALESCE(mes, DATE '0001-01-01'));
CREATE INDEX orcamento_dono_idx ON orcamento(dono_id);
ALTER TABLE orcamento ENABLE ROW LEVEL SECURITY;
-- quem usa o cadastro do dono (contas/cartões compartilhados) consulta; só o dono altera
CREATE POLICY orc_sel ON orcamento FOR SELECT USING (dono_id = app_uid() OR cadastro_visivel(dono_id));
CREATE POLICY orc_ins ON orcamento FOR INSERT WITH CHECK (
  dono_id = app_uid() AND EXISTS (SELECT 1 FROM categoria c WHERE c.id = categoria_id AND c.dono_id = app_uid()));
CREATE POLICY orc_upd ON orcamento FOR UPDATE USING (dono_id = app_uid()) WITH CHECK (dono_id = app_uid());
CREATE POLICY orc_del ON orcamento FOR DELETE USING (dono_id = app_uid());
GRANT SELECT, INSERT, UPDATE (valor_centavos, atualizado_em), DELETE ON orcamento TO fin_app;

-- ===== Mudança de fechamento/vencimento: ajusta as faturas abertas que ainda não fecharam =====
-- Compras já lançadas permanecem na fatura em que estão; só as datas (e a data de caixa dos itens) mudam.
CREATE FUNCTION recalcular_faturas_abertas(p_cartao uuid) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE k cartao%ROWTYPE; f fatura%ROWTYPE; mes_v date; novo_f date; novo_v date; n int := 0;
BEGIN
  IF NOT dono_cartao(p_cartao) THEN RAISE EXCEPTION 'sem permissao' USING ERRCODE = '42501'; END IF;
  SELECT * INTO k FROM cartao WHERE id = p_cartao;
  FOR f IN SELECT * FROM fatura WHERE cartao_id = p_cartao AND status <> 'paga' AND data_fechamento >= current_date LOOP
    mes_v := (f.mes_referencia + (CASE WHEN k.dia_vencimento > k.dia_fechamento THEN 0 ELSE 1 END) * interval '1 month')::date;
    novo_f := dia_no_mes(f.mes_referencia, k.dia_fechamento);
    novo_v := dia_no_mes(mes_v, k.dia_vencimento);
    IF novo_f <> f.data_fechamento OR novo_v <> f.data_vencimento THEN
      UPDATE fatura SET data_fechamento = novo_f, data_vencimento = novo_v WHERE id = f.id;
      UPDATE transacao SET data_caixa = novo_v WHERE fatura_id = f.id;
      n := n + 1;
    END IF;
  END LOOP;
  RETURN n;
END $$;
REVOKE ALL ON FUNCTION recalcular_faturas_abertas(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION recalcular_faturas_abertas(uuid) TO fin_app;
