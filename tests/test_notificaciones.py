"""Pruebas del módulo de notificaciones y del comando `notificar`.

No tocan la red: `requests.post` se sustituye por un doble de prueba. La BBDD
es la temporal que fuerza conftest.py.  Ejecutar:  python3 -m pytest tests/ -v
"""

import os
import sys
import types

import pytest

# Permite importar cli.py (está en la raíz del proyecto, no en el paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opotrack import config, db, notificaciones as notif
from opotrack.models import Base, Candidato, Fuente, ResultadoBusqueda


# --- Dobles de prueba ----------------------------------------------------

class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _FakePost:
    """Registra las llamadas y devuelve siempre una respuesta configurable."""

    def __init__(self, payload=None):
        self.payload = payload if payload is not None else {"ok": True, "result": {}}
        self.llamadas = []

    def __call__(self, url, data=None, timeout=None):
        self.llamadas.append({"url": url, "data": data, "timeout": timeout})
        return _FakeResp(self.payload)


@pytest.fixture()
def telegram_ok(monkeypatch):
    """Configura credenciales de prueba y captura los envíos."""
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "999")
    # Estado determinista, independiente del .env real del usuario.
    monkeypatch.setattr(config, "NOTIFICAR_SIN_NOVEDADES", False)
    monkeypatch.setattr(config, "ENVIAR_NO_COINCIDENTES", True)
    fake = _FakePost()
    monkeypatch.setattr(notif.requests, "post", fake)
    return fake


def _candidato(**kw):
    base = dict(
        fuente_id=1,
        referencia_oficial="BOE-A-2026-0001",
        titulo="Técnico Auxiliar de Informática",
        url="https://www.boe.es/x",
        organismo="Ministerio X",
        localidad="Málaga",
        perfil_coincidente="Informática Málaga",
        nivel_confianza="alta",
        score=3,
        estado="pendiente",
    )
    base.update(kw)
    return Candidato(**base)


# --- construir_mensaje ---------------------------------------------------

def test_cabecera_y_conteo():
    msgs = notif.construir_mensaje([_candidato(), _candidato(referencia_oficial="BOE-A-2026-0002")], "20/09/2026")
    assert len(msgs) == 1
    assert "OpoTrack — novedades" in msgs[0]
    assert "20/09/2026" in msgs[0]
    assert "2 convocatorias nuevas" in msgs[0]


def test_singular():
    msgs = notif.construir_mensaje([_candidato()])
    assert "1 convocatoria nueva en tu bandeja" in msgs[0]


def test_orden_alta_antes_que_media():
    alta = _candidato(referencia_oficial="A", titulo="AAA-ALTA", nivel_confianza="alta", score=1)
    media = _candidato(referencia_oficial="B", titulo="BBB-MEDIA", nivel_confianza="media", score=9)
    msgs = notif.construir_mensaje([media, alta])
    texto = "\n".join(msgs)
    assert texto.index("AAA-ALTA") < texto.index("BBB-MEDIA")


def test_enlace_html():
    msgs = notif.construir_mensaje([_candidato(url="https://ej.com/a")])
    assert '<a href="https://ej.com/a">' in msgs[0]


def test_escapa_html():
    msgs = notif.construir_mensaje([_candidato(titulo="Plazas <TI> & más", url=None)])
    assert "&lt;TI&gt; &amp; más" in msgs[0]
    assert "<TI>" not in msgs[0]


def test_troceado_no_supera_limite():
    cands = [_candidato(referencia_oficial=f"BOE-{i}", titulo=f"Convocatoria número {i} " * 5)
             for i in range(200)]
    msgs = notif.construir_mensaje(cands, "20/09/2026")
    assert len(msgs) > 1
    assert all(len(m) <= notif.LIMITE_TELEGRAM for m in msgs)


# --- envío ---------------------------------------------------------------

