from datetime import datetime
import sys
import csv
import json

from dp_utils import clear_screen, validate_phone_number, save_to_file, logger, save_to_csv, save_to_html
from phone_analyzer import PhoneNumberAnalyzer

# La función display_results se mantiene, pero se podría considerar una interfaz de usuario más avanzada para la visualización de datos de investigación.
def display_results(data, number):
    """Muestra los resultados de forma organizada"""
    clear_screen()
    print(f"""
╔{'═'*70}╗
║{'RESUMEN DE ANÁLISIS':^70}║
╠{'═'*70}╣
║ Número: {number:<59}║
║ Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<59}║
╚{'═'*70}╝
""")
    
    # Información básica
    basic = data.get("Información_básica", {})
    if not basic.get("error"):
        print(f"\n{' INFORMACIÓN BÁSICA ':=^70}")
        print(f"• País: {basic.get('País', 'Desconocido')}")
        print(f"• Operadora: {basic.get('Operadora', 'Desconocida')}")
        print(f"• Tipo: {basic.get('Tipo de número', 'Desconocido')}")
        print(f"• Zona horaria: {', '.join(basic.get('Zona horaria', []))}")
        print(f"• Formato local: {basic.get('Formato local', 'N/A')}")
    
    # Ubicación
    loc = data.get("Ubicación_aproximada", {})
    if not loc.get("error"):
        print(f"\n{' UBICACIÓN APROXIMADA ':=^70}")
        print(f"• Región/Ciudad: {loc.get('Región_o_Ciudad', 'N/A')}")
        print(f"• Precisión estimada: {loc.get('Precisión', 'N/A')}")

    # Reputación
    reputation = data.get("Reputación_del_número", {})
    if not reputation.get("error"):
        print(f"\n{' REPUTACIÓN ':=^70}")
        print(f"• Calificación: {reputation.get('Calificación_de_reputación', 'Desconocida')}")
        print(f"• Factores de riesgo: {reputation.get('Factores_de_riesgo', 0)}")
        if reputation.get('Patrones_sospechosos') != "Ninguno detectado":
            print(f"• Patrones detectados: {len(reputation.get('Patrones_sospechosos', []))}")
        print(f"• Recomendación: {reputation.get('Recomendación', '')}")
    
    # Proveedores VoIP
    voip = data.get("Proveedores_VoIP", {})
    if not voip.get("error"):
        print(f"\n{' PROVEEDORES VoIP ':=^70}")
        print(f"• Es VoIP: {voip.get('es_voip', False)}")
        if voip.get('proveedores_detectados'):
            for prov in voip['proveedores_detectados']:
                print(f"  - {prov.get('proveedor', 'N/A')}: {prov.get('tipo', '')}")
        print(f"• Riesgo VoIP: {voip.get('riesgo_voip', 'N/A')}")
    
    # Verificación Premium Rate
    premium = data.get("Verificación_tarifa_premium", {})
    if not premium.get("error"):
        print(f"\n{' VERIFICACIÓN TARIFA ':=^70}")
        print(f"• Es Premium Rate: {premium.get('es_premium_rate', False)}")
        if premium.get('es_premium_rate'):
            info = premium.get('informacion_tarifa', {})
            print(f"• Tipo: {info.get('tipo', 'N/A')}")
            print(f"• ⚠️  ADVERTENCIA: {info.get('recomendacion', '')}")
    
    # Patrones de email
    emails = data.get("Patrones_de_email", {})
    if not emails.get("error") and emails.get("patrones_generados"):
        print(f"\n{' PATRONES DE EMAIL ':=^70}")
        print(f"• Total patrones: {emails.get('total_patrones', 0)}")
        for email in emails.get("patrones_generados", [])[:5]:
            print(f"  - {email}")
        if len(emails.get("patrones_generados", [])) > 5:
            print(f"  ... y {len(emails.get('patrones_generados', [])) - 5} más")
    
    # Búsqueda en Google
    google = data.get("Búsqueda_en_Google", {})
    if not google.get("error"):
        print(f"\n{' BÚSQUEDA EN INTERNET ':=^70}")
        print(f"• Menciones encontradas: {google.get('Menciones', 0)}")
        if google.get("Enlaces_relacionados"):
            print(f"• Enlaces relevantes encontrados: {len(google['Enlaces_relacionados'])}")
    
    # Operadora
    carrier_info = data.get("Información_de_operadora", {})
    if not carrier_info.get("error"):
        print(f"\n{' INFORMACIÓN DE OPERADORA ':=^70}")
        print(f"• Nombre: {carrier_info.get('Operadora', 'Desconocida')}")
        if carrier_info.get('Sitio web oficial'):
            print(f"• Sitio web: {carrier_info['Sitio web oficial']}")
    
    # Bases de filtraciones
    breaches = data.get("Bases_de_filtraciones", {})
    if not breaches.get("error"):
        print(f"\n{' BASES DE FILTRACIONES ':=^70}")
        print(f"• Bases consultadas: {', '.join(breaches.get('bases_consultadas', []))}")
        if breaches.get("enlaces_verificacion"):
            print("• Enlaces de verificación:")
            for source, url in list(breaches["enlaces_verificacion"].items())[:3]:
                print(f"  - {source}: {url}")
    
    # Google Dorks avanzados
    dorks = data.get("Google_Dorks_avanzados", {})
    if not dorks.get("error"):
        print(f"\n{' GOOGLE DORKS AVANZADOS ':=^70}")
        for category, dork_list in list(dorks.items())[:3]:
            print(f"• {category.replace('_', ' ').title()}:")
            for dork in dork_list[:2]:
                print(f"  {dork}")
    
    # Huella de operadora
    footprint = data.get("Huella_de_operadora", {})
    if not footprint.get("error"):
        print(f"\n{' HUELLA DE OPERADORA ':=^70}")
        print(f"• Operadora: {footprint.get('operadora', 'N/A')}")
        infra = footprint.get('infraestructura', {})
        if infra:
            print(f"• Tipo de red: {infra.get('tipo_red', 'N/A')}")
            print(f"• Portabilidad: {infra.get('portabilidad', 'N/A')}")
    
    # Advertencias
    if reputation.get("Calificación_de_reputación", "") in ["Alta", "Muy Alta"]:
        print(f"\n{'¡ADVERTENCIA!':!^70}")
        print("Este número muestra características sospechosas que podrían indicar:")
        print("- Número de spam/scam - Número virtual - Servicio premium costoso")
    
    print(f"\n{'═'*70}")
    print("Nota: Para detalles completos, consulte los archivos de reporte generados")

