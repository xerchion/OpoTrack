"""Motor de búsqueda: aplica los perfiles a los anuncios y llena la bandeja.

Lógica de coincidencia (regla ámbito × rama):
un anuncio casa un perfil si (a) aparece al menos un término *temático* del
perfil, (b) el perfil no tiene términos *geográficos* o aparece al menos uno,
y (c) no aparece ningún término de *exclusión*. Filtro exhaustivo: ante la
duda entra en la bandeja, y el usuario descarta lo que no valga.
"""

from __future__ import annotations

import time
import unicodedata
from datetime import date
from typing import Callable, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import config, extraccion
from .fuentes import get_conector
from .fuentes.base import ConectorBase, SumarioNoDisponible
from .models import (
    Candidato,
    Descarte,
    Fuente,
    LogBusqueda,
    PerfilBusqueda,
    Publicacion,
    ResultadoBusqueda,
)


class LimiteBusquedasExcedido(Exception):
    """Se alcanzó el máximo de búsquedas permitidas para hoy."""


def normaliza(texto: Optional[str]) -> str:
    """Minúsculas y sin acentos, para comparar de forma robusta."""
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_acentos.lower()


def cargar_perfiles(session: Session) -> list[dict]:
    """Lee los perfiles activos y prepara sus reglas ya normalizadas."""
    perfiles = session.scalars(
        select(PerfilBusqueda).where(PerfilBusqueda.activo.is_(True))
    ).all()
    resultado = []
    for p in perfiles:
        resultado.append(
            {
                "nombre": p.nombre,
                "tematicas": [normaliza(r.termino) for r in p.reglas if r.tipo == "tematica"],
                "geograficas": [normaliza(r.termino) for r in p.reglas if r.tipo == "geografica"],
                "exclusiones": [normaliza(r.termino) for r in p.reglas if r.tipo == "exclusion"],
            }
        )
    return resultado


def evaluar(anuncio, perfiles: list[dict], extra_texto: str = "") -> Optional[dict]:
    """Devuelve el mejor perfil que casa el anuncio, o None.

    `extra_texto` añade contexto al texto evaluado (p. ej. la provincia de la
    fuente) para que casen los perfiles geográficos aunque no aparezca en el
    título del anuncio."""
    texto = (
        normaliza(anuncio.titulo) + " || " + normaliza(anuncio.organismo)
        + " " + normaliza(extra_texto)
    )
    mejor = None
    for p in perfiles:
        if any(term in texto for term in p["exclusiones"]):
            continue
        tematicas = [t for t in p["tematicas"] if t in texto]
        if not tematicas:
            continue
        geograficas = [g for g in p["geograficas"] if g in texto]
        if p["geograficas"] and not geograficas:
            continue  # el perfil exige ámbito geográfico y el anuncio no lo cumple
        score = len(tematicas) + len(geograficas)
        nivel = "alta" if (p["geograficas"] and geograficas) else "media"
        candidato = {"perfil": p["nombre"], "nivel": nivel, "score": score}
        if mejor is None or score > mejor["score"]:
            mejor = candidato
    return mejor


def _ya_conocido(session: Session, fuente_id: int, referencia: str) -> bool:
    """True si el anuncio ya está en bandeja, descartado o en seguimiento."""
    en_bandeja = session.scalar(
        select(Candidato.id).where(
            Candidato.fuente_id == fuente_id,
            Candidato.referencia_oficial == referencia,
        )
    )
    descartado = session.scalar(
        select(Descarte.id).where(
            Descarte.fuente_id == fuente_id,
            Descarte.referencia_oficial == referencia,
        )
    )
    en_seguimiento = session.scalar(
        select(Publicacion.id).where(
            Publicacion.fuente_id == fuente_id,
            Publicacion.referencia_oficial == referencia,
        )
    )
    return bool(en_bandeja or descartado or en_seguimiento)


def _descartado(session: Session, fuente_id: int, referencia: str) -> bool:
    """True si el anuncio está en la memoria de descartes (no debe reaparecer)."""
    return bool(session.scalar(
        select(Descarte.id).where(
            Descarte.fuente_id == fuente_id,
            Descarte.referencia_oficial == referencia,
        )
    ))


def _resultado(fuente_codigo, clasificacion, anuncio) -> ResultadoBusqueda:
    """Construye una fila de ResultadoBusqueda para el listado de la web."""
    return ResultadoBusqueda(
        clasificacion=clasificacion,
        fuente_codigo=fuente_codigo,
        referencia_oficial=anuncio.referencia_oficial,
        titulo=anuncio.titulo,
        organismo=anuncio.organismo,
        url=anuncio.url_html or anuncio.url_pdf,
        fecha_publicacion=anuncio.fecha_publicacion,
    )
