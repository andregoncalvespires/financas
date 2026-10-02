-- Relatório para a área de administração: só contadores e datas, nunca lançamentos, valores ou nomes de contas.
-- Só adiciona uma função; não altera dados. Quem pode chamá-la é decidido pela API (ADMIN_EMAIL).
CREATE OR REPLACE FUNCTION admin_listar_usuarios()
RETURNS TABLE (id uuid, nome text, email text, criado_em timestamptz, ultimo_acesso timestamptz, contas integer, cartoes integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$
  SELECT u.id, u.nome, u.email::text, u.criado_em,
         (SELECT max(d.ultimo_uso) FROM dispositivo d WHERE d.usuario_id = u.id),
         (SELECT count(*)::int FROM conta c WHERE c.dono_id = u.id AND NOT c.inativa),
         (SELECT count(*)::int FROM cartao k WHERE k.dono_id = u.id AND NOT k.inativo)
  FROM usuario u
  WHERE u.email <> 'ex-usuario@invalido.local'          -- marcador interno de contas excluídas, não é uma pessoa
  ORDER BY u.criado_em
$$;
