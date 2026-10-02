"""Extracción heurística de localidad, puesto y categoría desde el anuncio.

El BOE da el título en prosa y el organismo (departamento). De ahí derivamos,
de forma aproximada, los datos que interesan mostrar en la bandeja. Son
heurísticas mejorables; el usuario puede corregirlas al aceptar la convocatoria.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Provincias españolas (para localizar el ámbito en el texto).
PROVINCIAS = [
    "A Coruña", "Álava", "Albacete", "Alicante", "Almería", "Asturias", "Ávila",
    "Badajoz", "Barcelona", "Bizkaia", "Burgos", "Cáceres", "Cádiz", "Cantabria",
    "Castellón", "Ciudad Real", "Córdoba", "Cuenca", "Gipuzkoa", "Girona", "Granada",
    "Guadalajara", "Huelva", "Huesca", "Jaén", "La Rioja", "Las Palmas", "León",
    "Lleida", "Lugo", "Madrid", "Málaga", "Murcia", "Navarra", "Ourense", "Palencia",
    "Pontevedra", "Salamanca", "Segovia", "Sevilla", "Soria", "Tarragona", "Teruel",
    "Toledo", "Valencia", "Valladolid", "Zamora", "Zaragoza", "Ceuta", "Melilla",
    "Illes Balears", "Santa Cruz de Tenerife",
]

_ENTIDAD = re.compile(
    r"(?:Ayuntamiento|Diputaci[oó]n Provincial|Diputaci[oó]n|Cabildo(?: Insular)?|"
    r"Consejo Insular|Mancomunidad|Universidad|Consorcio)\s+de\s+"
    r"([A-Za-zÁÉÍÓÚÑáéíóúñ.\-]+(?:\s+[A-Za-zÁÉÍÓÚÑáéíóúñ.\-]+){0,3})",
    re.IGNORECASE,
)

# Cortes que marcan el fin de la denominación del puesto: puntuación, conectores
# y, sobre todo, el organismo convocante ("de la Diputación", "del Ayuntamiento"…).
# Ojo: NO cortamos en "del Cuerpo" / "de la Escala" porque forman parte del puesto.
_CORTE = (
    r"[,.;]|\s+por\s|\s+convocad|\s+aspirantes|\s+sujet|\s+correspondiente"
    r"|\s+del\s+[aá]mbito|\s+de\s+la\s+plantilla|\s+en\s+turno|\s+vacante"
    r"|\s+incluid|\s+de\s+la\s+oferta"
    r"|\s+de\s+la\s+(?:Diputaci[oó]n|Universidad|Consejer[ií]a|Direcci[oó]n|"
    r"Subsecretar[ií]a|Agencia|Comunidad|Junta|Mancomunidad|Consejo)"
    r"|\s+del\s+(?:Ayuntamiento|Ministerio|Consorcio|Cabildo|Organismo|Instituto)"
)
_CORTE_CUERPO = (
    r"[,.;]|\s+por\s|\s+y\s+para\s|\s+del\s+[aá]mbito|\s+sujet"
    r"|\s+de\s+la\s+Universidad|\s+del\s+Ministerio|\s+de\s+la\s+Consejer[ií]a"
)

_PUESTO_PATRONES = [
    re.compile(r"plazas?\s+de\s+(.+?)(?=" + _CORTE + r"|$)", re.IGNORECASE),
    re.compile(r"puestos?\s+(?:de\s+trabajo\s+)?de\s+(.+?)(?=" + _CORTE + r"|$)", re.IGNORECASE),
    re.compile(
        r"\ben\s+(?:el|la|los|las)\s+(Cuerpo[s]?\b.+?|Escala[s]?\b.+?)(?=" + _CORTE_CUERPO + r"|$)",
        re.IGNORECASE,
    ),
    re.compile(r"\bcomo\s+(personal\s+.+?)(?=" + _CORTE + r"|\s+en\s+los\s+grupos|$)", re.IGNORECASE),
    re.compile(
        r"\b(Cuerpo[s]?\b.+?|Escala[s]?\b.+?)(?=[,.;]|\s+del\s+[aá]mbito|\s+por\s|\s+sujet|$)",
        re.IGNORECASE,
    ),
    re.compile(r"categor[ií]a\s+(?:profesional\s+)?de\s+(.+?)(?=[,.;]|$)", re.IGNORECASE),
]

_GRUPO_RE = re.compile(r"\b(A1|A2|C1|C2|M1|M2|M3|E1|E2)\b", re.IGNORECASE)

# Inferencia de grupo por denominación (orden importa: lo más específico primero).
_INFERENCIA_GRUPO = [
    ("auxiliar administrativo", "C2"),
    ("administrativo", "C1"),
    ("tecnico auxiliar", "C1"),
    ("tecnico superior", "A2/B"),
    ("gestion", "A2"),
    ("subalterno", "AP/E"),
    ("ordenanza", "AP/E"),
]


def _norm(texto: Optional[str]) -> str:
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).lower()


def extraer_localidad(anuncio) -> Optional[str]:
    texto = f"{anuncio.organismo or ''}. {anuncio.titulo or ''}"
    tnorm = _norm(texto)
    for provincia in PROVINCIAS:
        if re.search(rf"\b{re.escape(_norm(provincia))}\b", tnorm):
            return provincia
    m = _ENTIDAD.search(texto)
    if m:
        return m.group(1).strip(" .,-").title()
    return None


# Resultados genéricos que NO son un puesto real (p. ej. 'puesto de trabajo por
# libre designación' captura 'trabajo'): se descartan y se sigue buscando.
_PUESTO_GENERICO = {"trabajo", "trabajos", "empleo", "empleos"}


def puesto_desde_texto(texto: str) -> Optional[str]:
    """Aplica los patrones de puesto ('… plaza(s) de X', 'puesto de X'…) a un
    texto cualquiera (título o cuerpo). Devuelve la primera coincidencia válida,
    saltando genéricos como 'trabajo' (de 'puesto de trabajo…')."""
    texto = texto or ""
    for patron in _PUESTO_PATRONES:
        for m in patron.finditer(texto):
            puesto = re.sub(r"\s+", " ", m.group(1)).strip(" .,-")
            puesto = puesto.split("(")[0].strip(" .,-")   # descarta coletillas entre paréntesis
            if len(puesto) >= 3 and _norm(puesto) not in _PUESTO_GENERICO:
                return puesto[:100]
    return None


def extraer_puesto(anuncio) -> Optional[str]:
    # Primero el título; si no da nada, el cuerpo del anuncio (BOE: se rellena
    # bajo demanda porque el título a veces no incluye el puesto).
    return puesto_desde_texto(anuncio.titulo or "") or puesto_desde_texto(
        getattr(anuncio, "cuerpo", "") or ""
    )


def extraer_categoria(anuncio) -> Optional[str]:
    titulo = anuncio.titulo or ""
    grupos = _GRUPO_RE.findall(titulo)
    if grupos:
        vistos: list[str] = []
        for g in grupos:
            gu = g.upper()
            if gu not in vistos:
                vistos.append(gu)
        return ", ".join(vistos)
    tnorm = _norm(titulo)
    for clave, grupo in _INFERENCIA_GRUPO:
        if clave in tnorm:
            return grupo
    return None


_NUMEROS = {
    "una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "cien": 100,
}
_NUM_DIGITOS_RE = re.compile(r"\b(\d{1,4})\s+plazas?\b", re.IGNORECASE)
_NUM_PALABRA_RE = re.compile(r"\b(" + "|".join(_NUMEROS) + r")\s+plazas?\b")


def extraer_num_plazas(anuncio) -> Optional[int]:
    titulo = anuncio.titulo or ""
    m = _NUM_DIGITOS_RE.search(titulo)
    if m:
        return int(m.group(1))
    m = _NUM_PALABRA_RE.search(_norm(titulo))
    if m:
        return _NUMEROS.get(m.group(1))
    return None


def extraer_tipo_personal(anuncio) -> Optional[str]:
    t = _norm(anuncio.titulo)
    if "personal laboral" in t or "laboral fijo" in t or "laboral temporal" in t:
        return "laboral"
    if "funcionari" in t or "cuerpo" in t or "escala" in t:
        return "funcionario"
    return None


def extraer_sistema_acceso(anuncio) -> Optional[str]:
    t = _norm(anuncio.titulo)
    if "concurso-oposicion" in t or "concurso oposicion" in t:
        return "concurso-oposición"
    if "oposicion" in t:
        return "oposición"
    if "concurso" in t:
        return "concurso"
    return None


def extraer_turno(anuncio) -> Optional[str]:
    t = _norm(anuncio.titulo)
    turnos = []
    if "promocion interna" in t:
        turnos.append("promoción interna")
    if "acceso libre" in t or "turno libre" in t:
        turnos.append("libre")
    if "discapacidad" in t or "diversidad funcional" in t:
        turnos.append("discapacidad")
    return ", ".join(turnos) if turnos else None


def extraer(anuncio) -> dict:
    """Devuelve todos los datos que se pueden inferir del anuncio."""
    return {
        "localidad": extraer_localidad(anuncio),
        "puesto": extraer_puesto(anuncio),
        "categoria": extraer_categoria(anuncio),
        "num_plazas": extraer_num_plazas(anuncio),
        "tipo_personal": extraer_tipo_personal(anuncio),
        "sistema_acceso": extraer_sistema_acceso(anuncio),
        "turno": extraer_turno(anuncio),
    }
