# -*- coding: utf-8 -*-
"""
dp/utils.py - Utilidades v2: logging UTF-8, HTTP con throttle por host,
paralelismo sin sumisiones espaciadas y exportes JSON/TXT/CSV/HTML.

Cambios v2 (auditoría):
- FileHandler con encoding="utf-8" (el log antiguo salía mojibake en cp1252).
- make_request: sesión por hilo, throttle por host, copia de headers (ya no
  muta el dict del llamador), backoff en 429/503, soporte de auth.
- parallel_check: SIN sleep entre sumisiones (solo el throttle real de red
  espacia las peticiones); cancela futuros en Ctrl+C; resultados en orden.
- Exportes: UTF-8/utf-8-sig, HTML con html.escape y render recursivo.
- validate_phone_number acepta región de fallback.
- Los reportes se guardan en reports/.
"""

import csv
import html as html_mod
import json
import logging
import os
import random
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import phonenumbers
import requests

REPORTS_DIR = "reports"


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

def _build_logger() -> logging.Logger:
    lg = logging.getLogger("dp")
    lg.setLevel(logging.INFO)
    if lg.handlers:
        return lg
    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    try:
        fh = logging.FileHandler("dp_analysis.log", encoding="utf-8")
        fh.setFormatter(fmt)
        lg.addHandler(fh)
    except OSError:
        pass  # sin fichero de log: seguimos con consola
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    lg.addHandler(sh)
    return lg


logger = _build_logger()


# --------------------------------------------------------------------------
# HTTP: sesión por hilo + throttle por host
# --------------------------------------------------------------------------

_thread_local = threading.local()
_throttle_lock = threading.Lock()
_last_request: Dict[str, float] = {}

DEFAULT_HOST_INTERVAL = 1.0
HOST_MIN_INTERVAL = {
    "wa.me": 1.0,
    "t.me": 1.0,
    "gravatar.com": 0.5,
    "www.gravatar.com": 0.5,
    "ip-api.com": 1.5,        # límite público: 45 req/min
    "apilayer.net": 1.0,
    "lookups.twilio.com": 1.0,
}


def _session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        _thread_local.session = s
    return s


def _throttle(url: str) -> None:
    host = urllib.parse.urlparse(url).netloc.lower() or url
    interval = HOST_MIN_INTERVAL.get(host, DEFAULT_HOST_INTERVAL)
    with _throttle_lock:
        now = time.time()
        wait = max(0.0, interval - (now - _last_request.get(host, 0.0)))
        _last_request[host] = now + wait
    if wait > 0:
        time.sleep(wait + random.uniform(0.05, 0.35))


