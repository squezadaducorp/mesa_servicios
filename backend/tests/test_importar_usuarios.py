import pytest
from sqlalchemy import select

from app.core.security import validar_politica_clave, verificar_clave
from app.infrastructure.db import models as m
from app.infrastructure.db.session import SessionLocal
from tests.test_api import crear_ticket
from scripts.importar_usuarios import USUARIOS_EJEMPLO, importar, leer_csv

CSV = """nombre;correo;cargo;rol;area;atiende;supervisa
Ana Prueba;ana.prueba@aducorp.com.ec;Gerente General;GERENCIA;Gerencia General;;
Beto Legal;beto.dario.apoyo@aducorp.com.ec;Jefe Legal;SUPERVISOR;Legal;LEGAL_ADUANERO*;CLASIF_ARANCEL,LEGAL_ADUANERO
Carla Aranceles;carla.aranceles@aducorp.com.ec;Especialista;ANALISTA;Operaciones Aduaneras;CLASIF_ARANCEL*;
# comentario ignorado
Dario Apoyo;dario.apoyo@aducorp.com.ec;Asistente Legal;ANALISTA;Legal;LEGAL_ADUANERO;
Elena Cliente;elena.cliente@aducorp.com.ec;Asistente;cliente;Comercial;;
"""


def test_importa_personal_y_retira_ejemplos(db):
    with SessionLocal() as s:
        res = importar(s, leer_csv(CSV))
        assert len(res.creados) == 5
        correo, clave = res.creados[0]
        u = s.scalar(select(m.Usuario).where(m.Usuario.correo == correo))
        assert verificar_clave(clave, u.clave_hash) and u.debe_cambiar_clave
        assert all(not validar_politica_clave(c) for _, c in res.creados)

        legal = s.scalar(select(m.Categoria).where(m.Categoria.codigo == "LEGAL_ADUANERO"))
        assert {(r.usuario.correo, r.es_principal) for r in legal.responsables} == {
            ("beto.dario.apoyo@aducorp.com.ec", True), ("dario.apoyo@aducorp.com.ec", False)}
        assert legal.supervisor.correo == "beto.dario.apoyo@aducorp.com.ec"

        # Los de ejemplo sin actividad desaparecen; admin@ y los clientes demo de la semilla de pruebas se conservan
        quedan = set(s.scalars(select(m.Usuario.correo)))
        assert not quedan & set(USUARIOS_EJEMPLO)
        assert "admin@aducorp.com.ec" in quedan
        assert s.get(m.Configuracion, "usuarios.ejemplo").valor == "no"


def test_segunda_carga_actualiza_sin_cambiar_claves(db):
    with SessionLocal() as s:
        importar(s, leer_csv(CSV))
        hash_antes = s.scalar(select(m.Usuario.clave_hash).where(m.Usuario.correo == "carla.aranceles@aducorp.com.ec"))
        res = importar(s, leer_csv(CSV.replace("Especialista;ANALISTA", "Especialista;SUPERVISOR")))
        assert not res.creados and len(res.actualizados) == 5
        u = s.scalar(select(m.Usuario).where(m.Usuario.correo == "carla.aranceles@aducorp.com.ec"))
        assert u.clave_hash == hash_antes
        assert s.get(m.Rol, u.rol_id).codigo == "SUPERVISOR"


def test_ejemplo_con_actividad_se_desactiva(client, como):
    crear_ticket(client, como("mesa.servicios"))
    with SessionLocal() as s:
        res = importar(s, leer_csv(CSV))
        assert "mesa.servicios@aducorp.com.ec" in res.desactivados
        assert not s.scalar(select(m.Usuario).where(m.Usuario.correo == "mesa.servicios@aducorp.com.ec")).activo


@pytest.mark.parametrize("texto, error", [
    ("nombre;correo;cargo;rol\nA;a@x.com;c;CLIENTE", "Faltan columnas"),
    (CSV + "Otro;ana.prueba@aducorp.com.ec;x;CLIENTE;;;\n", "repetido"),
    (CSV.replace("GERENCIA;Gerencia General", "JEFE;Gerencia General"), "rol desconocido"),
])
def test_csv_invalido(texto, error):
    with pytest.raises(ValueError, match=error):
        leer_csv(texto)


def test_categoria_sin_principal_no_cambia_nada(db):
    with SessionLocal() as s:
        with pytest.raises(ValueError, match="principal"):
            importar(s, leer_csv(CSV.replace("LEGAL_ADUANERO*", "LEGAL_ADUANERO")))
    with SessionLocal() as s:
        assert s.scalar(select(m.Usuario).where(m.Usuario.correo == "ana.prueba@aducorp.com.ec")) is None
        assert s.get(m.Configuracion, "usuarios.ejemplo") is None
