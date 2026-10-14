# -*- coding: utf-8 -*-
"""
dp.py - CLI de Donkey Punch Phone Recognizer (v2).

Cambios v2 (auditoría):
- argparse: -n/-b/--region/--no-net/--max-queries/--workers. Sin args, modo
  interactivo como antes.
- sys.stdout/stderr reconfigurados a UTF-8 con errors="replace": los box-draw
  y acentos ya no revientan consolas cp1252.
- Reportes en reports/ (los escribe dp_utils).
- Ctrl+C limpio: cancela futuros pendientes y guarda lo que haya.
- display_results actualizado a las claves v2 del analizador (Búsqueda_web,
  Detección_VoIP, Mensajería, Número_gratuito, Resumen_de_riesgo, ...).
"""

import argparse
import json
import sys
from datetime import datetime

# Consolas Windows (cp1252) sin caracteres unicode: degradar, no romper.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dp_utils import (clear_screen, validate_phone_number, save_to_file,
                      logger, save_to_csv, save_to_html)
from dp_search import SearchClient
from phone_analyzer import PhoneNumberAnalyzer


def display_results(data: dict, number: str) -> None:
    """Muestra un resumen legible de los resultados v2."""
    print(f"""
╔{'═'*70}╗
║{'RESUMEN DE ANÁLISIS':^70}║
╠{'═'*70}╣
║ Número: {number:<59}║
║ Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<59}║
╚{'═'*70}╝
""")

    risk = data.get("Resumen_de_riesgo", {})
    if risk:
        print(f"{' RESUMEN DE RIESGO ':=^70}")
        print(f"• Puntuación: {risk.get('puntuación_riesgo', 'N/A')} "
              f"({risk.get('calificación', 'N/A')})")
        for s in (risk.get('señales') or [])[:6]:
            print(f"  - {s}")
        for r in (risk.get('recomendaciones') or []):
            print(f"  >> {r}")

    basic = data.get("Información_básica", {})
    if not basic.get("error"):
        print(f"\n{' INFORMACIÓN BÁSICA ':=^70}")
        print(f"• País: {basic.get('País', 'Desconocido')}")
        print(f"• Operadora: {basic.get('Operadora', 'Desconocida')}")
        print(f"• Tipo: {basic.get('Tipo de número', 'Desconocido')}")
        print(f"• Válido: {basic.get('Es válido número', 'N/A')}")
        print(f"• Zona horaria: {', '.join(basic.get('Zona horaria', []) or [])}")
        print(f"• Formato local: {basic.get('Formato local', 'N/A')}")

    loc = data.get("Ubicación_aproximada", {})
    if not loc.get("error"):
        print(f"\n{' UBICACIÓN APROXIMADA ':=^70}")
        print(f"• Región/Ciudad: {loc.get('Región_o_Ciudad', 'N/A')}")
        print(f"• Precisión estimada: {loc.get('Precisión', 'N/A')}")

    geo = data.get("Geolocalización_móvil", {})
    if not geo.get("error"):
        if geo.get("ignorado"):
            print(f"\n{' GEOLOCALIZACIÓN ':=^70}")
            print(f"• Ignorado: {geo.get('razon', 'N/A')}")
        else:
            print(f"\n{' GEOLOCALIZACIÓN MÓVIL ':=^70}")
            print(f"• Ciudad: {geo.get('ciudad_detectada', 'N/A')}")
            print(f"• Región: {geo.get('región', 'N/A')}")
            if geo.get('código_postal_sugerido'):
                print(f"• Código Postal (sugerido): {geo.get('código_postal_sugerido')}")
            if geo.get('ip_vinculada'):
                print(f"• IP especulativa: {geo.get('ip_vinculada')} "
                      f"({(geo.get('ip_ubicación') or {}).get('city', 'N/A')})")
            print(f"• Nivel de precisión: {geo.get('nivel_precisión', 'N/A')}")

    web = data.get("Búsqueda_web", {})
    if not web.get("error"):
        print(f"\n{' BÚSQUEDA EN INTERNET ':=^70}")
        if web.get("modo"):
            print(f"• {web['modo']}")
        else:
            print(f"• Motor: {web.get('Motor', 'N/A')} "
                  f"| Presupuesto: {web.get('Presupuesto', 'N/A')}")
            print(f"• Enlaces únicos: {web.get('Total_resultados', 0)}")
            for p in (web.get('Presencias_detectadas') or [])[:5]:
                print(f"  - {p}")
            for c in (web.get('Consultas') or []):
                estado = c.get('error') or f"{c.get('resultados', 0)} resultados"
                print(f"  [{c.get('motor') or '-'}] {c.get('consulta')} -> {estado}")

    msg = data.get("Mensajería", {})
    if not msg.get("error"):
        print(f"\n{' MENSAJERÍA ':=^70}")
        tg = msg.get('telegram', {})
        print(f"• Telegram: {tg.get('estado', 'N/A')}")
        if tg.get('alias_titulo'):
            print(f"  - Alias: {tg['alias_titulo']}")
        print(f"• WhatsApp (enlace, NO verificación): {msg.get('whatsapp', {}).get('enlace', 'N/A')}")

    reputation = data.get("Reputación_del_número", {})
    if not reputation.get("error"):
        print(f"\n{' REPUTACIÓN ':=^70}")
        print(f"• Calificación: {reputation.get('Calificación_de_reputación', 'Desconocida')}")
        print(f"• Factores de riesgo: {reputation.get('Factores_de_riesgo', 0)}")
        print(f"• Recomendación: {reputation.get('Recomendación', '')}")

    voip = data.get("Detección_VoIP", {})
    if not voip.get("error"):
        print(f"\n{' DETECCIÓN VoIP ':=^70}")
        print(f"• Es VoIP: {voip.get('es_voip', False)} "
              f"| Tipo de línea: {voip.get('tipo_de_línea', 'N/A')}")
        print(f"• Operadora reportada: {voip.get('operadora_reportada', 'N/A')}")
        for prov in (voip.get('proveedores_detectados') or []):
            print(f"  - {prov.get('proveedor', 'N/A')} ({prov.get('sitio_web', '')})")

    premium = data.get("Verificación_tarifa_premium", {})
    if not premium.get("error"):
        print(f"\n{' VERIFICACIÓN TARIFA ':=^70}")
        print(f"• Es Premium Rate: {premium.get('es_premium_rate', False)} "
              f"({premium.get('fuente_deteccion', 'N/A')})")
        if premium.get('es_premium_rate'):
            info = premium.get('informacion_tarifa', {})
            print(f"• Tipo: {info.get('tipo', 'N/A')}")
            print(f"• ADVERTENCIA: {info.get('recomendacion', '')}")

    toll = data.get("Número_gratuito", {})
    if not toll.get("error"):
        print(f"\n{' NÚMERO GRATUITO (TOLL FREE) ':=^70}")
        print(f"• Es Toll Free: {toll.get('es_toll_free', False)}")

    emails = data.get("Cruce_correos", {})
    if not emails.get("error"):
        print(f"\n{' CRUCE DE CORREOS ':=^70}")
        if emails.get("modo"):
            print(f"• {emails['modo']}")
        else:
            print(f"• Correos hallados (filtrados): {len(emails.get('correos_hallados', []) or [])}")
            for email in (emails.get('correos_hallados') or [])[:5]:
                print(f"  - {email}")
            if emails.get('correos_descartados_por_filtro'):
                print(f"• Descartados por filtro (ajenos al número): "
                      f"{emails['correos_descartados_por_filtro']}")
            for g in (emails.get('gravatar_con_avatar') or [])[:3]:
                print(f"• Gravatar con avatar: {g.get('email')}")
            print(f"• Patrones probables: {len(emails.get('patrones_probables', []) or [])}")

    email_patterns = data.get("Patrones_de_email", {})
    if not email_patterns.get("error") and email_patterns.get("patrones_generados"):
        print(f"\n{' PATRONES DE EMAIL ':=^70}")
        for email in (email_patterns.get("patrones_generados") or [])[:5]:
            print(f"  - {email}")
        rest = len(email_patterns.get("patrones_generados", [])) - 5
        if rest > 0:
            print(f"  ... y {rest} más")

    carrier_info = data.get("Información_de_operadora", {})
    if not carrier_info.get("error"):
        print(f"\n{' INFORMACIÓN DE OPERADORA ':=^70}")
        print(f"• Nombre: {carrier_info.get('Operadora', 'Desconocida')}")
        if carrier_info.get('Sitio web oficial'):
            print(f"• Sitio web: {carrier_info['Sitio web oficial']}")

    breaches = data.get("Bases_de_filtraciones", {})
    if not breaches.get("error"):
        print(f"\n{' BASES DE FILTRACIONES ':=^70}")
        for name, url in list((breaches.get('enlaces_verificacion') or {}).items())[:3]:
            print(f"  - {name}: {url}")
        for m in (breaches.get('posibles_menciones_web') or [])[:3]:
            print(f"  - web: {m.get('url', '')}")

    dorks = data.get("Google_Dorks", {})
    if not dorks.get("error"):
        print(f"\n{' GOOGLE DORKS ':=^70}")
        ejec = dorks.get("ejecutadas")
        if isinstance(ejec, list):
            for e in ejec[:3]:
                print(f"• [{e.get('categoria')}] {e.get('consulta')}")
                for r in (e.get('resultados') or [])[:2]:
                    print(f"    - {r.get('url', '')}")
        else:
            print(f"• {ejec}")
        manual = dorks.get('enlaces_manual') or {}
        print(f"• Dorks totales (manual incluido): {len(manual)}")

    footprint = data.get("Huella_de_operadora", {})
    if not footprint.get("error"):
        print(f"\n{' HUELLA DE OPERADORA ':=^70}")
        print(f"• Operadora: {footprint.get('operadora', 'N/A')}")
        infra = footprint.get('infraestructura', {})
        if infra:
            print(f"• Tipo de red: {infra.get('tipo_red', 'N/A')}")
            print(f"• Portabilidad: {infra.get('portabilidad', 'N/A')}")

    enrich = data.get("Enriquecimiento_API", {})
    if enrich:
        print(f"\n{' ENRIQUECIMIENTO API ':=^70}")
        print(f"• Disponible: {enrich.get('disponible', False)}")
        if enrich.get("razon"):
            print(f"• {enrich['razon']}")
        for c in (enrich.get('consultas') or []):
            print(f"  - {c.get('fuente')}: "
                  f"{c.get('error') or 'datos recibidos'}")

    if risk.get("calificación") in ("Elevado", "Crítico"):
        print(f"\n{'¡ADVERTENCIA!':!^70}")
        print("Este número acumula señales de riesgo (ver RESUMEN DE RIESGO).")

    print(f"\n{'═'*70}")
    print("Nota: detalles completos en los reportes de reports/ y en dp_analysis.log")


