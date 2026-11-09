"""Carga el personal real de ADUCORP y retira los usuarios de ejemplo.

Lee un CSV separado por «;» desde la entrada estándar, con encabezado:
    nombre;correo;cargo;rol;area;atiende;supervisa
- rol: SUPER_ADMIN, ADMIN_MESA, SUPERVISOR, ANALISTA, CLIENTE o GERENCIA
- atiende: códigos de categoría separados por «,»; con «*» al final es el responsable principal (TRAMITES_ADUANA*)
- supervisa: códigos de categoría separados por «,»

Los usuarios nuevos reciben una contraseña temporal (deben cambiarla al ingresar). Los existentes se
actualizan sin tocar su contraseña. Los responsables y supervisores de las categorías nombradas en el
CSV se reemplazan por los del CSV. Los usuarios de ejemplo de 05_datos_iniciales.sql se borran si no
tienen actividad, o se desactivan si la tienen, y no vuelven a crearse en las próximas actualizaciones.

Uso (en el servidor):
    docker compose exec -T api python -m scripts.importar_usuarios < usuarios.csv
"""
from __future__ import annotations

import csv
import secrets
import string
import sys
from dataclasses import dataclass, field

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_clave, utcnow
from app.domain.enums import Rol
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal

# Usuarios de ejemplo que crea 05_datos_iniciales.sql (admin@ se conserva como cuenta de TI)
USUARIOS_EJEMPLO = [f"{u}@aducorp.com.ec" for u in (
    "mesa.servicios", "gerencia", "supervisor.tecnico", "supervisor.operativo", "david.medina", "juan.villamar",
    "denisse.quinga", "claudia.vasquez", "jorge.caicedo", "debbie.diaz", "carlos.torres",
)]
CLAVE_SIN_EJEMPLOS = "usuarios.ejemplo"
COLUMNAS = ["nombre", "correo", "cargo", "rol", "area", "atiende", "supervisa"]


@dataclass
class Fila:
    nombre: str
    correo: str
    cargo: str
    rol: str
    area: str
    atiende: dict[str, bool] = field(default_factory=dict)   # categoría -> es_principal
    supervisa: list[str] = field(default_factory=list)


@dataclass
class Resultado:
    creados: list[tuple[str, str]] = field(default_factory=list)   # (correo, contraseña temporal)
    actualizados: list[str] = field(default_factory=list)
    borrados: list[str] = field(default_factory=list)
    desactivados: list[str] = field(default_factory=list)


def clave_temporal() -> str:
    """Cumple la política: 10+ caracteres con mayúscula, minúscula, número y símbolo."""
    resto = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    return f"Ad{secrets.randbelow(10)}{resto}-x"


def _codigos(texto: str) -> list[str]:
    return [c.strip().upper() for c in (texto or "").split(",") if c.strip()]


