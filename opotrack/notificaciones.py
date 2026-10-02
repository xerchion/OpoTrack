"""Envío de avisos de novedades por Telegram.

El comando ``python cli.py notificar`` usa este módulo para mandar al móvil un
resumen de las convocatorias nuevas detectadas (los candidatos de la bandeja
que aún no se han avisado). Solo necesita ``requests`` (ya en requirements) y
dos variables en el ``.env``:

    TELEGRAM_BOT_TOKEN=...   (el bot que creas con @BotFather)
    TELEGRAM_CHAT_ID=...     (tu chat con el bot)

El paso a paso para obtenerlas está en NOTIFICACIONES.md. El mensaje se manda en
HTML (parse_mode=HTML) y se trocea si supera el límite de Telegram.
"""

from __future__ import annotations

import html
from typing import Optional, Sequence

import requests

from . import config
from .models import Candidato


class TelegramNoConfigurado(Exception):
    """Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en el entorno/.env."""


class EnvioFallido(Exception):
    """La API de Telegram devolvió un error al enviar el mensaje."""


# Telegram admite hasta 4096 caracteres por mensaje; troceamos con margen.
LIMITE_TELEGRAM = 4096
TROZO_OBJETIVO = 3500


def hay_config() -> bool:
    """True si están configurados el token del bot y el chat de destino."""
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def _esc(texto: Optional[str]) -> str:
    """Escapa el texto para el parse_mode HTML de Telegram (< > &)."""
    return html.escape((texto or "").strip(), quote=False)


def _esc_attr(url: Optional[str]) -> str:
    """Escapa una URL para usarla como atributo href (también comillas)."""
    return html.escape((url or "").strip(), quote=True)


# --- Construcción del mensaje -------------------------------------------

def _bloque_candidato(c: Candidato) -> str:
    """Formatea una novedad como un bloque compacto y legible en el móvil."""
    marca = "🟢" if (c.nivel_confianza == "alta") else "🟡"
    titulo = _esc(c.titulo or c.referencia_oficial or "Convocatoria")
    if c.url:
        linea1 = f'{marca} <a href="{_esc_attr(c.url)}"><b>{titulo}</b></a>'
    else:
        linea1 = f"{marca} <b>{titulo}</b>"

    lineas = [linea1]
    contexto = " · ".join(x for x in (_esc(c.organismo), _esc(c.localidad)) if x)
    if contexto:
        lineas.append(f"   {contexto}")
    fuente = _esc(c.fuente.nombre) if c.fuente else ""
    metas = " · ".join(x for x in (fuente, _esc(c.perfil_coincidente)) if x)
    if metas:
        lineas.append(f"   <i>{metas}</i>")
    return "\n".join(lineas)


def _trocear(cabecera: str, bloques: Sequence[str], sep: str = "\n\n") -> list[str]:
    """Une la cabecera y los bloques en mensajes que no superen el límite."""
    mensajes: list[str] = []
    actual = cabecera
    for b in bloques:
        tentativo = f"{actual}{sep}{b}"
        if len(tentativo) > TROZO_OBJETIVO and actual:
            mensajes.append(actual)
            actual = f"… (continúa){sep}{b}"
        else:
            actual = tentativo
    if actual:
        mensajes.append(actual)
    # Salvaguarda: si un único bloque fuese enorme, recorta al límite duro.
    return [m[:LIMITE_TELEGRAM] for m in mensajes]


def construir_mensaje(
    candidatos: Sequence[Candidato], fecha_legible: Optional[str] = None
) -> list[str]:
    """Devuelve la lista de mensajes (uno o varios) con las novedades.

    Ordena primero las de confianza alta (coincide el ámbito geográfico) y,
    dentro de cada nivel, por puntuación descendente.
    """
    n = len(candidatos)
    plural = "" if n == 1 else "s"
    cabecera = "📋 <b>OpoTrack — novedades</b>"
    if fecha_legible:
        cabecera += f" ({_esc(fecha_legible)})"
    cabecera += f"\n{n} convocatoria{plural} nueva{plural} en tu bandeja."

    orden = {"alta": 0, "media": 1, "baja": 2}
    ordenados = sorted(
        candidatos,
        key=lambda c: (orden.get(c.nivel_confianza or "", 3), -(c.score or 0)),
    )
    bloques = [_bloque_candidato(c) for c in ordenados]
    return _trocear(cabecera, bloques)


