#!/usr/bin/env python3
"""Teste de leitura de comprovantes com o Gemini, sem banco e sem app.

Uso (dentro do contêiner):
  docker compose exec api python /srv/scripts/testar_gemini.py /data/teste
ou no seu computador (com `pip install -r backend/requirements.txt`):
  GEMINI_API_KEY=... python scripts/testar_gemini.py ~/fotos_de_notas

Aceita arquivos (jpg/png/webp/pdf) ou pastas. Se existir um `gabarito.csv` na pasta (colunas: arquivo;valor;data),
calcula quantos valores e datas o modelo acertou. Nada é gravado; as imagens só vão ao Gemini.
"""
import csv
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ.setdefault("DATABASE_URL", "")

from fastapi import HTTPException  # noqa: E402

from app import gemini  # noqa: E402
from app.config import settings  # noqa: E402
from app.imagens import preparar  # noqa: E402

EXT = {".jpg", ".jpeg", ".png", ".webp", ".pdf", ".heic"}


def coletar(args):
    for a in args:
        p = Path(a).expanduser()
        if p.is_dir():
            yield from sorted(x for x in p.iterdir() if x.suffix.lower() in EXT)
        elif p.exists():
            yield p


def gabarito(args):
    for a in args:
        p = Path(a).expanduser()
        g = (p if p.is_dir() else p.parent) / "gabarito.csv"
        if g.exists():
            with open(g, newline="", encoding="utf-8") as f:
                return {r["arquivo"]: r for r in csv.DictReader(f, delimiter=";")}
    return {}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if not settings.gemini_api_key and not settings.gemini_mock:
        sys.exit("Defina GEMINI_API_KEY (e, se quiser, GEMINI_MODEL).")
    arquivos = list(coletar(sys.argv[1:]))
    gab = gabarito(sys.argv[1:])
    print(f"Modelo: {settings.gemini_model} | {len(arquivos)} arquivo(s)\n")
    ok_valor = ok_data = com_gab = falhas = 0
    tin = tout = 0
    lat = []
    for arq in arquivos:
        try:
            dados, mime, _ = preparar(arq.read_bytes())
        except HTTPException as e:
            print(f"{arq.name}: PULADO ({e.detail})")
            continue
        t0 = time.time()
        try:
            ext, meta = gemini.extrair(dados, mime)
        except gemini.GeminiErro as e:
            falhas += 1
            print(f"{arq.name}: FALHOU -> {e}")
            continue
        dt = time.time() - t0
        lat.append(dt)
        tin += meta.get("tokens_entrada") or 0
        tout += meta.get("tokens_saida") or 0
        marca = ""
        g = gab.get(arq.name)
        if g:
            com_gab += 1
            v_ok = abs(ext.valor_total - float(g["valor"].replace(",", "."))) < 0.01
            d_ok = ext.data == g["data"]
            ok_valor += v_ok
            ok_data += d_ok
            marca = f"  [valor {'OK' if v_ok else 'ERRADO'} | data {'OK' if d_ok else 'ERRADA'}]"
        print(f"{arq.name}: {ext.tipo_documento} | R$ {ext.valor_total:.2f} | {ext.data or '—'} | {ext.estabelecimento or '—'} | "
              f"{ext.forma_pagamento} final={ext.final_cartao or '—'} | {ext.categoria_codigo} | conf {ext.confianca:.2f} | {dt:.1f}s{marca}")
    print("\n--- Resumo ---")
    n = len(lat)
    if n:
        print(f"Lidos: {n}  Falhas: {falhas}  Tempo médio: {sum(lat) / n:.1f}s  Tokens médios: {tin // n} entrada / {tout // n} saída")
    if com_gab:
        print(f"Com gabarito: {com_gab}  Valor certo: {ok_valor}/{com_gab}  Data certa: {ok_data}/{com_gab}")


if __name__ == "__main__":
    main()
