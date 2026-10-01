-- 007: exclusão da própria conta e dos dados. Executa com os privilégios do dono (ignora RLS) mas só age sobre app_uid().
-- Usuário-sentinela: herda a autoria de lançamentos feitos em contas de OUTRAS pessoas, que continuam no caixa delas.
INSERT INTO usuario (id, email, nome) VALUES ('00000000-0000-0000-0000-00000000dead', 'ex-usuario@invalido.local', 'Ex-usuário')
ON CONFLICT (id) DO NOTHING;

CREATE FUNCTION excluir_minha_conta() RETURNS text[]
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  u uuid := app_uid();
  ex constant uuid := '00000000-0000-0000-0000-00000000dead';
  v_email citext;
  ids_tx uuid[];
  cands uuid[];
  caminhos text[];
BEGIN
  IF u IS NULL OR u = ex THEN RAISE EXCEPTION 'sem usuário autenticado'; END IF;
  SELECT email INTO v_email FROM usuario WHERE id = u;

  -- lançamentos que somem: das minhas contas e cartões (de qualquer autor), pagamentos das minhas faturas
  -- e os previstos gerados por recorrências minhas em contas alheias
  SELECT COALESCE(array_agg(DISTINCT t.id), '{}') INTO ids_tx FROM transacao t
   WHERE t.conta_id IN (SELECT id FROM conta WHERE dono_id = u)
      OR t.plastico_id IN (SELECT p.id FROM plastico p JOIN cartao k ON k.id = p.cartao_id WHERE k.dono_id = u)
      OR t.id IN (SELECT f.pagamento_transacao_id FROM fatura f JOIN cartao k ON k.id = f.cartao_id
                   WHERE k.dono_id = u AND f.pagamento_transacao_id IS NOT NULL)
      OR (t.estado = 'previsto' AND t.recorrencia_id IN (SELECT id FROM recorrencia WHERE criado_por = u));

  -- a outra ponta de uma transferência que sobra em conta alheia: previsto some; efetivado fica como movimento avulso
  DELETE FROM transacao WHERE transferencia_id IN (SELECT transferencia_id FROM transacao WHERE id = ANY(ids_tx) AND transferencia_id IS NOT NULL)
     AND id <> ALL(ids_tx) AND estado = 'previsto';
  UPDATE transacao SET transferencia_id = NULL WHERE transferencia_id IN (SELECT transferencia_id FROM transacao WHERE id = ANY(ids_tx) AND transferencia_id IS NOT NULL)
     AND id <> ALL(ids_tx);

  SELECT COALESCE(array_agg(DISTINCT a), '{}') INTO cands FROM (
    SELECT anexo_id AS a FROM transacao WHERE id = ANY(ids_tx) AND anexo_id IS NOT NULL
    UNION SELECT id FROM anexo WHERE criado_por = u) x;

  DELETE FROM transacao WHERE id = ANY(ids_tx);
  DELETE FROM recorrencia WHERE criado_por = u;
  DELETE FROM captura WHERE criado_por = u;
  DELETE FROM conta WHERE dono_id = u;
  DELETE FROM cartao WHERE dono_id = u;

  -- comprovantes: somem os que não pertencem a mais nenhum lançamento; os demais passam ao "ex-usuário"
  WITH d AS (
    DELETE FROM anexo WHERE id = ANY(cands)
       AND NOT EXISTS (SELECT 1 FROM transacao t WHERE t.anexo_id = anexo.id)
       AND NOT EXISTS (SELECT 1 FROM captura c WHERE c.anexo_id = anexo.id)
    RETURNING caminho)
  SELECT COALESCE(array_agg(caminho), '{}') INTO caminhos FROM d;
  UPDATE anexo SET criado_por = ex WHERE criado_por = u;
  UPDATE transacao SET criado_por = ex WHERE criado_por = u;

  DELETE FROM convite WHERE email = v_email;
  DELETE FROM otp WHERE email = v_email;
  DELETE FROM usuario WHERE id = u;   -- cascata: dispositivos, categorias, favorecidos, orçamento, tipos de conta, acessos, convites enviados
  RETURN caminhos;
END $$;

REVOKE ALL ON FUNCTION excluir_minha_conta() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION excluir_minha_conta() TO fin_app;

-- o "ex-usuário" precisa aparecer como autor nas listas e exportações de quem continua com os lançamentos
CREATE OR REPLACE FUNCTION usuario_visivel(p_id uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT p_id = app_uid()
   OR (p_id = '00000000-0000-0000-0000-00000000dead'
       AND EXISTS (SELECT 1 FROM transacao t WHERE t.criado_por = p_id AND pode_ver_alvo(t.conta_id, t.plastico_id)))
   OR EXISTS (SELECT 1 FROM conta c WHERE c.dono_id = p_id AND papel_conta(c.id) IS NOT NULL)
   OR EXISTS (SELECT 1 FROM conta_acesso a WHERE a.usuario_id = p_id AND papel_conta(a.conta_id) IS NOT NULL)
   OR EXISTS (SELECT 1 FROM plastico pl JOIN cartao k ON k.id = pl.cartao_id WHERE pl.portador_id = p_id AND k.dono_id = app_uid())
   OR EXISTS (SELECT 1 FROM cartao k JOIN plastico pl ON pl.cartao_id = k.id WHERE k.dono_id = p_id AND pl.portador_id = app_uid())
   OR EXISTS (SELECT 1 FROM convite v WHERE v.criado_por = p_id AND v.email = (SELECT email FROM usuario WHERE id = app_uid())) $$;
