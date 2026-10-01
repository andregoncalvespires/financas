"""Gera e guarda, uma única vez, os segredos do app (senhas do banco e valor de proteção dos códigos de login).

Roda como serviço de uma execução só do docker compose, antes do banco e da API. Se os arquivos já existem, não mexe em nada.
Instalações antigas (com os valores no .env) são adotadas: os mesmos valores são gravados, então nada muda para o banco existente.
Nunca imprime os valores."""
import os
import secrets
import sys

DIR = os.environ.get("SEGREDOS_DIR", "/segredos")
DONO_API = 10001                         # usuário "fin" da imagem
SEGREDOS = [("postgres_password", "POSTGRES_PASSWORD", 24), ("app_db_password", "APP_DB_PASSWORD", 24), ("app_pepper", "APP_PEPPER", 32)]


def garantir(diretorio: str = DIR, env: dict | None = None) -> dict[str, str]:
    env = os.environ if env is None else env
    os.makedirs(diretorio, exist_ok=True)
    resultado = {}
    for arquivo, variavel, nbytes in SEGREDOS:
        caminho = os.path.join(diretorio, arquivo)
        if os.path.isfile(caminho) and os.path.getsize(caminho) > 0:
            resultado[arquivo] = "existente"
            continue
        valor = (env.get(variavel) or "").strip()
        origem = "adotado do .env"
        if not valor:
            valor, origem = secrets.token_hex(nbytes), "gerado"
        fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o400)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(valor)
        try:
            os.chown(caminho, DONO_API, DONO_API)
        except (PermissionError, AttributeError):
            os.chmod(caminho, 0o444)     # sem privilégio para trocar o dono (ex.: testes locais)
        resultado[arquivo] = origem
    return resultado


if __name__ == "__main__":
    for arquivo, estado in garantir().items():
        print(f"segredo {arquivo}: {estado}", flush=True)
    sys.exit(0)