def test_no_configurado(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    assert notif.hay_config() is False
    with pytest.raises(notif.TelegramNoConfigurado):
        notif.enviar_telegram("hola")


def test_enviar_ok(telegram_ok):
    notif.enviar_telegram("hola")
    assert len(telegram_ok.llamadas) == 1
    llamada = telegram_ok.llamadas[0]
    assert "123:ABC" in llamada["url"]
    assert llamada["data"]["chat_id"] == "999"
    assert llamada["data"]["parse_mode"] == "HTML"
    assert llamada["data"]["text"] == "hola"


def test_enviar_error(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "999")
    monkeypatch.setattr(notif.requests, "post",
                        _FakePost({"ok": False, "description": "Bad Request: chat not found"}))
    with pytest.raises(notif.EnvioFallido):
        notif.enviar_telegram("hola")


# --- comando notificar (integración ligera) ------------------------------

@pytest.fixture()
def bbdd_limpia():
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    with db.get_session() as s:
        s.add(Fuente(id=1, codigo="BOE", nombre="BOE", activa=True))
    yield


def test_cmd_notificar_marca_y_no_repite(telegram_ok, bbdd_limpia, capsys):
    import cli
    with db.get_session() as s:
        s.add(_candidato())

    args = types.SimpleNamespace(test=False, sin_buscar=True)
    cli.cmd_notificar(args)

    # Se envió y el candidato quedó marcado como notificado.
    assert len(telegram_ok.llamadas) == 1
    from sqlalchemy import select
    with db.get_session() as s:
        c = s.scalar(select(Candidato))
        assert c.fecha_notificacion is not None

    # Segunda ejecución: ya no hay pendientes sin avisar → no reenvía.
    cli.cmd_notificar(args)
    assert len(telegram_ok.llamadas) == 1


def test_cmd_notificar_test_sin_config(monkeypatch, capsys):
    import cli
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    cli.cmd_notificar(types.SimpleNamespace(test=True, sin_buscar=True))
    assert "no configurado" in capsys.readouterr().out.lower()


# --- no coincidentes (2º mensaje) --------------------------------------

def _rb(**kw):
    base = dict(
        titulo="Plaza X", referencia_oficial="R1", url="https://e/1",
        organismo="Ayto Y", fuente_codigo="BOPMA",
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_no_coincidentes_agrupa_y_enlaza():
    rs = [
        _rb(fuente_codigo="BOE", titulo="Cuerpo Superior", url="https://boe/1"),
        _rb(fuente_codigo="BOPMA", titulo="Peón", url="https://bopma/1"),
    ]
    nombres = {"BOE": "BOE", "BOPMA": "BOP Málaga"}
    msgs = notif.construir_mensaje_no_coincidentes(rs, "20/09/2026", nombres, limite=60)
    texto = "\n".join(msgs)
    assert "no coincidentes" in texto
    assert "BOP Málaga" in texto           # usa el nombre de la fuente, no el código
    assert '<a href="https://boe/1">' in texto
    assert "2 anuncio" in texto


def test_no_coincidentes_limite():
    rs = [_rb(referencia_oficial=f"R{i}", url=f"https://e/{i}", fuente_codigo="BOE")
          for i in range(5)]
    msgs = notif.construir_mensaje_no_coincidentes(rs, None, {"BOE": "BOE"}, limite=2)
    texto = "\n".join(msgs)
    assert "y 3 más" in texto


def test_cmd_notificar_envia_no_coincidentes(telegram_ok, bbdd_limpia):
    import cli
    with db.get_session() as s:
        s.add(ResultadoBusqueda(
            clasificacion="sin_match", fuente_codigo="BOE",
            referencia_oficial="BOE-A-1", titulo="Algo", url="https://e/1",
        ))
    cli.cmd_notificar(types.SimpleNamespace(
        test=False, sin_buscar=True, sin_no_coincidentes=False))
    assert len(telegram_ok.llamadas) >= 1
    assert any("no coincidentes" in ll["data"]["text"] for ll in telegram_ok.llamadas)


def test_cmd_notificar_flag_desactiva_no_coincidentes(telegram_ok, bbdd_limpia):
    import cli
    with db.get_session() as s:
        s.add(ResultadoBusqueda(
            clasificacion="sin_match", fuente_codigo="BOE",
            referencia_oficial="BOE-A-1", titulo="Algo", url="https://e/1",
        ))
    cli.cmd_notificar(types.SimpleNamespace(
        test=False, sin_buscar=True, sin_no_coincidentes=True))
    assert len(telegram_ok.llamadas) == 0


def test_mensaje_sin_novedades_texto():
    m = notif.mensaje_sin_novedades("22/09/2026")
    assert "Sin novedades en la fecha" in m
    assert "22/09/2026" in m


def test_cmd_notificar_sin_novedades_avisa(telegram_ok, bbdd_limpia, monkeypatch):
    import cli
    monkeypatch.setattr(config, "NOTIFICAR_SIN_NOVEDADES", True)
    # BBDD sin candidatos ni resultados: no hay nada que enviar.
    cli.cmd_notificar(types.SimpleNamespace(
        test=False, sin_buscar=True, sin_no_coincidentes=False))
    assert len(telegram_ok.llamadas) == 1
    assert "Sin novedades" in telegram_ok.llamadas[0]["data"]["text"]


def test_cmd_notificar_ve_su_propia_busqueda(telegram_ok, bbdd_limpia, monkeypatch):
    """Regresión: lo que inserta la búsqueda debe verse en la misma ejecución
    (antes, con autoflush=False, se mandaba 'sin novedades' pese a haber datos)."""
    import cli
    from opotrack import motor

    def fake_buscar(session, fecha, **kw):
        session.add(_candidato(referencia_oficial="BOE-A-NUEVA"))
        session.add(ResultadoBusqueda(
            clasificacion="sin_match", fuente_codigo="BOE",
            referencia_oficial="BOE-A-SM", titulo="No casa", url="https://e/sm"))
        return {"nuevos": 1, "ya_vistos": 0, "sin_match": 1}

    monkeypatch.setattr(motor, "buscar_fuentes_activas", fake_buscar)
    cli.cmd_notificar(types.SimpleNamespace(
        test=False, sin_buscar=False, sin_no_coincidentes=False))

    textos = " ".join(ll["data"]["text"] for ll in telegram_ok.llamadas)
    assert "Sin novedades" not in textos          # el bug mandaba justo esto
    assert "novedades" in textos                   # cabecera de bandeja (1 candidato)
    assert "no coincidentes" in textos             # 2º mensaje
