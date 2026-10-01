import os
from urllib.parse import quote
from dataclasses import dataclass


def _segredo(nome: str, default: str = "") -> str:
    """Segredos vêm de arquivo (NOME_FILE, gerado e guardado pelo próprio app) ou, se não houver, da variável NOME."""
    caminho = os.environ.get(f"{nome}_FILE")
    if caminho and os.path.isfile(caminho):
        with open(caminho, encoding="utf-8") as f:
            return f.read().strip()
    return os.environ.get(nome, default)


def modo_teste() -> bool:
    """Só a suíte de testes liga isto: e-mail em memória, sem SMTP. Nunca é documentado nem usado em produção."""
    return os.environ.get("FIN_TESTE") == "1"


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "sim", "yes", "on")


@dataclass
class Settings:
    database_url: str = ""
    pepper: str = ""
    app_url: str = "http://localhost:8000"
    mail_mode: str = "smtp"              # sempre 'smtp' em produção; 'console' só nos testes
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_mock: bool = False
    capturas_por_dia: int = 30
    dados_dir: str = "./dados"
    otp_validade_min: int = 10
    dispositivo_idle_dias: int = 180
    web_dir: str = ""


def url_banco(papel: str) -> str:
    """URL de conexão. 'app' e 'owner' usam DATABASE_URL / DATABASE_URL_OWNER se definidas (desenvolvimento e testes);
    senão montam a URL a partir de DB_HOST/DB_PORT/DB_NAME e das senhas, escapando caracteres especiais."""
    e = os.environ
    explicita = e.get("DATABASE_URL_OWNER" if papel == "owner" else "DATABASE_URL")
    if explicita:
        return explicita
    usuario, senha = ("fin_owner", _segredo("POSTGRES_PASSWORD")) if papel == "owner" else ("fin_app", _segredo("APP_DB_PASSWORD"))
    return f"postgresql://{quote(usuario, safe='')}:{quote(senha, safe='')}@{e.get('DB_HOST', 'localhost')}:{e.get('DB_PORT', '5432')}/{e.get('DB_NAME', 'financas')}"


def carregar() -> Settings:
    e = os.environ
    return Settings(
        database_url=url_banco("app"),
        pepper=_segredo("APP_PEPPER"),
        app_url=e.get("APP_URL", "http://localhost:8000").rstrip("/"),
        mail_mode=e.get("MAIL_MODE", "smtp") if modo_teste() else "smtp",
        smtp_host=e.get("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(e.get("SMTP_PORT", "587")),
        smtp_user=e.get("SMTP_USER", ""),
        smtp_password=e.get("SMTP_PASSWORD", ""),
        mail_from=e.get("MAIL_FROM") or e.get("SMTP_USER", ""),
        gemini_api_key=e.get("GEMINI_API_KEY", ""),
        gemini_model=e.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        gemini_mock=_bool(e.get("GEMINI_MOCK")),
        capturas_por_dia=int(e.get("CAPTURAS_POR_DIA", "30")),
        dados_dir=e.get("DADOS_DIR", "./dados"),
        otp_validade_min=int(e.get("OTP_VALIDADE_MIN", "10")),
        dispositivo_idle_dias=int(e.get("DISPOSITIVO_IDLE_DIAS", "180")),
        web_dir=e.get("WEB_DIR", ""),
    )


def problemas(s: "Settings | None" = None) -> list[str]:
    """Lista, em linguagem clara, o que falta configurar para o app poder funcionar (vazia = tudo certo)."""
    s = s or settings
    if modo_teste():
        return []
    faltas = []
    if not s.pepper:
        faltas.append("segredo APP_PEPPER ausente (o serviço 'segredos' do compose o gera sozinho; confira se ele rodou)")
    if not s.smtp_user:
        faltas.append("SMTP_USER: o envio de e-mail é obrigatório (os códigos de acesso chegam por e-mail)")
    if not s.smtp_password:
        faltas.append("SMTP_PASSWORD: senha do servidor de e-mail (no Gmail, uma 'senha de app')")
    return faltas


def exigir_configuracao() -> None:
    faltas = problemas()
    if faltas:
        raise SystemExit("Configuração incompleta, o aplicativo não vai iniciar:\n  - " + "\n  - ".join(faltas)
                         + "\nEdite o arquivo docker-compose.yml (bloco 'EDITE AQUI', no topo) e rode: docker compose up -d")


settings = carregar()
