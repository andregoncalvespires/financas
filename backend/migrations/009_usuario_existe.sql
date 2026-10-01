-- Permite saber, antes do primeiro acesso, se o e-mail já tem conta (para avisar o administrador de um novo cadastro).
-- Só adiciona uma função; não altera dados.
CREATE FUNCTION auth_usuario_existe(p_email citext) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT EXISTS (SELECT 1 FROM usuario WHERE email = p_email) $$;