def leer_csv(texto: str) -> list[Fila]:
    lineas = [l for l in texto.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    lector = csv.DictReader(lineas, delimiter=";")
    faltan = [c for c in COLUMNAS if c not in (lector.fieldnames or [])]
    if faltan:
        raise ValueError(f"Faltan columnas en el encabezado: {', '.join(faltan)}")
    filas, vistos, roles = [], set(), {r.value for r in Rol}
    for n, r in enumerate(lector, start=2):
        f = Fila(nombre=r["nombre"].strip(), correo=r["correo"].strip().lower(), cargo=(r["cargo"] or "").strip(),
                 rol=r["rol"].strip().upper(), area=(r["area"] or "").strip(),
                 atiende={c.rstrip("*"): c.endswith("*") for c in _codigos(r["atiende"])},
                 supervisa=_codigos(r["supervisa"]))
        if not f.nombre or "@" not in f.correo:
            raise ValueError(f"Línea {n}: falta el nombre o el correo no es válido")
        if f.correo in vistos:
            raise ValueError(f"Línea {n}: el correo {f.correo} está repetido; cada persona necesita el suyo")
        if f.rol not in roles:
            raise ValueError(f"Línea {n}: rol desconocido {f.rol}")
        vistos.add(f.correo)
        filas.append(f)
    return filas


def importar(session: Session, filas: list[Fila]) -> Resultado:
    res = Resultado()
    roles = {r.codigo: r for r in session.scalars(select(m.Rol))}
    areas = {a.nombre.lower(): a for a in session.scalars(select(m.Area))}
    categorias = {c.codigo: c for c in session.scalars(select(m.Categoria))}
    for f in filas:
        for c in [*f.atiende, *f.supervisa]:
            if c not in categorias:
                raise ValueError(f"{f.correo}: categoría desconocida {c}")
        if f.area and f.area.lower() not in areas:
            raise ValueError(f"{f.correo}: área desconocida {f.area}")
    atendidas = {c for f in filas for c in f.atiende}
    for codigo in atendidas:   # cada categoría atendida necesita un principal
        if not any(f.atiende.get(codigo) for f in filas):
            raise ValueError(f"La categoría {codigo} no tiene responsable principal (marque uno con *)")

    # 1. Usuarios del CSV
    usuarios: dict[str, m.Usuario] = {}
    for f in filas:
        u = session.scalar(select(m.Usuario).where(m.Usuario.correo == f.correo))
        if u is None:
            clave = clave_temporal()
            u = m.Usuario(correo=f.correo, clave_hash=hash_clave(clave), debe_cambiar_clave=True)
            session.add(u)
            res.creados.append((f.correo, clave))
        else:
            u.fecha_actualizacion = utcnow()
            res.actualizados.append(f.correo)
        u.nombre, u.cargo, u.rol_id = f.nombre, f.cargo or None, roles[f.rol].id
        u.area_id = areas[f.area.lower()].id if f.area else None
        u.activo, u.eliminado = True, False
        usuarios[f.correo] = u
    session.flush()

    # 2. Responsables y supervisores de las categorías que nombra el CSV
    for codigo in atendidas:
        categorias[codigo].responsables.clear()
    session.flush()
    for f in filas:
        for codigo, principal in f.atiende.items():
            categorias[codigo].responsables.append(
                m.CategoriaResponsable(usuario_id=usuarios[f.correo].id, es_principal=principal))
        for codigo in f.supervisa:
            categorias[codigo].supervisor_id = usuarios[f.correo].id

    # 3. Usuarios de ejemplo: no vuelven a crearse; se borran si no tienen actividad
    conf = session.get(m.Configuracion, CLAVE_SIN_EJEMPLOS)
    if conf is None:
        session.add(m.Configuracion(clave=CLAVE_SIN_EJEMPLOS, valor="no",
                                    descripcion="«no» evita que 05_datos_iniciales.sql cree los usuarios de ejemplo"))
    else:
        conf.valor = "no"
    session.commit()

    ejemplos = [u for u in session.scalars(select(m.Usuario).where(m.Usuario.correo.in_(USUARIOS_EJEMPLO)))
                if u.correo not in usuarios]
    for u in ejemplos:
        session.execute(delete(m.CategoriaResponsable).where(m.CategoriaResponsable.usuario_id == u.id))
        session.execute(update(m.Categoria).where(m.Categoria.supervisor_id == u.id).values(supervisor_id=None))
        session.execute(update(m.Usuario).where(m.Usuario.supervisor_id == u.id).values(supervisor_id=None))
        session.commit()
        try:
            session.delete(u)
            session.commit()
            res.borrados.append(u.correo)
        except IntegrityError:   # tiene tickets, comentarios o auditoría: se conserva inactivo
            session.rollback()
            u.activo, u.fecha_actualizacion = False, utcnow()
            session.commit()
            res.desactivados.append(u.correo)
    return res


def main() -> int:
    try:
        filas = leer_csv(sys.stdin.read())
        with SessionLocal() as session:
            res = importar(session, filas)
    except ValueError as e:
        print(f"ERROR: {e}. No se cambió nada.", file=sys.stderr)
        return 1
    print(f"Usuarios creados: {len(res.creados)} · actualizados: {len(res.actualizados)} · "
          f"de ejemplo borrados: {len(res.borrados)} · de ejemplo desactivados: {len(res.desactivados)}")
    if res.creados:
        print("\nContraseñas temporales (cada persona la cambia al ingresar):")
        ancho = max(len(c) for c, _ in res.creados)
        for correo, clave in res.creados:
            print(f"  {correo.ljust(ancho)}  {clave}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