def make_request(url: str, method: str = "GET", headers: Optional[Dict] = None,
                 timeout: int = 10, max_retries: int = 3,
                 allow_redirects: bool = True,
                 auth: Optional[Tuple[str, str]] = None) -> Optional[requests.Response]:
    """Petición HTTP con reintentos, backoff y rotación de User-Agent.

    - Copia SIEMPRE los headers: no muta el dict del llamador.
    - Throttle por host compartido entre hilos.
    - Backoff exponencial en 429/503.
    - auth: tupla (usuario, contraseña) para HTTP Basic (p. ej. Twilio).
    """
    from .data import USER_AGENTS

    request_headers = dict(headers) if headers else {}
    if not any(k.lower() == "user-agent" for k in request_headers):
        request_headers["User-Agent"] = random.choice(USER_AGENTS)
    request_headers.setdefault("Accept-Language", "es-ES,es;q=0.9,en;q=0.8")

    for attempt in range(max_retries):
        _throttle(url)
        try:
            resp = _session().request(method, url, headers=request_headers,
                                      timeout=timeout, auth=auth,
                                      allow_redirects=allow_redirects)
            if resp.status_code in (429, 503):
                wait_time = (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning("Rate limited (%s) en %s. Esperando %.1fs...",
                               resp.status_code, url, wait_time)
                time.sleep(wait_time)
                continue
            return resp
        except Exception as e:
            logger.error("Error en make_request (intento %s/%s) %s: %s",
                         attempt + 1, max_retries, url, e)
            if attempt < max_retries - 1:
                time.sleep(random.uniform(1, 2))
    return None


def check_url_status(url: str) -> Dict[str, Any]:
    """Estado de una URL; HEAD con fallback GET (algunos sitios rechazan HEAD)."""
    try:
        response = make_request(url, method="HEAD", timeout=6)
        if response is None or response.status_code in (400, 403, 404, 405, 501):
            response = make_request(url, method="GET", timeout=6)
        if response is not None:
            return {
                "url": url,
                "status": response.status_code,
                "accesible": response.status_code < 400,
                "content_type": response.headers.get("Content-Type", "Unknown"),
            }
        return {"url": url, "status": "Error", "accesible": False}
    except Exception as e:
        return {"url": url, "status": "Error", "accesible": False, "error": str(e)}


# --------------------------------------------------------------------------
# Utilidades varias
# --------------------------------------------------------------------------

def clear_screen():
    """Limpia la pantalla de la consola (Windows y Unix)."""
    os.system('cls' if os.name == 'nt' else 'clear')


def validate_phone_number(number: str, region: Optional[str] = None) -> bool:
    """Valida el número con phonenumbers.

    region: código ISO opcional (p. ej. 'ES') para números sin prefijo +.
    """
    try:
        parsed = phonenumbers.parse(number, region)
        return phonenumbers.is_valid_number(parsed)
    except Exception as e:
        logger.warning("Error al validar el número '%s': %s", number, e)
        return False


def _reports_dir() -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    return REPORTS_DIR


def _fmt_value(v: Any) -> str:
    if isinstance(v, bool):
        return "Sí" if v else "No"
    return str(v)


def _write_block(f, content: Any, depth: int = 0) -> None:
    """Render recursivo de dict/list para el TXT (profundidad arbitraria)."""
    ind = "  " * depth
    if isinstance(content, dict):
        for k, v in content.items():
            if isinstance(v, (dict, list, tuple, set)):
                f.write(f"{ind}{k}:\n")
                _write_block(f, v, depth + 1)
            else:
                f.write(f"{ind}{k}: {_fmt_value(v)}\n")
    elif isinstance(content, (list, tuple, set)):
        for item in content:
            if isinstance(item, dict):
                f.write(f"{ind}-\n")
                _write_block(f, item, depth + 1)
            else:
                f.write(f"{ind}- {_fmt_value(item)}\n")
    else:
        f.write(f"{ind}{_fmt_value(content)}\n")


def save_to_file(number: str, data: dict) -> Tuple[str, str]:
    """Guarda el análisis en JSON y TXT (UTF-8) dentro de reports/."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe = number.replace('+', '')
    json_filename = os.path.join(_reports_dir(), f"reporte_{safe}_{timestamp}.json")
    txt_filename = os.path.join(_reports_dir(), f"reporte_{safe}_{timestamp}.txt")
    logger.info("Guardando resultados para %s en %s y %s",
                number, txt_filename, json_filename)

    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False, default=str)

    with open(txt_filename, 'w', encoding='utf-8') as f:
        f.write(f"╔{'═'*70}╗\n")
        f.write(f"║{'ANÁLISIS DE NÚMERO TELEFÓNICO':^70}║\n")
        f.write(f"╠{'═'*70}╣\n")
        f.write(f"║ Número: {number:<59}║\n")
        f.write(f"║ Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<59}║\n")
        f.write(f"╚{'═'*70}╝\n\n")

        for section, content in data.items():
            f.write(f"■ {section.upper()} {'■' * max(0, 68 - len(section))}\n\n")
            _write_block(f, content)
            f.write("\n")

        f.write("\n" + "═" * 70 + "\n")
        f.write("FIN DEL REPORTE\n")

    return txt_filename, json_filename


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------

def save_to_csv(numbers_data: List[Tuple[str, dict]],
                filename: Optional[str] = None) -> str:
    """Guarda un lote de análisis en CSV (utf-8-sig: compatible con Excel)."""
    if not filename:
        filename = os.path.join(
            _reports_dir(),
            f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Número', 'País', 'Región/Ciudad', 'Operadora', 'Tipo',
                         'Válido', 'Reputación', 'Riesgo global',
                         'Es VoIP', 'Es Premium', 'Es Toll Free',
                         'Geo ciudad', 'Correos hallados', 'Menciones web'])

        for number, data in numbers_data:
            basic = data.get("Información_básica", {}) or {}
            loc = data.get("Ubicación_aproximada", {}) or {}
            geo = data.get("Geolocalización_móvil", {}) or {}
            rep = data.get("Reputación_del_número", {}) or {}
            risk = data.get("Resumen_de_riesgo", {}) or {}
            voip = data.get("Detección_VoIP", {}) or {}
            prem = data.get("Verificación_tarifa_premium", {}) or {}
            toll = data.get("Número_gratuito", {}) or {}
            web = data.get("Búsqueda_web", {}) or {}
            mail = data.get("Cruce_correos", {}) or {}

            writer.writerow([
                number,
                basic.get('País', 'N/A'),
                loc.get('Región_o_Ciudad', 'N/A'),
                basic.get('Operadora', 'N/A'),
                basic.get('Tipo de número', 'N/A'),
                basic.get('Válido', 'N/A'),
                rep.get('Calificación_de_reputación', 'N/A'),
                risk.get('calificación', 'N/A'),
                voip.get('es_voip', 'N/A'),
                prem.get('es_premium_rate', 'N/A'),
                toll.get('es_toll_free', 'N/A'),
                geo.get('ciudad_detectada', 'N/A') if not geo.get('ignorado') else '(ignorado)',
                len(mail.get('correos_hallados', []) or []),
                web.get('Total_resultados', 0),
            ])

    logger.info("Reporte batch guardado en %s", filename)
    return filename


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

_URL_RE = re.compile(r'https?://[^\s<>"\']+')


def _html_render(value: Any, depth: int = 0) -> str:
    """Render recursivo escapado: dicts -> listas anidadas, URLs -> enlaces."""
    esc = html_mod.escape

    def with_links(text: str) -> str:
        return _URL_RE.sub(lambda m: f'<a href="{esc(m.group(0))}" target="_blank">{esc(m.group(0))}</a>',
                           esc(text))

    if isinstance(value, dict):
        items = "".join(
            f"<li><strong>{esc(str(k))}:</strong> {_html_render(v, depth + 1)}</li>"
            for k, v in value.items())
        return f"<ul>{items}</ul>"
    if isinstance(value, (list, tuple, set)):
        items = "".join(f"<li>{_html_render(v, depth + 1)}</li>" for v in value)
        return f"<ul>{items}</ul>"
    text = _fmt_value(value)
    if _URL_RE.fullmatch(text):
        return f'<a href="{esc(text)}" target="_blank">{esc(text)}</a>'
    return with_links(text) if "http" in text else esc(text)


def save_to_html(number: str, data: dict) -> str:
    """Reporte HTML en reports/ con todo el contenido escapado (anti-XSS local)."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe = number.replace('+', '')
    filename = os.path.join(_reports_dir(), f"reporte_{safe}_{timestamp}.html")

    risk = data.get("Resumen_de_riesgo", {}) or {}
    badge = str(risk.get("calificación", ""))

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Análisis de Número: {html_mod.escape(number)}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #007bff; margin-top: 30px; }}
        .section {{ margin: 20px 0; padding: 15px; background: #f8f9fa; border-left: 4px solid #007bff; }}
        .warning {{ background: #fff3cd; border-color: #ffc107; }}
        .danger {{ background: #f8d7da; border-color: #dc3545; }}
        .info-item {{ margin: 8px 0; }}
        ul {{ margin: 4px 0; padding-left: 20px; }}
        a {{ word-break: break-all; }}
        .risk-Elevado, .risk-Crítico {{ background: #f8d7da; border-color: #dc3545; }}
        .risk-Moderado {{ background: #fff3cd; border-color: #ffc107; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Análisis de Número Telefónico: {html_mod.escape(number)}</h1>
        <p><strong>Fecha:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
"""

    for section, content in data.items():
        low = str(content).lower()
        css_class = "section"
        if "error" in section.lower() or "riesgo" in low or "advertencia" in low:
            css_class += " warning"
        if "alto" in low or "premium" in low or "crítico" in low:
            css_class += " danger"
        if section == "Resumen_de_riesgo":
            css_class = f"section risk-{html_mod.escape(badge) or 'Bajo'}"

        html_content += f'\n        <div class="{css_class}">\n'
        html_content += (f'            <h2>{html_mod.escape(section.replace("_", " ").title())}</h2>\n')
        html_content += f'            {_html_render(content)}\n'
        html_content += '        </div>\n'

    html_content += """
    </div>
</body>
</html>"""

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)

    logger.info("Reporte HTML guardado en %s", filename)
    return filename


# --------------------------------------------------------------------------
# Paralelismo
# --------------------------------------------------------------------------

def parallel_check(number: str, functions: Dict[str, Any],
                   max_workers: int = 4) -> Dict[str, Any]:
    """Ejecuta módulos en paralelo con presupuesto y throttle reales.

    v2: SIN sleep entre sumisiones (el throttle por host de make_request/
    dp_search espacia las peticiones de verdad). Ctrl+C cancela los futuros
    pendientes en lugar de colgar. Los resultados llegan en orden de envío.
    """
    results: Dict[str, Any] = {}
    priority_order = [
        "Información_básica",
        "Ubicación_aproximada",
        "Información_de_operadora",
        "Reputación_del_número",
        "Variaciones_de_formato",
        "Listas_negras",
    ]
    ordered_functions = {k: functions[k] for k in priority_order if k in functions}
    ordered_functions.update({k: functions[k] for k in functions
                              if k not in priority_order})

    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures: Dict[Any, str] = {}
    interrupted = False
    try:
        for name, func in ordered_functions.items():
            try:
                futures[executor.submit(func)] = name
            except Exception as e:
                logger.error("Error al programar la tarea '%s' para '%s': %s",
                             name, number, e)
                results[name] = {"error": f"Error al programar la tarea '{name}': {e}"}

        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                logger.error("Error en la ejecución de la tarea '%s' para '%s': %s",
                             name, number, e)
                results[name] = {"error": f"Error en la ejecución de '{name}': {e}"}
    except KeyboardInterrupt:
        interrupted = True
        for fut in futures:
            fut.cancel()
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:  # Python < 3.9
            executor.shutdown(wait=False)
        raise
    else:
        executor.shutdown(wait=True)

    # Reordenar según el orden de envío (as_completed desordena)
    ordered = {name: results[name] for name in ordered_functions if name in results}
    for name, res in results.items():  # por si algo quedó fuera
        ordered.setdefault(name, res)
    if interrupted:
        ordered["_interrumpido"] = True
    return ordered
