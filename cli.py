#!/usr/bin/env python3
"""Interfaz de línea de comandos de OpoTrack (para probar el núcleo).

Uso típico:
    python cli.py init-db          # crea la base de datos
    python cli.py seed             # carga fuentes, catálogos y perfiles
    python cli.py buscar --demo    # busca sobre el sumario de ejemplo (sin red)
    python cli.py buscar --fecha 20260804   # búsqueda real en el BOE (requiere internet)
    python cli.py bandeja          # muestra la bandeja de novedades
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime

from sqlalchemy import select

from opotrack import config, db, motor
from opotrack import seed as seed_mod
from opotrack.fuentes.base import SumarioNoDisponible
from opotrack.fuentes.boe import ConectorBOE
from opotrack.models import Candidato
from opotrack.motor import LimiteBusquedasExcedido


def cmd_init_db(args) -> None:
    db.init_db()
    print(f"Base de datos lista en: {config.DB_PATH}")


def cmd_seed(args) -> None:
    db.init_db()
    with db.get_session() as s:
        creados = seed_mod.seed(s)
    print("Datos iniciales cargados:", ", ".join(f"{k}={v}" for k, v in creados.items()))


def _fetch_demo(fecha):
    with open(config.FIXTURE_SUMARIO, encoding="utf-8") as f:
        return json.load(f)


def cmd_buscar(args) -> None:
    conector = ConectorBOE()
    fetch_fn = _fetch_demo if args.demo else None
    fecha = args.fecha or date.today().strftime("%Y%m%d")
    etiqueta = "demo" if args.demo else fecha
    with db.get_session() as s:
        try:
            resumen = motor.buscar(
                s, conector, fecha,
                fetch_fn=fetch_fn,
                ignorar_limite=args.ignorar_limite or args.demo,
            )
        except SumarioNoDisponible as e:
            print(f"Aviso: {e}")
            return
        except LimiteBusquedasExcedido as e:
            print(f"Límite alcanzado: {e}")
            return
    print(
        f"Búsqueda [{etiqueta}]: {resumen['anuncios']} anuncios en la sección de oposiciones · "
        f"{resumen['nuevos']} nuevos en bandeja · {resumen['ya_vistos']} ya conocidos · "
        f"{resumen['sin_match']} sin coincidencia."
    )


def cmd_bandeja(args) -> None:
    hoy = date.today()
    with db.get_session() as s:
        candidatos = s.scalars(
            select(Candidato)
            .where(Candidato.estado == "pendiente")
            .order_by(Candidato.score.desc(), Candidato.fecha_entrada_bandeja.asc())
        ).all()
        if not candidatos:
            print("Bandeja vacía.")
            return
        print(f"Bandeja de novedades ({len(candidatos)} pendientes):\n")
        for c in candidatos:
            atrasada = "  <-- ATRASADA" if c.fecha_entrada_bandeja.date() < hoy else ""
            titulo = (c.titulo or "")[:72]
            print(f"  [{(c.nivel_confianza or '?'):>5}] {c.referencia_oficial}  {titulo}")
            print(
                f"          perfil: {c.perfil_coincidente}  |  "
                f"entró: {c.fecha_entrada_bandeja:%Y-%m-%d}{atrasada}"
            )


def cmd_diag_boja(args) -> None:
    """Diagnóstico del conector BOJA con datos reales (requiere internet)."""
    from opotrack.fuentes.boja import ConectorBOJA, RSS_OPOSICIONES

    c = ConectorBOJA()
    print(f"Feed RSS: {RSS_OPOSICIONES}")
    xml = c.fetch_rss()
    print(f"Longitud del XML: {len(xml)} caracteres")
    print("--- primeros 1200 caracteres del XML ---")
    print(xml[:1200])
    print("--- fin muestra ---")
    anuncios = c.parse_rss(xml)
    print(f"Items parseados: {len(anuncios)}")
    for a in anuncios[:6]:
        print(f"  - {a.referencia_oficial} | {(a.fecha_publicacion)} | {(a.titulo or '')[:70]}")


def cmd_notificar(args) -> None:
    """Busca novedades y las envía por Telegram (para la tarea programada).

    Envía hasta dos mensajes: (1) la bandeja —lo que casa con tus perfiles— y
    (2) los "no coincidentes" del boletín —lo que el filtro deja fuera—, salvo
    que se desactive. Solo marca la bandeja como avisada tras enviarla (si el
    envío falla, se reintenta en la siguiente ejecución). Con --test solo
    comprueba la conexión.
    """
    from opotrack import notificaciones as notif
    from opotrack.models import Fuente, ResultadoBusqueda

    if args.test:
        try:
            notif.enviar_telegram(notif.mensaje_prueba())
            print("Mensaje de prueba enviado correctamente.")
        except notif.TelegramNoConfigurado as e:
            print(f"Telegram no configurado: {e}")
        except notif.EnvioFallido as e:
            print(f"No se pudo enviar el mensaje de prueba: {e}")
        return

    if not notif.hay_config():
        print(
            "Telegram no configurado: define TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID "
            "en el .env (ver NOTIFICACIONES.md)."
        )
        return

    enviar_no_coin = config.ENVIAR_NO_COINCIDENTES and not getattr(
        args, "sin_no_coincidentes", False
    )
    hoy = date.today()
    fecha_legible = hoy.strftime("%d/%m/%Y")
    db.init_db()
    algo_enviado = False
    inicio_busqueda = datetime.now()   # solo se avisan los no coincidentes nuevos desde aquíe
    with db.get_session() as s:
        if not args.sin_buscar:
            try:
                resumen = motor.buscar_fuentes_activas(
                    s, hoy.strftime("%Y%m%d"), ignorar_limite=True
                )
                print(
                    f"Búsqueda: {resumen['nuevos']} nuevos · "
                    f"{resumen['ya_vistos']} ya conocidos · "
                    f"{resumen['sin_match']} sin coincidencia."
                )
            except Exception as e:  # noqa: BLE001 (no romper el aviso por un fallo de red)
                print(f"Aviso: la búsqueda falló ({e}); aviso de lo que ya hubiera.")
            # Vuelca a la BBDD lo que la búsqueda acaba de insertar, para que los
            # SELECT de abajo lo vean (la sesión usa autoflush=False).
            s.flush()

        # --- Mensaje 1: bandeja (novedades que casan con los perfiles) ---
        candidatos = s.scalars(
            select(Candidato)
            .where(
                Candidato.estado == "pendiente",
                Candidato.fecha_notificacion.is_(None),
            )
            .order_by(Candidato.score.desc(), Candidato.fecha_entrada_bandeja.asc())
        ).all()
        if candidatos:
            try:
                notif.enviar_mensajes(notif.construir_mensaje(candidatos, fecha_legible))
                ahora = datetime.now()
                for c in candidatos:
                    c.fecha_notificacion = ahora
                algo_enviado = True
                print(f"Bandeja: {len(candidatos)} novedad(es) enviadas.")
            except notif.EnvioFallido as e:
                print(f"No se pudo enviar la bandeja ({e}); no se marcan (se reintentará).")
        else:
            print("Bandeja: sin novedades nuevas.")

        # --- Mensaje 2: no coincidentes de la última búsqueda ---
        # --- Mensaje 2: no coincidentes NUEVOS de esta búsqueda ---
        if enviar_no_coin:
            no_coin = s.scalars(
                select(ResultadoBusqueda)
                .where(
                    ResultadoBusqueda.clasificacion == "sin_match",
                    ResultadoBusqueda.momento >= inicio_busqueda,
                )
                .order_by(
                    ResultadoBusqueda.fuente_codigo, ResultadoBusqueda.referencia_oficial
                )
            ).all()
            if no_coin:
                nombres = {f.codigo: f.nombre for f in s.scalars(select(Fuente)).all()}
                try:
                    notif.enviar_mensajes(
                        notif.construir_mensaje_no_coincidentes(
                            no_coin, fecha_legible, nombres, limite=config.MAX_NO_COINCIDENTES
                        )
                    )
                    algo_enviado = True
                    print(f"No coincidentes: {len(no_coin)} enviados.")
                except notif.EnvioFallido as e:
                    print(f"No se pudieron enviar los no coincidentes: {e}")
            else:
                print("No coincidentes: ninguno nuevo en esta búsqueda.")

        # --- Días sin nada que enviar ---
        if not algo_enviado:
            if config.NOTIFICAR_SIN_NOVEDADES:
                try:
                    notif.enviar_telegram(notif.mensaje_sin_novedades(fecha_legible))
                    print("Nada que enviar: enviado el aviso de 'hoy nada nuevo'.")
                except notif.EnvioFallido as e:
                    print(f"Nada que enviar y no se pudo avisar: {e}")
            else:
                print("Nada que enviar (ni novedades ni no coincidentes); no se manda mensaje.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="opotrack", description="OpoTrack — núcleo (CLI de pruebas)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="crea la base de datos").set_defaults(func=cmd_init_db)
    sub.add_parser("seed", help="carga datos iniciales").set_defaults(func=cmd_seed)

    b = sub.add_parser("buscar", help="ejecuta una búsqueda")
    b.add_argument("--fecha", help="fecha AAAAMMDD (por defecto, hoy)")
    b.add_argument("--demo", action="store_true", help="usa el sumario de ejemplo (sin red)")
    b.add_argument("--ignorar-limite", dest="ignorar_limite", action="store_true",
                   help="salta el límite diario de búsquedas")
    b.set_defaults(func=cmd_buscar)

    sub.add_parser("bandeja", help="muestra la bandeja de novedades").set_defaults(func=cmd_bandeja)
    sub.add_parser("diag-boja", help="diagnóstico del conector BOJA (requiere internet)").set_defaults(func=cmd_diag_boja)

    pn = sub.add_parser("notificar", help="busca y envía las novedades por Telegram")
    pn.add_argument("--sin-buscar", dest="sin_buscar", action="store_true",
                    help="no busca; solo avisa de los candidatos pendientes sin notificar")
    pn.add_argument("--test", action="store_true",
                    help="envía un mensaje de prueba para comprobar la conexión")
    pn.add_argument("--sin-no-coincidentes", dest="sin_no_coincidentes",
                    action="store_true",
                    help="no envía el 2º mensaje con los anuncios que no casan con tus perfiles")
    pn.set_defaults(func=cmd_notificar)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
