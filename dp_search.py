# -*- coding: utf-8 -*-
"""
dp_search.py - Motor de busqueda web multi-motor (sin claves de API).

Sustituye el scraping directo de Google, que en la practica devolvia
timeouts y CAPTCHAS (ver dp_analysis.log), por una cadena de motores
scrapeables con degradacion automatica:

    1. DuckDuckGo HTML  (POST https://html.duckduckgo.com/html/)
    2. DuckDuckGo Lite  (GET  https://lite.duckduckgo.com/lite/)
    3. Bing             (GET  https://www.bing.com/search)
    4. Mojeek           (GET  https://www.mojeek.com/search)

Incluye:
- Presupuesto de consultas por analisis (max_queries) compartido entre hilos.
- Throttle por host con jitter (protege de 429 de verdad, no en la sumision).
- Cache en disco con TTL (dp_cache/search/) para re-analisis rapidos.
- Deteccion de bloqueo/anomalia por motor con fallback al siguiente.
- Sesiones HTTP por hilo (keep-alive).

Honestidad tecnica: los selectores de los motores cambian con el tiempo.
Los parsers son defensivos: si un motor cambia su HTML, ese motor devuelve
"sin resultados" (sin crashear) y el siguiente toma el relevo.
"""

import base64
import hashlib
import json
import logging
import os
import random
import threading
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from phone_data import USER_AGENTS

logger = logging.getLogger("dp_search")

_local = threading.local()
_throttle_lock = threading.Lock()
_last_request: Dict[str, float] = {}

# Intervalo minimo (segundos) entre requests al MISMO host, con margen anti-429.
HOST_MIN_INTERVAL = {
    "html.duckduckgo.com": 2.0,
    "lite.duckduckgo.com": 2.0,
    "www.bing.com": 1.5,
    "www.mojeek.com": 1.0,
}
DEFAULT_MIN_INTERVAL = 1.0

# Marcadores de bloqueo/anomalia (CAPTCHA, challenge, etc.)
BLOCK_MARKERS = (
    "anomaly", "unfortunately, bots use duckduckgo",
    "are you a robot", "captcha", "verify you are a human",
    "unusual traffic",
)

# Hosts internos de los motores: nunca contar como resultado "externo".
_INTERNAL_HOSTS = {
    "duckduckgo.com", "www.bing.com", "www.mojeek.com",
    "google.com", "www.google.com", "microsoft.com",
}


def _session() -> requests.Session:
    """Una sesion por hilo (requests.Session no es garantizado thread-safe)."""
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
    return _local.session


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }


def _throttle(url: str) -> None:
    """Duerme lo necesario para respetar el intervalo minimo por host."""
    host = urllib.parse.urlparse(url).netloc or url
    interval = HOST_MIN_INTERVAL.get(host, DEFAULT_MIN_INTERVAL)
    with _throttle_lock:
        now = time.time()
        elapsed = now - _last_request.get(host, 0.0)
        wait = max(0.0, interval - elapsed)
        _last_request[host] = now + wait  # reserva el hueco para este hilo
    if wait > 0:
        time.sleep(wait + random.uniform(0.0, 0.4))


def _request(method: str, url: str, data=None, params=None,
             timeout: int = 12) -> Tuple[Optional[int], Optional[str]]:
    _throttle(url)
    try:
        r = _session().request(method, url, headers=_headers(),
                               data=data, params=params, timeout=timeout)
        return r.status_code, r.text
    except Exception as e:
        logger.debug("dp_search: fallo de red en %s: %s", url, e)
        return None, None


# --------------------------------------------------------------------------
# Cache en disco (best-effort: cualquier fallo la ignora en silencio)
# --------------------------------------------------------------------------

