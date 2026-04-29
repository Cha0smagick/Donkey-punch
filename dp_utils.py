import os
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import random
import phonenumbers
import logging

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