"""Puesto del BOE a partir del cuerpo del anuncio (sin red)."""

from opotrack import extraccion
from opotrack.fuentes.base import AnuncioNormalizado
from opotrack.fuentes.boe import ConectorBOE


def test_puesto_desde_texto():
    txt = ("Se convoca proceso selectivo para cubrir dos plazas de Técnico "
           "Auxiliar de Informática, personal laboral, por concurso-oposición.")
    assert extraccion.puesto_desde_texto(txt) == "Técnico Auxiliar de Informática"


def test_extraer_puesto_cae_al_cuerpo():
    a = AnuncioNormalizado(
        referencia_oficial="BOE-A-2026-1",
        titulo="Resolución por la que se convoca proceso selectivo.",   # sin puesto
        cuerpo="En su virtud, se ofertan tres plazas de Ingeniero Técnico Industrial, "
               "personal funcionario de carrera.",
    )
    assert extraccion.extraer_puesto(a) == "Ingeniero Técnico Industrial"


def test_puesto_generico_trabajo_se_ignora():
    # 'puesto de trabajo por libre designación' NO es un puesto real -> None
    assert extraccion.puesto_desde_texto(
        "se convoca la provisión de puesto de trabajo por el sistema de libre designación."
    ) is None
    # pero 'puesto de trabajo de Jefe de Servicio' sí lo es
    assert extraccion.puesto_desde_texto(
        "provisión del puesto de trabajo de Jefe de Servicio."
    ) == "Jefe de Servicio"


def test_limpiar_texto_quita_tags_y_scripts():
    html = "<html><body><script>var x=1</script><p>Una plaza de <b>Bombero</b>.</p></body></html>"
    t = ConectorBOE._limpiar_texto(html)
    assert "Bombero" in t and "<" not in t and "x=1" not in t