def _cache_get(key: str, ttl: int, cache_dir: Optional[str]) -> Optional[list]:
    if not cache_dir:
        return None
    path = os.path.join(cache_dir, key + ".json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if time.time() - obj.get("ts", 0) <= ttl:
            return obj.get("data")
    except Exception:
        pass
    return None


def _cache_put(key: str, data: list, cache_dir: Optional[str]) -> None:
    if not cache_dir:
        return
    try:
        os.makedirs(cache_dir, exist_ok=True)
        path = os.path.join(cache_dir, key + ".json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "data": data}, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        logger.debug("dp_search: cache no escrita: %s", e)


# --------------------------------------------------------------------------
# Parsers (defensivos: ante HTML desconocido devuelven lista vacia)
# --------------------------------------------------------------------------

def _un_ddg(href: str) -> str:
    """Los enlaces de DDG llegan como redirect //duckduckgo.com/l/?uddg=<enc>."""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "uddg=" in href:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        target = qs.get("uddg", [""])[0]
        return urllib.parse.unquote(target)
    if href.startswith("http"):
        return href
    return ""


def _parse_ddg_html(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, str]] = []
    for res in soup.find_all("div", class_="result"):
        a = res.find("a", class_="result__a")
        if not a:
            continue
        url = _un_ddg(a.get("href", ""))
        if not url:
            continue
        snip = res.find("a", class_="result__snippet") \
            or res.find("td", class_="result-snippet")
        out.append({
            "titulo": a.get_text(strip=True)[:200],
            "url": url,
            "snippet": snip.get_text(" ", strip=True)[:400] if snip else "",
        })
    return out


def _parse_ddg_lite(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    # Los resultados lite van en <tr>; el snippet esta en la fila siguiente.
    for tr in soup.find_all("tr"):
        link = tr.find("a", class_="result-link")
        snip_td = tr.find("td", class_="result-snippet")
        if link is not None:
            url = _un_ddg(link.get("href", ""))
            if url:
                current = {"titulo": link.get_text(strip=True)[:200],
                           "url": url, "snippet": ""}
                out.append(current)
        if snip_td is not None and current is not None and not current["snippet"]:
            current["snippet"] = snip_td.get_text(" ", strip=True)[:400]
    return out


def _un_bing(href: str) -> str:
    """Los enlaces de Bing llegan como redirect www.bing.com/ck/a?...&u=a1<b64url>.

    Verificado en vivo (2026-10): el parametro u trae el destino real en
    base64url precedido de 'a1'. Sin esto, _dedupe filtraba TODO (el host
    www.bing.com esta en _INTERNAL_HOSTS) y Bing devolvia 0 hits.
    """
    if not href or "/ck/a" not in href:
        return href or ""
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        u = qs.get("u", [""])[0]
        if u.startswith("a1"):
            b64 = u[2:].replace("-", "+").replace("_", "/")
            b64 += "=" * (-len(b64) % 4)
            decoded = base64.b64decode(b64).decode("utf-8", "replace")
            if decoded.startswith("http"):
                return decoded
    except Exception:
        pass
    return href


def _parse_bing(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, str]] = []
    for li in soup.find_all("li", class_="b_algo"):
        h2 = li.find("h2")
        if not h2:
            continue
        a = h2.find("a")
        if not a or not a.get("href"):
            continue
        url = _un_bing(a["href"])
        if not url.startswith("http"):
            continue
        p = li.find("p")
        out.append({
            "titulo": a.get_text(strip=True)[:200],
            "url": url,
            "snippet": p.get_text(" ", strip=True)[:400] if p else "",
        })
    return out


def _parse_generic_h2(html: str) -> List[Dict[str, str]]:
    """Fallback generico (Mojeek y similares): <h2><a href> + <p> hermano."""
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, str]] = []
    for h2 in soup.find_all("h2"):
        a = h2.find("a", href=True)
        if not a or not str(a["href"]).startswith("http"):
            continue
        p = h2.find_next_sibling("p")
        out.append({
            "titulo": a.get_text(strip=True)[:200],
            "url": a["href"],
            "snippet": p.get_text(" ", strip=True)[:400] if p else "",
        })
    return out