def _make_analyzer(number: str, args) -> PhoneNumberAnalyzer:
    return PhoneNumberAnalyzer(
        number,
        region=args.region,
        no_net=args.no_net,
        max_queries=args.max_queries,
        search_client=None,
    )


def run_single(number: str, args) -> dict:
    """Analiza un número, guarda reportes y devuelve los datos."""
    logger.info("Iniciando análisis para el número: %s", number)
    analyzer = _make_analyzer(number, args)
    if analyzer.parsed_number is None:
        print(f"✗ No se pudo parsear el número '{number}'.")
        return {}
    data = analyzer.analyze_all()
    txt_file, json_file = save_to_file(number, data)
    html_file = save_to_html(number, data)
    display_results(data, number)
    print(f"\nReportes guardados en:")
    print(f"- Formato texto: {txt_file}")
    print(f"- Formato JSON: {json_file}")
    print(f"- Formato HTML: {html_file}")
    logger.info("Análisis completado para %s: %s, %s, %s",
                number, txt_file, json_file, html_file)
    return data


def single_analysis(args) -> None:
    """Modo interactivo de un solo número."""
    while True:
        number = input(
            "\nIngrese el número telefónico (con código de país, ej: +34123456789) "
            "o 'q' para salir: ").strip()
        if number.lower() == 'q':
            break
        if number.lower() == 'b':
            batch_analysis(args)
            return
        if not validate_phone_number(number, args.region):
            print("\n¡Número no válido! Use formato internacional "
                  "(ej. +34123456789) o indique --region.\n")
            continue
        print("\nIniciando análisis... Progreso detallado en 'dp_analysis.log'.\n")
        run_single(number, args)
        print("\nPresione Enter para continuar o 'q' para salir...")
        if input().lower() == 'q':
            break


