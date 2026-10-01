import logging
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import exigir_configuracao, settings
from .db import abrir_pool, fechar_pool, sessao
from .routers import auth, capturas, cadastros, cartoes, conta_usuario, contas, exportar, lembretes, orcamento, resumo, transacoes

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    exigir_configuracao()
    abrir_pool()
    yield
    fechar_pool()


app = FastAPI(title="Finanças", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

for r in (auth, cadastros, contas, cartoes, transacoes, resumo, capturas, orcamento, lembretes, exportar, conta_usuario):
    app.include_router(r.router)


@app.get("/api/saude")
def saude():
    with sessao(None) as cur:
        cur.execute("SELECT 1")
    return {"ok": True}


def _erro(status: int, msg: str):
    return JSONResponse({"detail": msg}, status_code=status)


@app.exception_handler(psycopg.errors.InsufficientPrivilege)
async def _sem_permissao(request: Request, exc):
    return _erro(403, "sem permissão para esta operação")


@app.exception_handler(psycopg.errors.RaiseException)
async def _regra(request: Request, exc):
    return _erro(400, exc.diag.message_primary or "operação inválida")


@app.exception_handler(psycopg.errors.UniqueViolation)
async def _unico(request: Request, exc):
    return _erro(409, "já existe um registro igual")


@app.exception_handler(psycopg.errors.ForeignKeyViolation)
async def _fk(request: Request, exc):
    return _erro(409, "registro em uso por outros dados ou referência inválida")


@app.exception_handler(psycopg.errors.IntegrityError)
async def _integridade(request: Request, exc):
    return _erro(422, "dados inválidos")


@app.exception_handler(psycopg.errors.DataError)
async def _dados(request: Request, exc):
    return _erro(422, "valor inválido")


@app.middleware("http")
async def cabecalhos(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Content-Security-Policy",
                            "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    else:
        # Arquivos do app: sempre revalidar (ETag) para que atualizações apareçam sem limpar o cache do navegador.
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


_web = Path(settings.web_dir) if settings.web_dir else Path(__file__).resolve().parents[2] / "web"
if _web.exists():
    app.mount("/", StaticFiles(directory=_web, html=True), name="web")
