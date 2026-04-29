from datetime import datetime

from dp_utils import clear_screen, validate_phone_number, save_to_file, logger
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
    
    # Búsqueda en Google
    google = data.get("Búsqueda_en_Google", {})
    if not google.get("error"):
        print(f"\n{' BÚSQUEDA EN INTERNET ':=^70}")
        print(f"• Menciones encontradas: {google.get('Menciones', 0)}")
        if google.get("Enlaces_relacionados"):
            print(f"• Enlaces relevantes encontrados: {len(google['Enlaces_relacionados'])}")
    
    # Operadora
    carrier = data.get("Información_de_operadora", {})
    if not carrier.get("error"):
        print(f"\n{' INFORMACIÓN DE OPERADORA ':=^70}")
        print(f"• Nombre: {carrier.get('Operadora', 'Desconocida')}")
        if carrier.get('Sitio_web_oficial'):
            print(f"• Sitio web: {carrier['Sitio_web_oficial']}")
    
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
║{'Versión optimizada - Sin APIs externas':^70}║
╚{'═'*70}╝
""")
    
    while True:
        number = input("\nIngrese el número telefónico (con código de país, ej: +34123456789) o 'q' para salir: ").strip()
        
        if number.lower() == 'q':
            break
            
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
        
        # Guardar resultados
        txt_file, json_file = save_to_file(number, data)
        
        # Mostrar resumen
        display_results(data, number)
        logger.info(f"Análisis completado para {number}. Reportes generados: {txt_file}, {json_file}")
        
        print(f"\nReportes guardados en:")
        print(f"- Formato texto: {txt_file}")
        print(f"- Formato JSON: {json_file}\n")

if __name__ == "__main__":
    main()