"""Proveedores de autenticación.

- Local: contraseña bcrypt en la tabla usuarios.
- LDAP / Active Directory: bind con las credenciales del usuario; opcionalmente lee
  nombre, correo y grupos para crear o sincronizar la cuenta (rol por grupo de AD).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.security import verificar_clave

log = logging.getLogger(__name__)


@dataclass
class IdentidadExterna:
    usuario_ad: str
    nombre: str
    correo: str
    cargo: str | None = None
    grupos: list[str] = field(default_factory=list)


class ProveedorLocal:
    def verificar(self, clave: str, clave_hash: str | None) -> bool:
        return verificar_clave(clave, clave_hash)


class ProveedorLdap:
    """Autenticación contra Active Directory con ldap3 (LDAPS recomendado)."""

    def autenticar(self, usuario: str, clave: str) -> IdentidadExterna | None:
        if not settings.LDAP_URL or not clave:
            return None
        from ldap3 import ALL, NTLM, SIMPLE, Connection, Server
        from ldap3.utils.conv import escape_filter_chars

        cuenta = usuario.split("@")[0].split("\\")[-1]
        servidor = Server(settings.LDAP_URL, get_info=ALL, connect_timeout=5)
        bind_user = f"{settings.LDAP_DOMINIO}\\{cuenta}" if settings.LDAP_DOMINIO else usuario
        try:
            con = Connection(servidor, user=bind_user, password=clave,
                             authentication=NTLM if settings.LDAP_DOMINIO else SIMPLE, auto_bind=True)
        except Exception as exc:   # credenciales inválidas o servidor caído
            log.info("Bind LDAP fallido para %s: %s", cuenta, exc)
            return None
        try:
            con.search(
                settings.LDAP_BASE_DN,
                f"(&(objectClass=user)(sAMAccountName={escape_filter_chars(cuenta)}))",
                attributes=["displayName", "mail", "title", "memberOf", "userPrincipalName"],
            )
            if not con.entries:
                return None
            e = con.entries[0]
            correo = str(e.mail) if e.mail else str(e.userPrincipalName)
            return IdentidadExterna(
                usuario_ad=cuenta,
                nombre=str(e.displayName) if e.displayName else cuenta,
                correo=correo.lower(),
                cargo=str(e.title) if e.title else None,
                grupos=[str(g) for g in (e.memberOf or [])],
            )
        finally:
            con.unbind()

    @staticmethod
    def rol_por_grupos(grupos: list[str]) -> str | None:
        for grupo, rol in settings.LDAP_GRUPO_ROLES.items():
            if any(g.lower() == grupo.lower() for g in grupos):
                return rol
        return None