def main():
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
        batch_analysis()
    else:
        single_analysis()

def single_analysis():
    """Análisis de un solo número."""
    while True:
        number = input("\nIngrese el número telefónico (con código de país, ej: +34123456789) o 'q' para salir: ").strip()
        
        if number.lower() == 'q':
            break
        
        if number.lower() == 'b':
            batch_analysis()
            return
        
        logger.info(f"Iniciando análisis para el número: {number}")
        if not validate_phone_number(number):
            logger.warning(f"Número '{number}' no válido. Solicitando reingreso.")
            print("\n¡Número no válido! Por favor ingrese un número válido con código de país (ej. +34123456789).\n")
            continue
        
        print("\nIniciando análisis... Esto puede tomar unos minutos. Consulte 'dp_analysis.log' para el progreso detallado.\n")
        
        analyzer = PhoneNumberAnalyzer(number)
        if analyzer.parsed_number is None:
            logger.error(f"Fallo al inicializar PhoneNumberAnalyzer para '{number}'.")
            print("Error: No se pudo inicializar el analizador para este número. Asegúrese de que el formato sea correcto y reintente.")
            continue
        
        data = analyzer.analyze_all()
        
        # Guardar resultados en múltiples formatos
        txt_file, json_file = save_to_file(number, data)
        html_file = save_to_html(number, data)
        
        # Mostrar resumen
        display_results(data, number)
        logger.info(f"Análisis completado para {number}. Reportes generados: {txt_file}, {json_file}, {html_file}")
        
        print(f"\nReportes guardados en:")
        print(f"- Formato texto: {txt_file}")
        print(f"- Formato JSON: {json_file}")
        print(f"- Formato HTML: {html_file}")
        print(f"\nPresione Enter para continuar o 'q' para salir...")
        if input().lower() == 'q':
            break

def batch_analysis():
    """Análisis por lotes de múltiples números."""
    print("\n" + "="*70)
    print("MODO ANÁLISIS POR LOTES (BATCH)")
    print("="*70)
    print("\nIngrese los números uno por línea. Línea en blanco para finalizar.")
    print("Ejemplo:")
    print("+34612345678")
    print("+5491155512345")
    print("+12125551234")
    print()
    
    numbers = []
    while True:
        num = input("Número (o Enter para finalizar): ").strip()
        if not num:
            break
        if validate_phone_number(num):
            numbers.append(num)
            print(f"  ✓ {num} agregado")
        else:
            print(f"  ✗ {num} no válido, omitido")
    
    if not numbers:
        print("\nNo se ingresaron números válidos.")
        return
    
    print(f"\nAnalizando {len(numbers)} números...")
    results = []
    
    for i, number in enumerate(numbers, 1):
        print(f"\n[{i}/{len(numbers)}] Analizando {number}...")
        analyzer = PhoneNumberAnalyzer(number)
        if analyzer.parsed_number:
            data = analyzer.analyze_all()
            results.append((number, data))
            print(f"  ✓ Completado")
        else:
            print(f"  ✗ Error al procesar")
    
    if results:
        # Guardar reporte CSV
        csv_file = save_to_csv(results)
        print(f"\n✓ Reporte CSV guardado: {csv_file}")
        
        # Guardar reporte JSON combinado
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_file = f"batch_report_{timestamp}.json"
        combined = {num: data for num, data in results}
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(combined, f, indent=4, ensure_ascii=False)
        print(f"✓ Reporte JSON guardado: {json_file}")
        
        # Mostrar resumen
        print(f"\n{' RESUMEN DEL LOTE ':=^70}")
        for number, data in results:
            basic = data.get("Información_básica", {})
            rep = data.get("Reputación_del_número", {})
            print(f"• {number}: {basic.get('País', 'N/A')} - {basic.get('Operadora', 'N/A')} - Riesgo: {rep.get('Calificación_de_reputación', 'N/A')}")

if __name__ == "__main__":
    main()