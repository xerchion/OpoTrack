"""Pruebas de la interfaz web con el test_client de Flask (sin red).

Requiere que la BBDD apunte a una ruta local; en CI/local se ejecuta con
OPOTRACK_DB definido. Ejecutar:  python3 -m pytest tests/ -v
"""

import pytest
from sqlalchemy import select

from opotrack import db
from opotrack import seed as seed_mod
from opotrack.models import Base, Candidato, Convocatoria, PerfilBusqueda, ResultadoBusqueda
from opotrack.web import create_app


@pytest.fixture()
def client():
    # BBDD limpia por test.
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    with db.get_session() as s:
        seed_mod.seed(s)
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _ref_id(referencia):
    with db.get_session() as s:
        c = s.scalar(select(Candidato).where(Candidato.referencia_oficial == referencia))
        return c.id if c else None


def test_panel_responde(client):
    assert client.get("/").status_code == 200


def test_bandeja_muestra_localidad_puesto_categoria(client):
    r = client.post("/buscar", data={"modo": "demo"})
    assert r.status_code == 302
    html = client.get("/bandeja").get_data(as_text=True)
    # Los datos específicos que pidió el usuario deben aparecer.
    assert "Granada" in html
    assert "Administrativo" in html
    assert "Málaga" in html
    assert "Técnico Auxiliar de Informática" in html
    assert "C1" in html


def test_aceptar_crea_convocatoria_y_papelera(client):
    client.post("/buscar", data={"modo": "demo"})
    cid = _ref_id("BOE-A-2026-20002")
    assert client.post(f"/candidato/{cid}/aceptar").status_code == 302

    with db.get_session() as s:
        conv = s.scalar(select(Convocatoria).where(Convocatoria.estado_registro == "activa"))
        assert conv is not None
        conv_id = conv.id

    assert "Administrativo" in client.get(f"/convocatoria/{conv_id}").get_data(as_text=True)

    # A la papelera y de vuelta.
    assert client.post(f"/convocatoria/{conv_id}/eliminar", data={"motivo": "x"}).status_code == 302
    assert "Administrativo" in client.get("/papelera").get_data(as_text=True)
    assert client.post(f"/convocatoria/{conv_id}/restaurar").status_code == 302


def test_descartar_no_reaparece(client):
    client.post("/buscar", data={"modo": "demo"})
    cid = _ref_id("BOE-A-2026-20004")
    client.post(f"/candidato/{cid}/descartar", data={"motivo": "no interesa"})
    # Nueva búsqueda: el descartado no debe volver.
    client.post("/buscar", data={"modo": "demo"})
    with db.get_session() as s:
        pendientes = {
            c.referencia_oficial
            for c in s.scalars(select(Candidato).where(Candidato.estado == "pendiente"))
        }
    assert "BOE-A-2026-20004" not in pendientes


def test_home_es_la_bandeja(client):
    html = client.get("/").get_data(as_text=True)
    assert "Bandeja de novedades" in html
    assert "theme-toggle" in html  # selector de tema presente


def test_resultados_sin_coincidencia_y_a_seguimiento(client):
    client.post("/buscar", data={"modo": "demo"})
    r = client.get("/resultados/sin-coincidencia")
    assert r.status_code == 200
    assert "BOE-A-2026-20001" in r.get_data(as_text=True)  # administrativo estatal, no casa
    with db.get_session() as s:
        rid = s.scalar(
            select(ResultadoBusqueda).where(
                ResultadoBusqueda.referencia_oficial == "BOE-A-2026-20001"
            )
        ).id
    assert client.post(f"/resultado/{rid}/seguimiento").status_code == 302
    with db.get_session() as s:
        assert s.scalar(
            select(Convocatoria).where(Convocatoria.estado_registro == "activa")
        ) is not None


def test_configuracion_crud(client):
    assert client.get("/configuracion").status_code == 200
    assert client.post(
        "/configuracion/perfil/nuevo", data={"nombre": "Perfil X", "rama": "informatica"}
    ).status_code == 302
    with db.get_session() as s:
        pid = s.scalar(select(PerfilBusqueda).where(PerfilBusqueda.nombre == "Perfil X")).id
    assert client.post(
        f"/configuracion/perfil/{pid}/regla", data={"tipo": "tematica", "termino": "redes"}
    ).status_code == 302
    assert client.post(f"/configuracion/perfil/{pid}/toggle").status_code == 302
    assert client.post(f"/configuracion/perfil/{pid}/eliminar").status_code == 302
