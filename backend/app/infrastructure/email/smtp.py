"""Envío SMTP (Exchange/Office 365/Postfix). Lo usa el worker al procesar la cola."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger(__name__)


class EnviadorGraph:
    """Envío por Microsoft Graph desde el buzón compartido (EMAIL_TRANSPORTE=graph)."""

    def __init__(self, graph=None):
        self._graph = graph

    def enviar(self, para: str, asunto: str, cuerpo_html: str, cc: str | None = None) -> None:
        if not settings.EMAIL_ENABLED:
            log.info("Correo simulado (EMAIL_ENABLED=false) para %s: %s", para, asunto)
            return
        from app.infrastructure.m365.graph import ClienteGraph

        self._graph = self._graph or ClienteGraph()
        separar = lambda v: [d.strip() for d in (v or "").replace(";", ",").split(",") if d.strip()]  # noqa: E731
        self._graph.enviar_correo(settings.BUZON_CORREO, separar(para), asunto, cuerpo_html, separar(cc))


def enviador():
    return EnviadorGraph() if settings.EMAIL_TRANSPORTE == "graph" else EnviadorSmtp()


class EnviadorSmtp:
    def enviar(self, para: str, asunto: str, cuerpo_html: str, cc: str | None = None) -> None:
        msg = EmailMessage()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = para
        if cc:
            msg["Cc"] = cc
        msg["Subject"] = asunto
        msg.set_content("Este mensaje requiere un cliente de correo compatible con HTML.")
        msg.add_alternative(cuerpo_html, subtype="html")

        if not settings.EMAIL_ENABLED:
            log.info("Correo simulado (EMAIL_ENABLED=false) para %s: %s", para, asunto)
            return
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
            if settings.SMTP_STARTTLS:
                smtp.starttls(context=ssl.create_default_context())
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)


def plantilla_base(contenido: str) -> str:
    """Envoltorio HTML corporativo para todos los correos."""
    pie = ("Para agregar información, responda a este correo sin cambiar el asunto." if settings.BUZON_ENABLED
           else "Mensaje automático, no responda a este correo.")
    return f"""<!doctype html><html><body style="margin:0;background:#f4f6fa;font-family:Segoe UI,Arial,sans-serif;color:#10203C">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden">
<tr><td style="background:#10203C;padding:16px 24px;color:#ffffff;font-size:18px;font-weight:600">
ADUCORP · <span style="color:#70A9CE">Mesa de Servicios</span></td></tr>
<tr><td style="padding:24px;font-size:14px;line-height:1.5">{contenido}</td></tr>
<tr><td style="background:#F4F6FA;padding:12px 24px;font-size:11px;color:#5b6b85">
Asesores Aduaneros y Logísticos Cía. Ltda. · {pie}</td></tr>
</table></td></tr></table></body></html>"""