def _read_batch_file(path: str) -> list:
    numbers = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                n = line.strip()
                if n and not n.startswith("#"):
                    numbers.append(n)
    except OSError as e:
        print(f"✗ No se pudo leer el fichero de lote: {e}")
    return numbers


def batch_analysis(args, numbers: list = None) -> None:
    """Análisis por lotes: interactivo o desde fichero (-b fichero.txt)."""
    if numbers is None:
        print("\n" + "=" * 70)
        print("MODO ANÁLISIS POR LOTES (BATCH)")
        print("=" * 70)
        print("\nIngrese los números uno por línea. Línea en blanco para finalizar.")
        numbers = []
        while True:
            num = input("Número (o Enter para finalizar): ").strip()
            if not num:
                break
            if validate_phone_number(num, args.region):
                numbers.append(num)
                print(f"  ✓ {num} agregado")
            else:
                print(f"  ✗ {num} no válido, omitido")

    numbers = [n for n in numbers if validate_phone_number(n, args.region)]
    if not numbers:
        print("\nNo se ingresaron números válidos.")
        return

    print(f"\nAnalizando {len(numbers)} números...")
    results = []
    for i, number in enumerate(numbers, 1):
        print(f"\n[{i}/{len(numbers)}] Analizando {number}...")
        try:
            data = run_single(number, args)
            if data:
                results.append((number, data))
                print("  ✓ Completado")
            else:
                print("  ✗ Error al procesar")
        except KeyboardInterrupt:
            raise

    if not results:
        return

    csv_file = save_to_csv(results)
    print(f"\n✓ Reporte CSV guardado: {csv_file}")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_file = f"reports/batch_report_{timestamp}.json"
    combined = {num: data for num, data in results}
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(combined, f, indent=4, ensure_ascii=False, default=str)
    print(f"✓ Reporte JSON guardado: {json_file}")

    print(f"\n{' RESUMEN DEL LOTE ':=^70}")
    for number, data in results:
        basic = data.get("Información_básica", {})
        rep = data.get("Reputación_del_número", {})
        risk = data.get("Resumen_de_riesgo", {})
        geo = data.get("Geolocalización_móvil", {})
        geo_info = "" if geo.get("ignorado") else f" - Geo: {geo.get('ciudad_detectada', 'N/A')}"
        print(f"• {number}: {basic.get('País', 'N/A')} - "
              f"{basic.get('Operadora', 'N/A')} - "
              f"Riesgo: {risk.get('calificación', rep.get('Calificación_de_reputación', 'N/A'))}"
              f"{geo_info}")


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="dp.py",
        description="Donkey Punch Phone Recognizer - OSINT de números telefónicos.",
        epilog="Sin argumentos arranca el modo interactivo.")
    p.add_argument("-n", "--numero", action="append", default=[],
                   help="Número a analizar (formato internacional, ej. +34612345678). "
                        "Repetible: -n +34... -n +52...")
    p.add_argument("-b", "--batch", metavar="FICHERO",
                   help="Fichero de texto con un número por línea.")
    p.add_argument("--region", metavar="ISO",
                   help="Región de fallback para números sin '+', ej. ES.")
    p.add_argument("--no-net", action="store_true",
                   help="Solo módulos locales (sin ninguna petición de red).")
    p.add_argument("--max-queries", type=int, default=8,
                   help="Presupuesto de búsquedas web por número (default: 8).")
    p.add_argument("--workers", type=int, default=4,
                   help="Hilos de análisis en paralelo (default: 4).")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.numero or args.batch:
        numbers = list(args.numero)
        if args.batch:
            numbers.extend(_read_batch_file(args.batch))
        valid, invalid = [], []
        for n in numbers:
            (valid if validate_phone_number(n, args.region) else invalid).append(n)
        for n in invalid:
            print(f"✗ Número no válido, omitido: {n}")
        if not valid:
            print("No hay números válidos que analizar.")
            return 1
        if len(valid) == 1:
            run_single(valid[0], args)
        else:
            batch_analysis(args, valid)
        return 0

    clear_screen()
    print(f"""
╔{'═'*70}╗
║{'ANALIZADOR DE NÚMEROS TELEFÓNICOS (OSINT)':^70}║
╠{'═'*70}╣
║{'Versión con esteroides - Navaja Suiza de Reconocimiento':^70}║
╠{'═'*70}╣
║{'Opciones: [1] Análisis individual  [2] Análisis por lotes (batch)':^70}║
╚{'═'*70}╝
""")
    mode = input("\nSeleccione modo (1 o 2, Enter para individual): ").strip() or "1"
    if mode == "2":
        batch_analysis(args)
    else:
        single_analysis(args)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n[!] Análisis interrumpido por el usuario (Ctrl+C).")
        logger.info("Análisis interrumpido por el usuario (Ctrl+C).")
        sys.exit(130)
