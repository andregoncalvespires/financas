-- Área de administração: acrescenta dois contadores por pessoa (leituras por IA e média mensal de lançamentos criados).
-- Continua sem expor lançamentos, valores, descrições ou nomes de contas. Só troca a função de relatório; não altera dados.
DROP FUNCTION IF EXISTS admin_listar_usuarios();
CREATE FUNCTION admin_listar_usuarios()
RETURNS TABLE (id uuid, nome text, email text, criado_em timestamptz, ultimo_acesso timestamptz, contas integer, cartoes integer,
               leituras_ia integer, leituras_ia_30d integer, lancamentos_por_mes numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$
  SELECT u.id, u.nome, u.email::text, u.criado_em,
         (SELECT max(d.ultimo_uso) FROM dispositivo d WHERE d.usuario_id = u.id),
         (SELECT count(*)::int FROM conta c WHERE c.dono_id = u.id AND NOT c.inativa),
         (SELECT count(*)::int FROM cartao k WHERE k.dono_id = u.id AND NOT k.inativo),
         (SELECT count(*)::int FROM captura c WHERE c.criado_por = u.id),
         (SELECT count(*)::int FROM captura c WHERE c.criado_por = u.id AND c.criado_em > now() - interval '30 days'),
         -- lançamentos criados pela pessoa nos últimos 90 dias (sem os gerados sozinhos: recorrências e rendimentos) / meses de uso (até 3)
         round((SELECT count(*) FROM transacao t WHERE t.criado_por = u.id AND t.origem NOT IN ('recorrencia','rendimento')
                  AND t.criado_em > now() - interval '90 days')
               / GREATEST(1.0, LEAST(3.0, extract(epoch FROM now() - u.criado_em) / 2592000.0)), 1)
  FROM usuario u
  WHERE u.email <> 'ex-usuario@invalido.local'
  ORDER BY u.criado_em
$$;
