import logging
import smtplib
from email.message import EmailMessage

from .config import settings

# filho de "uvicorn.error": sempre aparece em `docker compose logs`, mesmo que o logging raiz seja reconfigurado
log = logging.getLogger("uvicorn.error.mailer")
caixa_saida: list[dict] = []   # só os testes usam (modo_teste)


def enviar(para: str, assunto: str, corpo: str) -> None:
    if settings.mail_mode == "smtp":
        msg = EmailMessage()
        msg["From"] = settings.mail_from
        msg["To"] = para
        msg["Subject"] = assunto
        msg.set_content(corpo)
        try:
            if settings.smtp_port == 465:        # SSL implícito
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as s:
                    s.login(settings.smtp_user, settings.smtp_password)
                    s.send_message(msg)
            else:                                # STARTTLS (587)
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
                    s.starttls()
                    s.login(settings.smtp_user, settings.smtp_password)
                    s.send_message(msg)
            log.info("e-mail enviado para %s (%s)", para, assunto)
        except Exception:  # não derruba a requisição; o usuário pode pedir outro código
            log.exception("falha ao enviar e-mail para %s", para)
        return
    caixa_saida.append({"para": para, "assunto": assunto, "corpo": corpo})
    log.warning("[teste] e-mail em memória para=%s assunto=%s", para, assunto)
