FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ /srv/backend/
COPY web/ /srv/web/
COPY scripts/ /srv/scripts/
COPY VERSION CHANGELOG.md /srv/
RUN useradd -r -u 10001 fin && mkdir -p /data && chown fin /data
USER fin
ENV DADOS_DIR=/data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/saude',timeout=4).status==200 else 1)"
CMD ["sh", "-c", "python -m app.migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