def _limpiar_ya_conocidos(session: Session) -> None:
    """Vacía solo la lista 'ya conocido'; los 'sin_match' se conservan."""
    session.execute(
        delete(ResultadoBusqueda).where(ResultadoBusqueda.clasificacion == "ya_conocido")
    )


def _sin_match_existente(session: Session, fuente_codigo: str, referencia: str) -> bool:
    """True si el anuncio ya está en la lista acumulada de no coincidentes."""
    return bool(session.scalar(
        select(ResultadoBusqueda.id).where(
            ResultadoBusqueda.clasificacion == "sin_match",
            ResultadoBusqueda.fuente_codigo == fuente_codigo,
            ResultadoBusqueda.referencia_oficial == referencia,
        )
    ))

def busquedas_hoy(session: Session) -> int:
    """Número de búsquedas efectivas registradas hoy (para el límite del botón)."""
    return session.scalar(
        select(func.count())
        .select_from(LogBusqueda)
        .where(LogBusqueda.fecha == date.today(), LogBusqueda.resultado == "ok")
    ) or 0


def buscar(
    session: Session,
    conector: ConectorBase,
    fecha,
    fetch_fn: Optional[Callable] = None,
    ignorar_limite: bool = False,
) -> dict:
    """Ejecuta una búsqueda y vuelca los candidatos nuevos en la bandeja.

    Devuelve un resumen con los contadores del proceso.
    """
    limite = config.MAX_BUSQUEDAS_DIA
    if not ignorar_limite and limite > 0 and busquedas_hoy(session) >= limite:
        raise LimiteBusquedasExcedido(
            f"Alcanzado el máximo de {limite} búsquedas por hoy."
        )

    fuente = session.scalar(select(Fuente).where(Fuente.codigo == conector.codigo))
    if fuente is None:
        raise ValueError(f"Fuente '{conector.codigo}' no encontrada. ¿Ejecutaste el seed?")

    try:
        anuncios = conector.buscar(fecha, fetch_fn=fetch_fn)
    except SumarioNoDisponible:
        session.add(LogBusqueda(fuente_codigo=conector.codigo, resultado="no_publicado"))
        raise

    perfiles = cargar_perfiles(session)
    # La lista de resultados refleja únicamente la última búsqueda.
    # Esto borra los de dias anteriores
    # session.execute(delete(ResultadoBusqueda))
    # Esto permite que sigan vivas las publicaciones de dias anteriores, acumulandose

    nuevos, ya_vistos, sin_match = _procesar_anuncios(
        session, fuente, anuncios, perfiles, fuente.provincia or ""
    )
    session.add(
        LogBusqueda(
            fuente_codigo=conector.codigo,
            resultado="ok",
            num_candidatos=nuevos,
            num_ya_vistos=ya_vistos,
            num_sin_match=sin_match,
        )
    )
    return {
        "anuncios": len(anuncios),
        "nuevos": nuevos,
        "ya_vistos": ya_vistos,
        "sin_match": sin_match,
    }


def _procesar_anuncios(session, fuente, anuncios, perfiles, provincia="") -> tuple[int, int, int]:
    """Evalúa los anuncios de una fuente, crea los candidatos nuevos y registra
    los resultados 'ya conocido' / 'sin coincidencia'. No resetea la lista de
    resultados (eso lo hace quien llama). Devuelve (nuevos, ya_vistos, sin_match)."""
    nuevos, ya_vistos, sin_match = 0, 0, 0
    vistos_sin_match = set()   # evita duplicados dentro de esta misma pasada

    for anuncio in anuncios:
        if not anuncio.referencia_oficial:
            continue
        if _descartado(session, fuente.id, anuncio.referencia_oficial):
            continue  # descartado por el usuario: se ignora del todo
        match = evaluar(anuncio, perfiles, provincia)
        if not match:
            sin_match += 1
            ref = anuncio.referencia_oficial
            if ref not in vistos_sin_match and not _sin_match_existente(session, fuente.codigo, ref):
                session.add(_resultado(fuente.codigo, "sin_match", anuncio))
            vistos_sin_match.add(ref)
            continue
        if _ya_conocido(session, fuente.id, anuncio.referencia_oficial):
            ya_vistos += 1
            session.add(_resultado(fuente.codigo, "ya_conocido", anuncio))
            continue
        datos = extraccion.extraer(anuncio)
        session.add(
            Candidato(
                fuente_id=fuente.id,
                referencia_oficial=anuncio.referencia_oficial,
                fecha_publicacion=anuncio.fecha_publicacion,
                titulo=anuncio.titulo,
                url=anuncio.url_html or anuncio.url_pdf,
                organismo=anuncio.organismo,
                localidad=datos["localidad"] or (provincia or None),
                puesto=datos["puesto"],
                categoria=datos["categoria"],
                perfil_coincidente=match["perfil"],
                nivel_confianza=match["nivel"],
                score=match["score"],
            )
        )
        session.execute(
            delete(ResultadoBusqueda).where(
                ResultadoBusqueda.clasificacion == "sin_match",
                ResultadoBusqueda.fuente_codigo == fuente.codigo,
                ResultadoBusqueda.referencia_oficial == anuncio.referencia_oficial,
            )
        )
        nuevos += 1
    return nuevos, ya_vistos, sin_match


