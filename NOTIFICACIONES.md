# OpoTrack — Avisos diarios por Telegram

Recibe en el móvil, cada mañana, un resumen de las **convocatorias nuevas** que
encajan con tus perfiles, sin abrir la app. El aviso lo genera el comando
`python cli.py notificar`, que:

1. busca en todas las fuentes activas del día,
2. coge las novedades de la bandeja que aún no te ha avisado,
3. te las manda por Telegram y las marca como avisadas (para no repetirlas).

Recibes **dos mensajes** cada día:

- **Bandeja**: las convocatorias que casan con tus perfiles (lo importante).
- **No coincidentes**: el resto de anuncios de oposiciones del boletín de hoy que
  el filtro deja fuera, por si quieres repasarlos. Se puede desactivar o limitar
  (ver abajo).

Pensado para lanzarse solo con el **Programador de tareas de Windows**.

---

## 1. Crear el bot de Telegram (2 minutos)

1. En Telegram, abre un chat con **@BotFather**.
2. Envía `/newbot` y sigue los pasos (un nombre y un usuario que acabe en `bot`).
3. BotFather te da un **token** con esta pinta:
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`. Guárdalo.

## 2. Obtener tu chat_id

1. Abre un chat con **tu nuevo bot** y envíale cualquier mensaje (p. ej. "hola").
   > Imprescindible: un bot no puede escribirte hasta que tú le hablas primero.
2. En el navegador, visita (con tu token):
   `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
3. Busca `"chat":{"id":123456789,...}`. Ese número es tu **chat_id**.
   Alternativa: escribe a **@userinfobot**, que te da tu id directamente.

## 3. Configurar el .env

Abre el archivo `.env` de la carpeta de OpoTrack y completa estas líneas:

```
TELEGRAM_BOT_TOKEN=123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789
```

El `.env` no se sube a git (está en `.gitignore`): tu token queda solo en tu equipo.

## 4. Probar que funciona

Desde la carpeta de OpoTrack, en una consola:

```
python cli.py notificar --test
```

Debe llegarte un mensaje de confirmación al móvil. Para una prueba real (busca y
te avisa de lo pendiente):

```
python cli.py notificar
```

## 5. Programar el aviso diario

### Opción A — Importar la tarea ya hecha (rápida)

`OpoTrack-Notificar.xml` es una **plantilla**: trae el usuario `TU_USUARIO` y la
ruta `C:\ruta\a\OpoTrack`, que tienes que sustituir por los tuyos.

1. Abre el **Programador de tareas** (búscalo en Inicio).
2. Menú **Acción → Importar tarea…**
3. Elige `OpoTrack-Notificar.xml` de la carpeta de OpoTrack.
4. Cambia antes de aceptar:
   - **General → Cambiar usuario o grupo…**: tu usuario de Windows (en lugar de
     `TU_USUARIO`).
   - **Desencadenadores**: la hora (viene a las **08:00** cada día).
   - **Acciones → Editar**: la ruta real a tu `notificar.bat` y, en *"Iniciar
     en"*, la carpeta de OpoTrack.

   Si el asistente rechaza la importación por el usuario, abre antes el XML con
   el Bloc de notas, sustituye `TU_USUARIO` y las dos rutas, y guárdalo
   manteniendo la codificación (UTF-16).
5. Si te lo ofrece, marca *"Ejecutar tanto si el usuario inició sesión como si no"*.

> El XML ya trae activadas dos cosas clave: **"Activar el equipo para ejecutar
> esta tarea"** (lo despierta de suspensión) y **"Ejecutar en cuanto sea posible
> si se perdió un inicio programado"** (si el PC estaba apagado a las 8:00, avisa
> en cuanto lo enciendas).

### Opción B — Crear la tarea a mano

Crear tarea básica → diaria a las 8:00 → acción *"Iniciar un programa"* →
Programa: `notificar.bat`, y en *"Iniciar en"* la carpeta de OpoTrack. Luego, en
las propiedades: pestaña **Condiciones** → *"Activar el equipo para ejecutar esta
tarea"*; pestaña **Configuración** → *"Ejecutar la tarea lo antes posible tras un
inicio programado perdido"*.

## 6. Que avise aunque no estés delante

Tres escenarios, de menos a más independiente:

- **PC encendido o en suspensión**: con "Activar el equipo…" (ya marcado), la
  tarea lo despierta, avisa y listo. Nada más que hacer.
- **PC apagado del todo**: Windows no puede encenderse solo. Activa en la
  **BIOS/UEFI** el encendido por reloj (*"Power On by RTC Alarm"*, *"Wake on
  RTC"* o *"Resume by Alarm"*) a tu hora. El PC arranca solo, corre la tarea y
  —si descomentas `shutdown /h` en `notificar.bat`— se hiberna después.
- **Independencia total** (de viaje, días sin tocar el PC): esa es la "Ruta B"
  (nube), que se puede montar encima de esto más adelante.

Para que "Activar el equipo" funcione: **Opciones de energía → Cambiar la
configuración del plan → Cambiar la configuración avanzada de energía → Suspender
→ Permitir temporizadores de reactivación → Habilitar**.

## Comandos y archivos

- `python cli.py notificar` — busca y avisa de las novedades (lo que usa la tarea).
- `python cli.py notificar --sin-buscar` — no busca; solo avisa de lo pendiente.
- `python cli.py notificar --test` — manda un mensaje de prueba.
- `python cli.py notificar --sin-no-coincidentes` — solo la bandeja (sin el 2º mensaje).
- Log de la tarea: `logs\notificar.log` en la carpeta de OpoTrack.

Opciones del `.env`:

- `OPOTRACK_ENVIAR_NO_COINCIDENTES=0` — desactiva el 2º mensaje (los «no
  coincidentes»). Por defecto está activado (`1`).
- `OPOTRACK_MAX_NO_COINCIDENTES=60` — máximo de «no coincidentes» por aviso, para
  no recibir mensajes larguísimos los días cargados (`0` = sin tope).

- `OPOTRACK_NOTIFICAR_SIN_NOVEDADES=1` — recibe también un aviso los días sin
  novedades (para saber que la tarea sigue viva). Por defecto, `0`.

## Problemas frecuentes

- **No llega el `--test`**: comprueba que escribiste primero al bot (paso 2) y
  que el token y el chat_id del `.env` son correctos. El comando te muestra el
  error exacto de Telegram (p. ej. "chat not found").
- **La tarea no arranca**: mira la pestaña **Historial** de la tarea. Si no
  encuentra `python`, edita `notificar.bat` y pon la ruta completa a tu Python
  (la ves con `where python`).
- **Se ejecuta pero no avisa**: seguramente no había novedades. Pon
  `OPOTRACK_NOTIFICAR_SIN_NOVEDADES=1` para confirmarlo, o revisa el log.
