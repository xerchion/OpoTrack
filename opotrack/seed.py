"""Datos iniciales de OpoTrack: fuentes, catálogos y perfiles de búsqueda.

Los perfiles codifican la regla de interés acordada:
- Granada y Málaga: interesan administrativa e informática.
- Resto de Andalucía y de España: solo informática.

Es idempotente: puede ejecutarse varias veces sin duplicar.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import EstadoPersonal, Fase, Fuente, PerfilBusqueda, ReglaCriterio, TipoPublicacion

FUENTES = [
    # (código, nombre, activa, provincia)
    ("BOE", "Boletín Oficial del Estado", True, None),
    ("BOPG", "Boletín Oficial de la Provincia de Granada", True, "Granada"),
    ("BOPMA", "Boletín Oficial de la Provincia de Málaga", True, "Málaga"),
    ("BOJA", "Boletín Oficial de la Junta de Andalucía", True, "Andalucía"),
    ("BOPS", "Boletín Oficial de la Provincia de Sevilla", True, "Sevilla"),
    ("BOPCO", "Boletín Oficial de la Provincia de Córdoba", True, "Córdoba"),
    ("BOPJ", "Boletín Oficial de la Provincia de Jaén", True, "Jaén"),
    ("AYTBEN", "Ayuntamiento de Benalmádena", True, "Benalmádena (Málaga)"),
    ("AYTLOJA", "Ayuntamiento de Loja", True, "Loja (Granada)"),
    ("AYTHT", "Ayuntamiento de Huétor Tájar", True, "Huétor Tájar (Granada)"),
    ("AYTANT", "Ayuntamiento de Antequera", True, "Antequera (Málaga)"),
    ("AYTMLG", "Ayuntamiento de Málaga", True, "Málaga (capital)"),
    ("AYTMOT", "Ayuntamiento de Motril", True, "Motril (Granada)"),
    ("AYTCOR", "Ayuntamiento de Córdoba", True, "Córdoba (capital)"),
    ("AYTNER", "Ayuntamiento de Nerja", True, "Nerja (Málaga)"),
]

TIPOS_PUBLICACION = [
    ("bases", "Convocatoria y bases", 10),
    ("correccion", "Corrección de errores", 15),
    ("apertura_plazo", "Apertura de plazo de solicitudes", 20),
    ("admitidos_prov", "Lista provisional de admitidos", 30),
    ("admitidos_def", "Lista definitiva de admitidos", 40),
    ("tribunal", "Designación del tribunal", 45),
    ("examen", "Fecha y lugar de examen", 50),
    ("resultados_ejercicio", "Resultados de un ejercicio", 55),
    ("resultados_prov", "Resultados provisionales", 60),
    ("resultados_def", "Resultados definitivos", 70),
    ("concurso", "Fase de concurso (méritos)", 75),
    ("nombramiento", "Nombramiento / adjudicación", 80),
    ("bolsa", "Bolsa de trabajo", 85),
    ("otros", "Otros", 99),
]

FASES = [
    ("informacion", "Información", 5),
    ("convocada", "Convocada", 10),
    ("plazo_abierto", "Inscripciones", 20),
    ("plazo_cerrado", "Plazo cerrado", 30),
    ("admitidos_prov", "Admitidos (Prov.)", 40),
    ("admitidos_def", "Admitidos (Def.)", 50),
    ("en_examen", "En examen", 60),
    ("resultados_prov", "Resultados Prov.", 70),
    ("resultados_def", "Resultados Def.", 80),
    ("concurso", "Concurso de méritos", 90),
    ("nombramiento", "Nombramiento / bolsa", 100),
    ("finalizada", "Finalizada", 110),
]

ESTADOS_PERSONALES = [
    ("me_interesa", "Me interesa"),
    ("inscrito", "Inscrito"),
    ("preparando", "Preparando"),
    ("en_espera", "En espera"),
    ("descartada", "Descartada"),
]

# Términos reutilizables.
_TEM_INFORMATICA = [
    "informática", "informático", "sistemas", "programación",
    "tecnologías de la información", "desarrollo de aplicaciones",
    "técnico auxiliar de informática", "gestión de sistemas",
    "analista", "ciberseguridad",
]
_TEM_ADMINISTRATIVO = [
    "administrativo", "administrativa", "auxiliar administrativo",
    "gestión administrativa", "cuerpo general administrativo",
    "cuerpo general auxiliar", "tramitación",
]
_EXCL_ADMIN = ["limpieza", "conductor", "peón", "bombero", "policía local"]

PERFILES = [
    {
        "nombre": "Granada/Málaga – Administrativo",
        "rama": "administrativa",
        "ambito": "Granada y Málaga",
        "tematicas": _TEM_ADMINISTRATIVO,
        "geograficas": ["granada", "málaga"],
        "exclusiones": _EXCL_ADMIN,
    },
    {
        "nombre": "Granada/Málaga – Informática",
        "rama": "informatica",
        "ambito": "Granada y Málaga",
        "tematicas": _TEM_INFORMATICA,
        "geograficas": ["granada", "málaga"],
        "exclusiones": [],
    },
    {
        "nombre": "Informática – resto de España",
        "rama": "informatica",
        "ambito": "Resto (solo informática)",
        "tematicas": _TEM_INFORMATICA,
        "geograficas": [],   # sin restricción geográfica
        "exclusiones": [],
    },
]


def seed(session: Session) -> dict:
    """Inserta los datos iniciales que falten. Devuelve un recuento."""
    creados = {"fuentes": 0, "tipos": 0, "fases": 0, "estados": 0, "perfiles": 0}

    for codigo, nombre, activa, provincia in FUENTES:
        f = session.scalar(select(Fuente).where(Fuente.codigo == codigo))
        if f is None:
            session.add(Fuente(codigo=codigo, nombre=nombre, activa=activa, provincia=provincia))
            creados["fuentes"] += 1
        else:
            if f.provincia is None and provincia:
                f.provincia = provincia          # rellena provincia en BBDD ya creadas
            if codigo in ("BOPG", "BOPMA", "BOJA", "BOPS", "BOPCO", "BOPJ", "AYTBEN", "AYTLOJA", "AYTHT", "AYTANT", "AYTMLG", "AYTMOT", "AYTCOR", "AYTNER") and not f.activa:
                f.activa = True                  # habilita Granada, Málaga, BOJA y Sevilla

    for codigo, nombre, orden in TIPOS_PUBLICACION:
        if not session.scalar(select(TipoPublicacion).where(TipoPublicacion.codigo == codigo)):
            session.add(TipoPublicacion(codigo=codigo, nombre=nombre, orden=orden))
            creados["tipos"] += 1

    for codigo, nombre, orden in FASES:
        if not session.scalar(select(Fase).where(Fase.codigo == codigo)):
            session.add(Fase(codigo=codigo, nombre=nombre, orden=orden))
            creados["fases"] += 1

    for codigo, nombre in ESTADOS_PERSONALES:
        if not session.scalar(select(EstadoPersonal).where(EstadoPersonal.codigo == codigo)):
            session.add(EstadoPersonal(codigo=codigo, nombre=nombre))
            creados["estados"] += 1

    for p in PERFILES:
        if session.scalar(select(PerfilBusqueda).where(PerfilBusqueda.nombre == p["nombre"])):
            continue
        perfil = PerfilBusqueda(
            nombre=p["nombre"], rama=p["rama"], ambito=p["ambito"], activo=True
        )
        for termino in p["tematicas"]:
            perfil.reglas.append(ReglaCriterio(tipo="tematica", termino=termino))
        for termino in p["geograficas"]:
            perfil.reglas.append(ReglaCriterio(tipo="geografica", termino=termino))
        for termino in p["exclusiones"]:
            perfil.reglas.append(ReglaCriterio(tipo="exclusion", termino=termino))
        session.add(perfil)
        creados["perfiles"] += 1

    return creados


def asegurar_fases(session: Session) -> int:
    """Inserta las fases de FASES que aún no existan y actualiza el nombre y el
    orden de las que ya existen (idempotente).

    Pensada para llamarse al arrancar la app, de modo que las bases de datos ya
    creadas incorporen fases nuevas (p. ej. 'Información') y adopten los nombres
    actuales del catálogo (p. ej. abreviaturas) sin volver a ejecutar el seed
    completo ni borrar la BBDD.
    """
    por_codigo = {f.codigo: f for f in session.scalars(select(Fase)).all()}
    creadas = 0
    for codigo, nombre, orden in FASES:
        f = por_codigo.get(codigo)
        if f is None:
            session.add(Fase(codigo=codigo, nombre=nombre, orden=orden))
            creadas += 1
        elif f.nombre != nombre or f.orden != orden:
            f.nombre = nombre
            f.orden = orden
    return creadas


def asegurar_fuentes(session: Session) -> int:
    """Inserta las fuentes de FUENTES que falten (idempotente), para que las
    BBDD ya creadas incorporen boletines nuevos (p. ej. Sevilla) al arrancar."""
    existentes = {c for (c,) in session.execute(select(Fuente.codigo)).all()}
    creadas = 0
    for codigo, nombre, activa, provincia in FUENTES:
        if codigo not in existentes:
            session.add(Fuente(codigo=codigo, nombre=nombre, activa=activa, provincia=provincia))
            creadas += 1
    return creadas