def buscar_fuentes_activas(
    session: Session,
    fecha,
    fetch_map: Optional[dict] = None,
    ignorar_limite: bool = False,
    codigos: Optional[list] = None,
    excluir: Optional[list] = None,
    limite: Optional[int] = None,
    on_progress: Optional[Callable] = None,
) -> dict:
    """Ejecuta la búsqueda en las fuentes activas que tengan conector.
    Si se pasa ``codigos``, se limita a esas fuentes (por su código).
    Si se pasa ``excluir``, se descartan esas fuentes (por su código).
    Resetea la lista de resultados una vez y registra un único log agregado."""
    if limite is None:
        limite = config.MAX_BUSQUEDAS_DIA
    if not ignorar_limite and limite > 0 and busquedas_hoy(session) >= limite:
        raise LimiteBusquedasExcedido(f"Alcanzado el máximo de {limite} búsquedas por hoy.")

    perfiles = cargar_perfiles(session)
    # Esto borra las publicaciones de dias anteriores
    # session.execute(delete(ResultadoBusqueda))
    # y esto permite que sigan acumulandose
    _limpiar_ya_conocidos(session)
    total = {"anuncios": 0, "nuevos": 0, "ya_vistos": 0, "sin_match": 0, "fuentes": [], "detalle": []}
    _t_ini = time.monotonic()

    consulta = select(Fuente).where(Fuente.activa.is_(True))
    if codigos:
        consulta = consulta.where(Fuente.codigo.in_(codigos))
    if excluir:
        consulta = consulta.where(Fuente.codigo.not_in(excluir))
    fuentes = session.scalars(consulta).all()
    total_fuentes = len(fuentes)
    for idx, fuente in enumerate(fuentes, start=1):
        if on_progress is not None:
            try:
                on_progress(idx, total_fuentes, fuente.codigo, fuente.nombre)
            except Exception:  # noqa: BLE001 (el progreso nunca debe romper la búsqueda)
                pass
        _t0 = time.monotonic()
        conector = get_conector(fuente.codigo)
        if conector is None:
            total["detalle"].append({"codigo": fuente.codigo, "estado": "sin_conector", "segundos": round(time.monotonic() - _t0, 2)})
            continue
        fetch_fn = (fetch_map or {}).get(fuente.codigo)
        try:
            anuncios = conector.buscar(fecha, fetch_fn=fetch_fn)
        except SumarioNoDisponible:
            session.add(LogBusqueda(fuente_codigo=fuente.codigo, resultado="no_publicado"))
            total["detalle"].append({"codigo": fuente.codigo, "estado": "sin_publicacion", "segundos": round(time.monotonic() - _t0, 2)})
            continue
        except Exception as e:  # noqa: BLE001
            session.add(LogBusqueda(fuente_codigo=fuente.codigo, resultado="error"))
            total["detalle"].append({"codigo": fuente.codigo, "estado": "error", "error": str(e)[:150], "segundos": round(time.monotonic() - _t0, 2)})
            continue
        n, y, s = _procesar_anuncios(session, fuente, anuncios, perfiles, fuente.provincia or "")
        total["anuncios"] += len(anuncios)
        total["nuevos"] += n
        total["ya_vistos"] += y
        total["sin_match"] += s
        total["fuentes"].append(fuente.codigo)
        total["detalle"].append(
            {"codigo": fuente.codigo, "estado": "ok", "nuevos": n, "anuncios": len(anuncios), "segundos": round(time.monotonic() - _t0, 2)}
        )

    session.add(
        LogBusqueda(
            fuente_codigo="TODAS",
            resultado="ok",
            num_candidatos=total["nuevos"],
            num_ya_vistos=total["ya_vistos"],
            num_sin_match=total["sin_match"],
        )
    )
    total["segundos"] = round(time.monotonic() - _t_ini, 2)
    return total
