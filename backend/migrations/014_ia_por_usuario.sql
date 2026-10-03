-- Leitura por IA por pessoa: a IA do servidor (GEMINI_API_KEY) só vale para quem o administrador liberar, e cada pessoa
-- pode cadastrar a própria chave do Gemini (guardada cifrada, visível só para o dono). Todo mundo começa DESLIGADO.
ALTER TABLE usuario ADD COLUMN ia_servidor boolean NOT NULL DEFAULT false;

CREATE TABLE usuario_ia (
  usuario_id uuid PRIMARY KEY REFERENCES usuario(id) ON DELETE CASCADE,
  chave_cifrada text NOT NULL,
  final text NOT NULL,                    -- últimos 4 caracteres, só para mostrar "termina em ••••"
  atualizado_em timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE usuario_ia ENABLE ROW LEVEL SECURITY;
CREATE POLICY uia_dono ON usuario_ia FOR ALL USING (usuario_id = app_uid()) WITH CHECK (usuario_id = app_uid());
GRANT SELECT, INSERT, UPDATE, DELETE ON usuario_ia TO fin_app;

-- de onde veio cada leitura: chave do servidor, chave própria ou nenhuma (sem IA: só guardou a foto). Linhas antigas ficam NULL (= servidor)
ALTER TABLE captura ADD COLUMN chave_ia text CHECK (chave_ia IN ('servidor','propria','nenhuma'));

-- o administrador liga/desliga a IA do servidor de uma pessoa (a API só chama isto para o ADMIN_EMAIL)
CREATE FUNCTION admin_definir_ia(p_uid uuid, p_liberada boolean) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS
$$ UPDATE usuario SET ia_servidor = p_liberada WHERE id = p_uid AND email <> 'ex-usuario@invalido.local' RETURNING true $$;

DROP FUNCTION IF EXISTS admin_listar_usuarios();
CREATE FUNCTION admin_listar_usuarios()
RETURNS TABLE (id uuid, nome text, email text, criado_em timestamptz, ultimo_acesso timestamptz, contas integer, cartoes integer,
               leituras_ia integer, leituras_ia_30d integer, lancamentos_por_mes numeric,
               ia_servidor boolean, chave_propria boolean, leituras_servidor_30d integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$
  SELECT u.id, u.nome, u.email::text, u.criado_em,
         (SELECT max(d.ultimo_uso) FROM dispositivo d WHERE d.usuario_id = u.id),
         (SELECT count(*)::int FROM conta c WHERE c.dono_id = u.id AND NOT c.inativa),
         (SELECT count(*)::int FROM cartao k WHERE k.dono_id = u.id AND NOT k.inativo),
         (SELECT count(*)::int FROM captura c WHERE c.criado_por = u.id AND c.chave_ia IS DISTINCT FROM 'nenhuma'),
         (SELECT count(*)::int FROM captura c WHERE c.criado_por = u.id AND c.chave_ia IS DISTINCT FROM 'nenhuma' AND c.criado_em > now() - interval '30 days'),
         round((SELECT count(*) FROM transacao t WHERE t.criado_por = u.id AND t.origem NOT IN ('recorrencia','rendimento')
                  AND t.criado_em > now() - interval '90 days')
               / GREATEST(1.0, LEAST(3.0, extract(epoch FROM now() - u.criado_em) / 2592000.0)), 1),
         u.ia_servidor,
         EXISTS (SELECT 1 FROM usuario_ia i WHERE i.usuario_id = u.id),
         (SELECT count(*)::int FROM captura c WHERE c.criado_por = u.id AND (c.chave_ia IS NULL OR c.chave_ia = 'servidor')
                  AND c.criado_em > now() - interval '30 days')
  FROM usuario u
  WHERE u.email <> 'ex-usuario@invalido.local'
  ORDER BY u.criado_em
$$;
