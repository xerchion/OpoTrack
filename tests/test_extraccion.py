"""Pruebas de la extracción de puesto con títulos reales de la sección 2B del BOE."""

from types import SimpleNamespace as NS

from opotrack.extraccion import extraer, extraer_puesto


def _p(titulo: str):
    return extraer_puesto(NS(titulo=titulo, organismo=""))


def test_cuerpos_y_escalas():
    assert "Cuerpo de Maestros" in _p(
        "Resolución por la que se convoca proceso selectivo para ingreso en el "
        "Cuerpo de Maestros y para adquisición de nuevas especialidades."
    )
    assert _p(
        "Resolución por la que se convocan pruebas selectivas para ingreso, por el "
        "sistema general de acceso libre, en la Escala Administrativa."
    ) == "Escala Administrativa"
    assert "Cuerpo Nacional de Policía" in _p(
        "Resolución por la que se convoca proceso selectivo para la provisión de "
        "plazas de personal facultativo y técnico del Cuerpo Nacional de Policía."
    )


def test_personal_laboral():
    assert _p(
        "Resolución por la que se convoca proceso selectivo para ingreso, como "
        "personal laboral fijo, en los grupos profesionales M3, M2, M1, E2 y E1."
    ) == "personal laboral fijo"


def test_cuerpos_docentes_corta_en_ambito():
    assert _p(
        "Resolución por la que se convocan procesos selectivos para el ingreso a "
        "Cuerpos docentes del ámbito de gestión territorial del Ministerio de Educación."
    ) == "Cuerpos docentes"


def test_puesto_local_sin_organismo():
    assert _p(
        "Resolución por la que se convocan pruebas selectivas para cubrir plazas de "
        "Administrativo de la Diputación Provincial de Granada."
    ) == "Administrativo"
    assert _p(
        "Resolución por la que se convocan plazas de Técnico de Sistemas Informáticos "
        "del Ayuntamiento de Valencia."
    ) == "Técnico de Sistemas Informáticos"


def test_plaza_local_limpiador():
    # Caso real: "Dos plazas de Limpiador/a de la plantilla de personal laboral fijo, ..."
    assert _p(
        "Dos plazas de Limpiador/a de la plantilla de personal laboral fijo, por el "
        "sistema de oposición, en turno libre."
    ) == "Limpiador/a"


def test_frase_de_la_foto_extrae_todo():
    d = extraer(NS(
        titulo="Dos plazas de Limpiador/a de la plantilla de personal laboral fijo, "
               "por el sistema de oposición, en turno libre.",
        organismo="",
    ))
    assert d["puesto"] == "Limpiador/a"
    assert d["num_plazas"] == 2
    assert d["tipo_personal"] == "laboral"
    assert d["sistema_acceso"] == "oposición"
    assert "libre" in (d["turno"] or "")


def test_listas_de_admitidos():
    assert "Cuerpo General Administrativo" in _p(
        "Resolución por la que se publican las listas provisionales de admitidos y "
        "excluidos del Cuerpo General Administrativo."
    )