def mensaje_sin_novedades(fecha_legible: Optional[str] = None) -> str:
    """Aviso corto para los días en que no hay nada que notificar."""
    cuando = f" \u00ab{fecha_legible}\u00bb" if fecha_legible else ""
    return f"📋 <b>OpoTrack</b>\nSin novedades en la fecha{cuando}."


def mensaje_prueba() -> str:
    """Mensaje de comprobación de la conexión con Telegram."""
    return (
        "✅ <b>OpoTrack conectado.</b>\n"
        "Si ves esto, los avisos por Telegram funcionan."
    )


def _bloque_no_coincidente(r) -> str:
    """Una línea compacta para un anuncio que no casó con ningún perfil."""
    titulo = _esc(r.titulo or r.referencia_oficial or "Anuncio")
    if len(titulo) > 130:
        titulo = titulo[:129] + "…"
    if r.url:
        linea = f'\u2022 <a href="{_esc_attr(r.url)}">{titulo}</a>'
    else:
        linea = f"\u2022 {titulo}"
    org = _esc(r.organismo)
    if org:
        linea += f" — {org}"
    return linea


def construir_mensaje_no_coincidentes(
    resultados,
    fecha_legible: Optional[str] = None,
    nombres_fuente: Optional[dict] = None,
    limite: int = 60,
) -> list[str]:
    """Mensaje(s) con los anuncios del boletín que NO casan con los perfiles.

    Van agrupados por fuente y en formato compacto (una línea por anuncio). Con
    ``limite`` > 0 se muestran como mucho esos y se añade un "y N más".
    """
    nombres_fuente = nombres_fuente or {}
    total = len(resultados)
    mostrados = resultados[:limite] if (limite and limite > 0) else list(resultados)

    cabecera = "🔎 <b>OpoTrack — no coincidentes</b>"
    if fecha_legible:
        cabecera += f" ({_esc(fecha_legible)})"
    cabecera += (
        f"\n{total} anuncio(s) del boletín que no casan con tus perfiles."
        " Repásalos por si el filtro se dejó algo."
    )

    lineas: list[str] = []
    fuente_actual = object()
    for r in mostrados:
        cod = r.fuente_codigo
        if cod != fuente_actual:
            fuente_actual = cod
            nombre = nombres_fuente.get(cod, cod or "?")
            prefijo = "" if not lineas else "\n"
            lineas.append(f"{prefijo}<b>{_esc(nombre)}</b>")
        lineas.append(_bloque_no_coincidente(r))
    if limite and total > limite:
        lineas.append(f"\n… y {total - limite} más. Ábrelos en la app para verlos todos.")

    return _trocear(cabecera, lineas, sep="\n")


# --- Envío ---------------------------------------------------------------

def enviar_telegram(texto: str, timeout: Optional[int] = None) -> dict:
    """Envía un mensaje al chat configurado. Lanza excepción si algo falla."""
    if not hay_config():
        raise TelegramNoConfigurado(
            "Faltan TELEGRAM_BOT_TOKEN y/o TELEGRAM_CHAT_ID en el .env."
        )
    url = config.TELEGRAM_API_URL.format(token=config.TELEGRAM_BOT_TOKEN)
    try:
        resp = requests.post(
            url,
            data={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": texto,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=timeout or config.HTTP_TIMEOUT,
        )
    except requests.RequestException as e:
        raise EnvioFallido(f"No se pudo contactar con Telegram: {e}") from e

    try:
        data = resp.json()
    except ValueError:
        raise EnvioFallido(
            f"Respuesta no válida de Telegram (HTTP {resp.status_code})."
        )
    if not data.get("ok"):
        desc = data.get("description") or f"HTTP {resp.status_code}"
        raise EnvioFallido(f"Telegram rechazó el envío: {desc}")
    return data


def enviar_mensajes(mensajes: Sequence[str]) -> int:
    """Envía una tanda de mensajes en orden. Devuelve cuántos se enviaron."""
    enviados = 0
    for m in mensajes:
        enviar_telegram(m)
        enviados += 1
    return enviados
