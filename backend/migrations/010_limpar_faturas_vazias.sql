-- Faturas abertas sem nenhuma compra (sobras de exclusões ou importações desfeitas) podem ser apagadas: o app as recria sozinho quando houver compra.
-- Só adiciona uma função; não altera dados. Quem chama precisa ser dono ou portador do cartão.
CREATE FUNCTION limpar_faturas_vazias(p_cartao uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE n integer;
BEGIN
  IF NOT (dono_cartao(p_cartao) OR portador_cartao(p_cartao)) THEN
    RETURN 0;
  END IF;
  DELETE FROM fatura f
   WHERE f.cartao_id = p_cartao AND f.status = 'aberta' AND f.pagamento_transacao_id IS NULL
     AND NOT EXISTS (SELECT 1 FROM transacao t WHERE t.fatura_id = f.id);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;
