-- 002: funções auxiliares. As SECURITY DEFINER leem tabelas ignorando RLS (o dono das tabelas não é submetido a ela),
-- por isso cada uma valida explicitamente app_uid() (o usuário da sessão, definido pela API por transação).

CREATE FUNCTION app_uid() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$;

CREATE FUNCTION meu_email() RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT email::text FROM usuario WHERE id = app_uid() $$;

CREATE FUNCTION papel_conta(p_conta uuid) RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT CASE WHEN c.dono_id = app_uid() THEN 'dono'
               ELSE (SELECT a.papel FROM conta_acesso a WHERE a.conta_id = c.id AND a.usuario_id = app_uid()) END
   FROM conta c WHERE c.id = p_conta $$;

CREATE FUNCTION pode_ver_conta(p_conta uuid) RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce(papel_conta(p_conta) IS NOT NULL, false) $$;
CREATE FUNCTION pode_editar_conta(p_conta uuid) RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce(papel_conta(p_conta) IN ('dono','gestor','editor'), false) $$;
CREATE FUNCTION pode_gerir_conta(p_conta uuid) RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce(papel_conta(p_conta) IN ('dono','gestor'), false) $$;

CREATE FUNCTION dono_cartao(p_cartao uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT EXISTS (SELECT 1 FROM cartao WHERE id = p_cartao AND dono_id = app_uid()) $$;
CREATE FUNCTION portador_cartao(p_cartao uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT EXISTS (SELECT 1 FROM plastico WHERE cartao_id = p_cartao AND portador_id = app_uid() AND ativo) $$;
CREATE FUNCTION dono_plastico(p_pl uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT EXISTS (SELECT 1 FROM plastico p JOIN cartao k ON k.id = p.cartao_id WHERE p.id = p_pl AND k.dono_id = app_uid()) $$;
CREATE FUNCTION portador_plastico(p_pl uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT EXISTS (SELECT 1 FROM plastico WHERE id = p_pl AND portador_id = app_uid() AND ativo) $$;
CREATE FUNCTION fatura_editavel(p_fat uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT coalesce((SELECT status <> 'paga' FROM fatura WHERE id = p_fat), false) $$;

CREATE FUNCTION pode_ver_alvo(p_conta uuid, p_plastico uuid) RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT CASE WHEN p_conta IS NOT NULL THEN pode_ver_conta(p_conta)
               ELSE dono_plastico(p_plastico) OR portador_plastico(p_plastico) END $$;
CREATE FUNCTION pode_editar_alvo(p_conta uuid, p_plastico uuid, p_criador uuid) RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT CASE WHEN p_conta IS NOT NULL THEN pode_editar_conta(p_conta)
               ELSE dono_plastico(p_plastico) OR (portador_plastico(p_plastico) AND p_criador = app_uid()) END $$;

-- Cadastros (categorias, favorecidos) do dono valem para quem usa suas contas ou é portador de seus cartões.
CREATE FUNCTION cadastro_visivel(p_dono uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT p_dono = app_uid()
   OR EXISTS (SELECT 1 FROM conta c WHERE c.dono_id = p_dono AND papel_conta(c.id) IS NOT NULL)
   OR EXISTS (SELECT 1 FROM cartao k JOIN plastico p ON p.cartao_id = k.id
              WHERE k.dono_id = p_dono AND p.portador_id = app_uid() AND p.ativo) $$;

-- Quais usuários posso "enxergar" (nome/e-mail): quem compartilha alguma conta ou cartão comigo, ou me convidou.
CREATE FUNCTION usuario_visivel(p_id uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT p_id = app_uid()
   OR EXISTS (SELECT 1 FROM conta c WHERE c.dono_id = p_id AND papel_conta(c.id) IS NOT NULL)
   OR EXISTS (SELECT 1 FROM conta_acesso a WHERE a.usuario_id = p_id AND papel_conta(a.conta_id) IS NOT NULL)
   OR EXISTS (SELECT 1 FROM plastico pl JOIN cartao k ON k.id = pl.cartao_id WHERE pl.portador_id = p_id AND k.dono_id = app_uid())
   OR EXISTS (SELECT 1 FROM cartao k JOIN plastico pl ON pl.cartao_id = k.id WHERE k.dono_id = p_id AND pl.portador_id = app_uid())
   OR EXISTS (SELECT 1 FROM convite v WHERE v.criado_por = p_id AND v.email = (SELECT email FROM usuario WHERE id = app_uid())) $$;

CREATE FUNCTION dia_no_mes(p_mes date, p_dia int) RETURNS date LANGUAGE sql IMMUTABLE AS
$$ SELECT least((p_mes + (p_dia - 1) * interval '1 day')::date, (p_mes + interval '1 month - 1 day')::date) $$;

-- Localiza (ou cria) a fatura em que uma compra feita em p_data cai. Compras até o dia do fechamento (inclusive)
-- entram na fatura que fecha neste mês; depois, na seguinte. Faturas já pagas não recebem novos lançamentos.
CREATE FUNCTION fatura_para_compra(p_plastico uuid, p_data date)
RETURNS TABLE(fatura_id uuid, data_vencimento date) LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE k cartao%ROWTYPE; mes_f date; mes_v date; f fatura%ROWTYPE;
BEGIN
  IF NOT (dono_plastico(p_plastico) OR portador_plastico(p_plastico)) THEN
    RAISE EXCEPTION 'sem permissao para este plastico' USING ERRCODE = '42501';
  END IF;
  SELECT c.* INTO k FROM cartao c JOIN plastico p ON p.cartao_id = c.id WHERE p.id = p_plastico;
  mes_f := (date_trunc('month', p_data) + (CASE WHEN extract(day FROM p_data) <= k.dia_fechamento THEN 0 ELSE 1 END) * interval '1 month')::date;
  LOOP
    mes_v := (mes_f + (CASE WHEN k.dia_vencimento > k.dia_fechamento THEN 0 ELSE 1 END) * interval '1 month')::date;
    INSERT INTO fatura(cartao_id, mes_referencia, data_fechamento, data_vencimento)
    VALUES (k.id, mes_f, dia_no_mes(mes_f, k.dia_fechamento), dia_no_mes(mes_v, k.dia_vencimento))
    ON CONFLICT (cartao_id, mes_referencia) DO NOTHING;
    SELECT * INTO f FROM fatura WHERE cartao_id = k.id AND mes_referencia = mes_f;
    EXIT WHEN f.status <> 'paga';
    mes_f := (mes_f + interval '1 month')::date;
  END LOOP;
  RETURN QUERY SELECT f.id, f.data_vencimento;
END $$;

CREATE FUNCTION provisionar_usuario(p_uid uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  INSERT INTO categoria(dono_id, nome, tipo, codigo_origem, ordem)
  SELECT DISTINCT ON (grupo_codigo) p_uid, grupo_nome, tipo, grupo_codigo, (substr(grupo_codigo,1,4))::int
  FROM kit_categoria ORDER BY grupo_codigo, ordem;
  INSERT INTO categoria(dono_id, pai_id, nome, tipo, codigo_origem, ordem)
  SELECT p_uid, g.id, k.nome, k.tipo, k.codigo, k.ordem
  FROM kit_categoria k JOIN categoria g ON g.dono_id = p_uid AND g.pai_id IS NULL AND g.codigo_origem = k.grupo_codigo;
END $$;

-- ===== Autenticação por código (as tabelas otp/dispositivo só são tocadas por aqui) =====
CREATE FUNCTION auth_registrar_otp(p_email citext, p_hash text, p_ip text, p_validade_min int) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF (SELECT count(*) FROM otp WHERE email = p_email AND criado_em > now() - interval '1 hour') >= 5 THEN RETURN 'limite'; END IF;
  IF p_ip IS NOT NULL AND (SELECT count(*) FROM otp WHERE ip = p_ip AND criado_em > now() - interval '1 hour') >= 20 THEN RETURN 'limite'; END IF;
  INSERT INTO otp(email, codigo_hash, ip, expira_em) VALUES (p_email, p_hash, p_ip, now() + make_interval(mins => p_validade_min));
  RETURN 'ok';
END $$;

CREATE FUNCTION auth_verificar_otp(p_email citext, p_hash text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE o otp%ROWTYPE;
BEGIN
  SELECT * INTO o FROM otp WHERE email = p_email AND usado_em IS NULL AND expira_em > now()
  ORDER BY criado_em DESC LIMIT 1 FOR UPDATE;
  IF NOT FOUND THEN RETURN 'invalido'; END IF;
  IF o.tentativas >= 5 THEN RETURN 'bloqueado'; END IF;
  IF o.codigo_hash = p_hash THEN
    UPDATE otp SET usado_em = now() WHERE email = p_email AND usado_em IS NULL;
    RETURN 'ok';
  END IF;
  UPDATE otp SET tentativas = tentativas + 1 WHERE id = o.id;
  RETURN 'invalido';
END $$;

CREATE FUNCTION auth_tem_convite(p_email citext) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT EXISTS (SELECT 1 FROM convite WHERE email = p_email AND estado = 'pendente' AND expira_em > now()) $$;

CREATE FUNCTION auth_upsert_usuario(p_email citext, p_nome text, p_permitir boolean) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v uuid;
BEGIN
  SELECT id INTO v FROM usuario WHERE email = p_email;
  IF FOUND THEN RETURN v; END IF;
  IF NOT p_permitir THEN RETURN NULL; END IF;
  INSERT INTO usuario(email, nome) VALUES (p_email, p_nome) RETURNING id INTO v;
  PERFORM provisionar_usuario(v);
  RETURN v;
END $$;

CREATE FUNCTION auth_criar_dispositivo(p_usuario uuid, p_hash text, p_nome text) RETURNS uuid
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS
$$ INSERT INTO dispositivo(usuario_id, token_hash, nome) VALUES (p_usuario, p_hash, left(p_nome, 80)) RETURNING id $$;

CREATE FUNCTION auth_validar_dispositivo(p_hash text, p_idle_dias int)
RETURNS TABLE(usuario_id uuid, email text, nome text, dispositivo_id uuid) LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE d dispositivo%ROWTYPE;
BEGIN
  SELECT * INTO d FROM dispositivo WHERE token_hash = p_hash AND revogado_em IS NULL
    AND ultimo_uso > now() - make_interval(days => p_idle_dias);
  IF NOT FOUND THEN RETURN; END IF;
  UPDATE dispositivo SET ultimo_uso = now() WHERE id = d.id AND ultimo_uso < now() - interval '1 hour';
  RETURN QUERY SELECT u.id, u.email::text, u.nome, d.id FROM usuario u WHERE u.id = d.usuario_id;
END $$;

-- ===== Convites =====
CREATE FUNCTION aceitar_convite(p_id uuid) RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE c convite%ROWTYPE; ok boolean;
BEGIN
  SELECT * INTO c FROM convite WHERE id = p_id FOR UPDATE;
  IF NOT FOUND OR c.estado <> 'pendente' OR c.expira_em < now() OR c.email::text <> meu_email() THEN
    RAISE EXCEPTION 'convite invalido ou expirado';
  END IF;
  IF c.tipo = 'conta' THEN
    SELECT EXISTS (SELECT 1 FROM conta WHERE id = c.conta_id AND (dono_id = c.criado_por OR EXISTS
           (SELECT 1 FROM conta_acesso a WHERE a.conta_id = c.conta_id AND a.usuario_id = c.criado_por AND a.papel = 'gestor'))) INTO ok;
    IF NOT ok THEN RAISE EXCEPTION 'quem convidou nao pode mais compartilhar esta conta'; END IF;
    IF EXISTS (SELECT 1 FROM conta WHERE id = c.conta_id AND dono_id = app_uid()) THEN RAISE EXCEPTION 'voce ja e dono desta conta'; END IF;
    INSERT INTO conta_acesso(conta_id, usuario_id, papel, concedido_por) VALUES (c.conta_id, app_uid(), c.papel, c.criado_por)
    ON CONFLICT (conta_id, usuario_id) DO UPDATE SET papel = EXCLUDED.papel;
  ELSE
    SELECT EXISTS (SELECT 1 FROM plastico p JOIN cartao k ON k.id = p.cartao_id WHERE p.id = c.plastico_id AND k.dono_id = c.criado_por) INTO ok;
    IF NOT ok THEN RAISE EXCEPTION 'quem convidou nao e mais dono deste cartao'; END IF;
    UPDATE plastico SET portador_id = app_uid() WHERE id = c.plastico_id AND portador_id IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'este plastico ja tem portador'; END IF;
  END IF;
  UPDATE convite SET estado = 'aceito' WHERE id = c.id;
  RETURN c.tipo;
END $$;

CREATE FUNCTION recusar_convite(p_id uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  UPDATE convite SET estado = 'recusado' WHERE id = p_id AND estado = 'pendente' AND email::text = meu_email();
  IF NOT FOUND THEN RAISE EXCEPTION 'convite invalido'; END IF;
END $$;

CREATE FUNCTION atualizado_em_trg() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.atualizado_em := now(); RETURN NEW; END $$;
CREATE TRIGGER transacao_atualizado BEFORE UPDATE ON transacao FOR EACH ROW EXECUTE FUNCTION atualizado_em_trg();