def _dedupe(hits: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out: List[Dict[str, str]] = []
    for h in hits:
        url = h.get("url", "")
        host = urllib.parse.urlparse(url).netloc.lower()
        if not host or host in _INTERNAL_HOSTS:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(h)
    return out


def _looks_blocked(html: Optional[str]) -> bool:
    low = (html or "").lower()
    return any(marker in low for marker in BLOCK_MARKERS)


# --------------------------------------------------------------------------
# Cliente de busqueda con presupuesto compartido entre hilos
# --------------------------------------------------------------------------

class SearchClient:
    """Cliente de busqueda reutilizable por todos los modulos de un analisis.

    El presupuesto (max_queries) es GLOBAL a la instancia: todos los hilos
    de parallel_check comparten el mismo SearchClient, por lo que el numero
    total de consultas web por numero queda acotado si o si.
    """

    def __init__(self, max_queries: int = 8, use_cache: bool = True,
                 cache_ttl: int = 86400, cache_dir: Optional[str] = None):
        self.max_queries = int(max_queries)
        self.queries_used = 0
        self.cache_ttl = int(cache_ttl)
        self.cache_dir = cache_dir if use_cache else None
        self.blocked_engines: set = set()
        self._budget_lock = threading.Lock()

    # -- presupuesto ------------------------------------------------------
    def _consume_budget(self) -> bool:
        with self._budget_lock:
            if self.queries_used >= self.max_queries:
                return False
            self.queries_used += 1
            return True

    # -- motores ------------------------------------------------------------
    ENGINES = [
        ("duckduckgo_html",
         lambda q: _request("POST", "https://html.duckduckgo.com/html/",
                            data={"q": q, "kl": "wt-wt"}),
         _parse_ddg_html),
        ("duckduckgo_lite",
         lambda q: _request("GET", "https://lite.duckduckgo.com/lite/",
                            params={"q": q}),
         _parse_ddg_lite),
        ("bing",
         lambda q: _request("GET", "https://www.bing.com/search",
                            params={"q": q, "count": "30"}),
         _parse_bing),
        ("mojeek",
         lambda q: _request("GET", "https://www.mojeek.com/search",
                            params={"q": q}),
         _parse_generic_h2),
    ]

    def search(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Busca un termino; devuelve dict con resultados y metadatos.

        Nunca lanza excepcion: errores y bloqueos se reportan en el dict.
        """
        result: Dict[str, Any] = {
            "consulta": query,
            "resultados": [],
            "motor_usado": None,
            "desde_cache": False,
            "error": None,
        }
        if not query or not query.strip():
            result["error"] = "Consulta vacia"
            return result

        key = hashlib.sha1(("dpsearch|" + query.strip().lower())
                           .encode("utf-8")).hexdigest()

        if self.cache_dir:
            cached = _cache_get(key, self.cache_ttl, self.cache_dir)
            if cached is not None:
                result["resultados"] = cached[:max_results]
                result["motor_usado"] = "cache"
                result["desde_cache"] = True
                return result

        if not self._consume_budget():
            result["error"] = ("Presupuesto de busquedas agotado "
                               f"({self.max_queries} consultas).")
            return result

        for name, fetch, parse in self.ENGINES:
            if name in self.blocked_engines:
                continue
            status, html = fetch(query.strip())
            if status is None:
                continue  # fallo de red: motor siguiente
            if status != 200 or _looks_blocked(html):
                self.blocked_engines.add(name)
                logger.warning("dp_search: motor %s bloqueado o anomalo "
                               "(status=%s)", name, status)
                continue
            try:
                hits = _dedupe(parse(html))
            except Exception as e:
                logger.debug("dp_search: parser de %s fallo: %s", name, e)
                hits = []
            if hits:
                result["resultados"] = hits[:max_results]
                result["motor_usado"] = name
                if self.cache_dir:
                    _cache_put(key, hits, self.cache_dir)
                return result

        result["error"] = ("Sin resultados o todos los motores bloqueados "
                           f"({', '.join(sorted(self.blocked_engines)) or 'red'})")
        return result

    def stats(self) -> Dict[str, Any]:
        return {
            "consultas_usadas": self.queries_used,
            "presupuesto_total": self.max_queries,
            "motores_bloqueados": sorted(self.blocked_engines),
        }


if __name__ == "__main__":
    # Prueba rapida:  python dp_search.py '"34612345678"'
    import sys
    logging.basicConfig(level=logging.DEBUG)
    client = SearchClient(max_queries=2, use_cache=False)
    for termino in (sys.argv[1:] or ['"34612345678"']):
        r = client.search(termino)
        print(f"\n=== {termino} -> {r['motor_usado']} ({len(r['resultados'])} hits)")
        for h in r["resultados"][:5]:
            print(f"  - {h['titulo'][:70]} | {h['url']}")
    print("\nStats:", client.stats())
