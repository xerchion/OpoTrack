"""Configuración central de OpoTrack.

Rutas, parámetros de la fuente BOE y límites de uso. Todo lo que aquí es un
valor por defecto se pensó para poder moverse a una tabla de configuración
editable desde la web más adelante.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

# --- Rutas ---------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # carpeta OpoTrack
DATA_DIR = BASE_DIR / "data"
FIXTURES_DIR = BASE_DIR / "fixtures"

# Variables de entorno: se cargan de un archivo .env en la raíz del proyecto
# (python-dotenv) si existe, antes de leer nada de os.environ. Así las
# credenciales no se guardan en la BBDD ni en git (.env está en .gitignore).
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# La ruta de la BBDD puede sobreescribirse con la variable de entorno
# OPOTRACK_DB (útil para pruebas o para ubicarla en otra carpeta).
# Ubicación de la BBDD. Por defecto FUERA de la carpeta del proyecto (que suele
# sincronizarse con Drive/OneDrive, y SQLite sincronizado da bloqueos/corrupción):
# se usa la carpeta local de datos del usuario. Se puede forzar con OPOTRACK_DB.
# Si ya existía una BBDD en data/opotrack.db, init_db() la copia una vez.
_env_db = os.environ.get("OPOTRACK_DB")
if _env_db:
    DB_PATH = Path(_env_db)
else:
    _local = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    DB_PATH = (Path(_local) / "OpoTrack" if _local else DATA_DIR) / "opotrack.db"
DB_URL = f"sqlite:///{DB_PATH}"

# Carpeta donde se guardan los archivos subidos (temario, requisitos), junto a
# la base de datos. Extensiones permitidas para las subidas.
ARCHIVOS_DIR = DB_PATH.parent / "archivos"
EXTENSIONES_DOCUMENTO = {".pdf", ".docx"}

FIXTURE_SUMARIO = FIXTURES_DIR / "sumario_ejemplo.json"
FIXTURE_BOPG = FIXTURES_DIR / "bopg_ejemplo.html"
FIXTURE_BOPS = FIXTURES_DIR / "bops_ejemplo.html"
FIXTURE_BOPCO = FIXTURES_DIR / "bopco_ejemplo.html"
FIXTURE_BOPJA = FIXTURES_DIR / "bopja_ejemplo.html"
FIXTURE_AYTBEN = FIXTURES_DIR / "aytben_ejemplo.html"
FIXTURE_AYTLOJA = FIXTURES_DIR / "aytloja_ejemplo.html"
FIXTURE_AYTHT = FIXTURES_DIR / "aytht_ejemplo.html"
FIXTURE_AYTANT = FIXTURES_DIR / "aytant_ejemplo.html"
FIXTURE_AYTMLG = FIXTURES_DIR / "aytmlg_ejemplo.html"
FIXTURE_AYTMOT = FIXTURES_DIR / "aytmot_ejemplo.html"
FIXTURE_AYTCOR = FIXTURES_DIR / "aytcor_ejemplo.html"
FIXTURE_AYTNER = FIXTURES_DIR / "aytner_ejemplo.html"
FIXTURE_BOPMA = FIXTURES_DIR / "bopma_ejemplo.csv"
FIXTURE_BOPMA_SUMARIO = FIXTURES_DIR / "bopma_sumario_ejemplo.html"
FIXTURE_BOJA = FIXTURES_DIR / "boja_ejemplo.xml"

# CSV de edictos del BOPMA (datos abiertos de la Diputación de Málaga) que el
# usuario descarga y coloca aquí; el conector lo lee si existe.
BOPMA_CSV = DATA_DIR / "bopma_edictos.csv"
# Sumario diario del BOP de Málaga (HTML servido; admite ?fecha=DD-MM-AAAA).
# Es la "vía del día": trae los edictos publicados ese día, sin el desfase del
# dataset de datos abiertos. El sitio solo responde a User-Agent de navegador.
BOPMA_SUMARIO = "https://www.bopmalaga.es/sumario.php"

# --- Fuente BOE ----------------------------------------------------------
# API oficial de datos abiertos. Requiere la cabecera Accept.
BOE_API_SUMARIO = "https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}"
BOE_ACCEPT = "application/json"
# Sección del sumario con las oposiciones ("II.B Oposiciones y concursos").
SECCION_OPOSICIONES = "2B"
# Identificador de tiempo de espera de las peticiones HTTP (segundos).
HTTP_TIMEOUT = 30

# Algunos boletines (p. ej. el BOJA) solo sirven el HTML completo a navegadores;
# a un User-Agent genérico devuelven una versión sin el contenido del sumario.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

# --- Límites del botón de búsqueda --------------------------------------
# Máximo de búsquedas por boletines al día. 0 = sin límite. Al alcanzarlo, el
# botón «Buscar boletines» se deshabilita hasta el día siguiente.
MAX_BUSQUEDAS_DIA = 100

# --- Código de la fuente principal --------------------------------------
FUENTE_BOE = "BOE"

# Clave de sesión de Flask (firma la cookie de sesión y los mensajes flash).
# Defínela con OPOTRACK_SECRET (.env). Si no existe, se genera una aleatoria en
# cada arranque: nunca hay una clave conocida de antemano, a cambio de que la
# sesión del navegador no sobrevive a un reinicio de la app.
SECRET_KEY = os.environ.get("OPOTRACK_SECRET") or secrets.token_hex(32)


# --- Notificaciones (Telegram) ------------------------------------------
# Avisos diarios de novedades por Telegram (comando `python cli.py notificar`,
# pensado para lanzarse desde el Programador de tareas de Windows). El token del
# bot y el chat de destino se leen del entorno (.env), NUNCA se guardan en git.
# Cómo obtenerlos: ver NOTIFICACIONES.md (bot con @BotFather + tu chat_id).
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
# Plantilla del endpoint de envío (no suele cambiar). Usa requests (ya incluido).
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
# Si es true, el aviso diario se manda también los días SIN novedades ("hoy nada
# nuevo"), útil para confirmar que la tarea programada sigue viva. Por defecto
# solo se avisa cuando hay algo. Actívalo con OPOTRACK_NOTIFICAR_SIN_NOVEDADES.
NOTIFICAR_SIN_NOVEDADES = os.environ.get(
    "OPOTRACK_NOTIFICAR_SIN_NOVEDADES", ""
).strip().lower() in {"1", "true", "si", "sí", "yes"}

# ¿Enviar además un 2º mensaje con los "no coincidentes" del día (anuncios del
# boletín que no casan con tus perfiles)? Por defecto sí; desactívalo con
# OPOTRACK_ENVIAR_NO_COINCIDENTES=0.
ENVIAR_NO_COINCIDENTES = os.environ.get(
    "OPOTRACK_ENVIAR_NO_COINCIDENTES", "1"
).strip().lower() not in {"0", "false", "no"}
# Tope de "no coincidentes" por aviso, para no mandar mensajes larguísimos los
# días cargados. 0 = sin tope. Configurable con OPOTRACK_MAX_NO_COINCIDENTES.
try:
    MAX_NO_COINCIDENTES = int(os.environ.get("OPOTRACK_MAX_NO_COINCIDENTES", "60"))
except ValueError:
    MAX_NO_COINCIDENTES = 60
