import os
import json
import csv
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import random
import phonenumbers
import logging
import requests
from typing import Optional, Dict, Any

# Configuración básica del logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("dp_analysis.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def make_request(url: str, method: str = "GET", headers: Optional[Dict] = None, 
                timeout: int = 10, max_retries: int = 3) -> Optional[requests.Response]:
    """
    Realiza una petición HTTP con reintentos y rotación de User-Agents.
    
    Args:
        url: URL a consultar
        method: Método HTTP (GET, POST, etc.)
        headers: Headers adicionales
        timeout: Tiempo de espera en segundos
        max_retries: Número máximo de reintentos
        
    Returns:
        Response object o None si falla
    """
    from phone_data import USER_AGENTS
    
    for attempt in range(max_retries):
        try:
            request_headers = headers or {}
            if "User-Agent" not in request_headers:
                request_headers["User-Agent"] = random.choice(USER_AGENTS)
            
            response = requests.request(method, url, headers=request_headers, timeout=timeout)
            
            if response.status_code == 429:
                wait_time = 2 ** attempt + random.uniform(0, 1)
                logger.warning(f"Rate limited. Esperando {wait_time:.2f}s antes de reintentar...")
                time.sleep(wait_time)
                continue
                
            return response
        except Exception as e:
            logger.error(f"Error en make_request (intento {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(1, 3))
    
    return None

def check_url_status(url: str) -> Dict[str, Any]:
    """
    Verifica el estado de una URL sin descargar todo el contenido.
    
    Args:
        url: URL a verificar
        
    Returns:
        Diccionario con el estado de la URL
    """
    try:
        response = make_request(url, method="HEAD", timeout=5)
        if response:
            return {
                "url": url,
                "status": response.status_code,
                "accesible": response.status_code < 400,
                "content_type": response.headers.get("Content-Type", "Unknown")
            }
        return {"url": url, "status": "Error", "accesible": False}
    except Exception as e:
        return {"url": url, "status": "Error", "accesible": False, "error": str(e)}

def clear_screen():
    """Limpia la pantalla de la consola."""
    os.system('cls' if os.name == 'nt' else 'clear')

def validate_phone_number(number: str) -> bool:
    """
    Valida el número telefónico con mayor precisión usando la librería phonenumbers.
    
    Args:
        number: El número de teléfono a validar.
        
    Returns:
        True si el número es válido, False en caso contrario.
    """
    try:
        parsed_number = phonenumbers.parse(number, None)
        return phonenumbers.is_valid_number(parsed_number)
    except Exception as e:
        logger.warning(f"Error al validar el número '{number}': {e}")
        return False

def save_to_file(number: str, data: dict) -> tuple[str, str]:
    """
    Guarda los resultados del análisis en formato JSON y texto legible.
    
    Args:
        number: El número de teléfono analizado.
        data: Un diccionario con todos los resultados del análisis.
        
    Returns:
        Una tupla con los nombres de archivo del reporte de texto y JSON.
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_filename = f"reporte_{number.replace('+', '')}_{timestamp}.json"
    txt_filename = f"reporte_{number.replace('+', '')}_{timestamp}.txt"
    logger.info(f"Guardando resultados para {number} en {txt_filename} y {json_filename}")
    
    # Guardar en JSON
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    
    # Guardar en texto legible
    with open(txt_filename, 'w', encoding='utf-8') as f:
        f.write(f"╔{'═'*70}╗\n")
        f.write(f"║{'ANÁLISIS DE NÚMERO TELEFÓNICO':^70}║\n")
        f.write(f"╠{'═'*70}╣\n")
        f.write(f"║ Número: {number:<59}║\n")
        f.write(f"║ Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<59}║\n")
        f.write(f"╚{'═'*70}╝\n\n")
        
        for section, content in data.items():
            f.write(f"■{' ' + section.upper() + ' ':{'■'}^70}\n\n")
            
            if isinstance(content, dict):
                for key, value in content.items():
                    if isinstance(value, dict):
                        f.write(f"  {key}:\n")
                        for subkey, subvalue in value.items():
                            f.write(f"    {subkey}: {subvalue}\n")
                    elif isinstance(value, list):
                        f.write(f"  {key}:\n")
                        for item in value:
                            f.write(f"    - {item}\n")
                    else:
                        f.write(f"  {key}: {value}\n")
                    f.write("\n")
            elif isinstance(content, list):
                for item in content:
                    f.write(f"- {item}\n")
                f.write("\n")
            else:
                f.write(f"{content}\n\n")
        
        f.write("\n" + "═"*70 + "\n")
        f.write("FIN DEL REPORTE\n")
    
    return txt_filename, json_filename

def save_to_csv(numbers_data: list, filename: str = None) -> str:
    """
    Guarda múltiples análisis en formato CSV para comparación.
    
    Args:
        numbers_data: Lista de tuplas (number, data)
        filename: Nombre del archivo (opcional)
        
    Returns:
        Nombre del archivo guardado
    """
    if not filename:
        filename = f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    with open(filename, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Número', 'País', 'Operadora', 'Tipo', 'Reputación', 'Riesgo VoIP', 'Es Premium'])
        
        for number, data in numbers_data:
            basic = data.get("Información_básica", {})
            reputation = data.get("Reputación_del_número", {})
            voip = data.get("Proveedores_VoIP", {})
            premium = data.get("Verificación_tarifa_premium", {})
            
            writer.writerow([
                number,
                basic.get('País', 'N/A'),
                basic.get('Operadora', 'N/A'),
                basic.get('Tipo de número', 'N/A'),
                reputation.get('Calificación_de_reputación', 'N/A'),
                voip.get('riesgo_voip', 'N/A'),
                premium.get('es_premium_rate', False)
            ])
    
    logger.info(f"Reporte batch guardado en {filename}")
    return filename

def save_to_html(number: str, data: dict) -> str:
    """
    Genera un reporte HTML interactivo.
    
    Args:
        number: El número analizado
        data: Datos del análisis
        
    Returns:
        Nombre del archivo HTML generado
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"reporte_{number.replace('+', '')}_{timestamp}.html"
    
    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Análisis de Número: {number}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #007bff; margin-top: 30px; }}
        .section {{ margin: 20px 0; padding: 15px; background: #f8f9fa; border-left: 4px solid #007bff; }}
        .warning {{ background: #fff3cd; border-color: #ffc107; }}
        .danger {{ background: #f8d7da; border-color: #dc3545; }}
        .info-item {{ margin: 8px 0; }}
        .label {{ font-weight: bold; color: #555; }}
        pre {{ background: #e9ecef; padding: 10px; border-radius: 4px; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Análisis de Número Telefónico: {number}</h1>
        <p><strong>Fecha:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
"""
    
    for section, content in data.items():
        css_class = "section"
        if "error" in section.lower() or "riesgo" in str(content).lower():
            css_class += " warning"
        if "alto" in str(content).lower() or "premium" in str(content).lower():
            css_class += " danger"
        
        html_content += f'\n        <div class="{css_class}">\n'
        html_content += f'            <h2>{section.replace("_", " ").title()}</h2>\n'
        
        if isinstance(content, dict):
            for key, value in content.items():
                html_content += f'            <div class="info-item"><span class="label">{key}:</span> {value}</div>\n'
        elif isinstance(content, list):
            for item in content:
                html_content += f'            <div class="info-item">• {item}</div>\n'
        else:
            html_content += f'            <pre>{content}</pre>\n'
        
        html_content += '        </div>\n'
    
    html_content += """
    </div>
</body>
</html>"""
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f"Reporte HTML guardado en {filename}")
    return filename

def parallel_check(number: str, functions: dict) -> dict:
    """
    Ejecuta verificaciones en paralelo usando un ThreadPoolExecutor.
    
    Args:
        number: El número de teléfono a analizar.
        functions: Un diccionario donde las claves son los nombres de las secciones
                   y los valores son las funciones a ejecutar.
                   
    Returns:
        Un diccionario con los resultados de cada función ejecutada.
    """
    results = {}
    # Definir un orden de prioridad para que la información básica se procese primero
    priority_order = [
        "Información_básica",
        "Ubicación_aproximada",
        "Búsqueda_en_Google",
        "Información_de_operadora",
        "Reputación_del_número",
        "Redes_sociales",
        "Listas_negras",
        "Variaciones_de_formato"
    ]
    
    # Reordenar funciones según prioridad
    ordered_functions = {k: functions[k] for k in priority_order if k in functions}
    ordered_functions.update({k: functions[k] for k in functions if k not in priority_order})
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        
        for name, func in ordered_functions.items():
            try:
                futures[executor.submit(func)] = name
                time.sleep(random.uniform(0.5, 1.5))  # Espaciar solicitudes para evitar bloqueos
            except Exception as e:
                logger.error(f"Error al programar la tarea '{name}' para el número '{number}': {e}")
                results[name] = {"error": f"Error al programar la tarea '{name}': {str(e)}"}
        
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                logger.error(f"Error en la ejecución de la tarea '{name}' para el número '{number}': {e}")
                results[name] = {"error": f"Error en la ejecución de '{name}': {str(e)}"}
    
    return results