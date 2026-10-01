import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

from .config import exigir_configuracao, url_banco, _segredo
from .kit import linhas

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def aplicar(owner_url: str | None = None, app_password: str | None = None) -> None:
    owner_url = owner_url or url_banco("owner")
    app_password = app_password or _segredo("APP_DB_PASSWORD")
    with psycopg.connect(owner_url, autocommit=True) as conn:
        # cria o papel de runtime (sem BYPASSRLS) se ainda não existir
        existe = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'fin_app'").fetchone()
        if not existe:
            if not app_password:
                raise SystemExit("APP_DB_PASSWORD é obrigatório para criar o papel fin_app")
            conn.execute(sql.SQL("CREATE ROLE fin_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}").format(
                sql.Literal(app_password)))
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migracao (arquivo text PRIMARY KEY, aplicada_em timestamptz DEFAULT now())")
        feitas = {r[0] for r in conn.execute("SELECT arquivo FROM schema_migracao")}
        arquivos = sorted(MIGRATIONS.glob("*.sql"))
        if not arquivos:
            raise SystemExit(f"nenhuma migração encontrada em {MIGRATIONS}")
        for arq in arquivos:
            if arq.name in feitas:
                continue
            print(f"aplicando {arq.name}", flush=True)
            with conn.transaction():
                conn.execute(arq.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migracao(arquivo) VALUES (%s)", (arq.name,))
        # kit de categorias: sempre sincronizado com o código
        with conn.transaction():
            for cod, gcod, gnome, nome, tipo, ordem in linhas():
                conn.execute(
                    """INSERT INTO kit_categoria(codigo, grupo_codigo, grupo_nome, nome, tipo, ordem)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (codigo) DO UPDATE SET grupo_codigo = EXCLUDED.grupo_codigo,
                         grupo_nome = EXCLUDED.grupo_nome, nome = EXCLUDED.nome, tipo = EXCLUDED.tipo, ordem = EXCLUDED.ordem""",
                    (cod, gcod, gnome, nome, tipo, ordem))


if __name__ == "__main__":
    exigir_configuracao()
    aplicar()
    print("migrações ok", file=sys.stderr)
