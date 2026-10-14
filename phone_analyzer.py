# -*- coding: utf-8 -*-
"""
phone_analyzer.py - Núcleo del analizador OSINT (v2, 17 módulos + resumen).

Cambios v2 (auditoría):
- Detección VoIP/premium/toll-free por phonenumbers.number_type() (verdad de
  terreno). El enum real es MOBILE=1, FIXED_LINE_OR_MOBILE=2, TOLL_FREE=3,
  PREMIUM_RATE=4, VOIP=6: el código original usaba enteros erróneos ([1,3]
  trataba Toll Free como móvil; ==7 era Personal Number, no VoIP).
- check_google_search ELIMINADO: scrapeaba Google hasta 11 veces por número
  con conteo inflado (response.text.count) y 429s. Sustituido por
  check_web_search vía dp_search.SearchClient (multi-motor + presupuesto).
- Mensajería honesta: wa.me responde 200 para CUALQUIER número (no es
  verificación); t.me/NNN solo indica un alias numérico, no titularidad.
- cross_reference_emails: filtra correos ajenos del SERP (solo acepta si la
  parte local contiene dígitos del número o aparece a <120 chars del número
  en el texto). Añade verificación Gravatar (md5, ?d=404).
- HIBP con URL correcta /phone/%2BXXXXXXXX.
- Dorks ejecutados vía SearchClient (presupuesto compartido) + enlaces manual.
- find_exact_location: solo móviles reales; IP especulativa geolocalizada vía
  ip-api.com con etiqueta de especulación.
- Enriquecimiento opcional (numverify/Twilio) solo con claves en entorno.
- Flag no-net: los módulos de red se auto-desactivan.
"""

import hashlib
import os
import random
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import phonenumbers
from bs4 import BeautifulSoup
from phonenumbers import carrier, geocoder, timezone

from phone_data import (
    NUMBER_TYPE_MAP, AREA_CODE_RULES, LINE_RULES, CARRIERS_DB,
    SUSPICIOUS_PATTERNS, COUNTRY_SPECIFIC_RISKS, SOCIAL_MEDIA_TEMPLATES,
    BLACKLIST_TEMPLATES, VOIP_PROVIDER_INFO, BREACH_SOURCES, EMAIL_PATTERNS,
    PREMIUM_RATE_INFO, TOLL_FREE_INFO, TELLOWS_TLDS,
    PEOPLE_SEARCH_TEMPLATES, DORK_TEMPLATES, COUNTRY_METADATA, API_ENDPOINTS,
)
from dp_utils import parallel_check, logger, make_request
from dp_search import SearchClient

_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
_PLACEHOLDER_RE = re.compile(r'\{([a-z0-9_]+)\}')


class PhoneNumberAnalyzer:
    """Analiza un número telefónico: info básica, ubicación, reputación,
    presencia en línea, mensajería y enriquecimiento opcional."""

    def __init__(self, number: str, region: Optional[str] = None,
                 search_client: Optional[SearchClient] = None,
                 no_net: bool = False, max_queries: int = 8):
        self.raw_number = str(number).strip()
        self.region = region
        self.no_net = no_net

        self.parsed_number: Optional[phonenumbers.PhoneNumber] = None
        self.is_valid = False
        self.country_code: Optional[str] = None
        self.national_number_str: Optional[str] = None
        self.e164_digits: Optional[str] = None
        self.num_type: Optional[int] = None
        self.type_name = "Desconocido"

        # Parseo con fallback de región (para números nacionales sin '+')
        parse_attempts = [None, region] if region else [None]
        for reg in parse_attempts:
            try:
                self.parsed_number = phonenumbers.parse(self.raw_number, reg)
                break
            except Exception:
                self.parsed_number = None
        if self.parsed_number is None:
            logger.error("Error al parsear el número '%s'", self.raw_number)
            return

        self.is_valid = phonenumbers.is_valid_number(self.parsed_number)
        self.country_code = phonenumbers.region_code_for_number(self.parsed_number)
        self.national_number_str = str(self.parsed_number.national_number)
        self.e164_digits = phonenumbers.format_number(
            self.parsed_number,
            phonenumbers.PhoneNumberFormat.E164).lstrip("+")
        self.num_type = phonenumbers.number_type(self.parsed_number)
        self.type_name = NUMBER_TYPE_MAP.get(
            self.num_type, NUMBER_TYPE_MAP.get(-1, "Desconocido"))

        self.search_client = search_client or SearchClient(
            max_queries=max_queries, cache_dir="dp_cache/search")

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _check_parsed_number(self) -> bool:
        return self.parsed_number is not None

    @property
    def last7(self) -> str:
        n = self.national_number_str or ""
        return n[-7:] if len(n) >= 7 else n

    @property
    def last4(self) -> str:
        n = self.national_number_str or ""
        return n[-4:] if len(n) >= 4 else n

    @property
    def national_dashed(self) -> str:
        if not self._check_parsed_number():
            return ""
        return phonenumbers.format_number(
            self.parsed_number,
            phonenumbers.PhoneNumberFormat.NATIONAL).replace(" ", "-")

    def _fmt_ctx(self) -> Dict[str, str]:
        return {
            "e164_digits": self.e164_digits or "",
            "national": self.national_number_str or "",
            "national_dashed": self.national_dashed,
            "region": self.country_code or "",
            "region_lower": (self.country_code or "").lower(),
            "tld": TELLOWS_TLDS.get(self.country_code, "com"),
            "last7": self.last7,
            "last4": self.last4,
        }

    def _safe_format(self, template: str, ctx: Dict[str, str]) -> str:
        """Sustituye solo los placeholders conocidos (evita KeyError/ValueError)."""
        def repl(m: "re.Match") -> str:
            return ctx.get(m.group(1), m.group(0))
        return _PLACEHOLDER_RE.sub(repl, template)

    def _no_net(self) -> Dict[str, Any]:
        return {"modo": "sin red (--no-net): módulos de red desactivados"}

    # ------------------------------------------------------------------
    # Tipos de línea (verdad de terreno vía enum, sin enteros mágicos)
    # ------------------------------------------------------------------

    def is_mobile_number(self) -> bool:
        """Móvil real: MOBILE o FIXED_LINE_OR_MOBILE (no Toll Free, v1 usaba 3)."""
        if not self._check_parsed_number():
            return False
        return self.num_type in (
            phonenumbers.PhoneNumberType.MOBILE,
            phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE,
        )

    def is_voip_or_fixed(self) -> Tuple[bool, str]:
        """True si el número NO es geolocalizable (fijo/VoIP/premium/etc.)."""
        if not self._check_parsed_number():
            return False, "inválido"
        if self.num_type == phonenumbers.PhoneNumberType.FIXED_LINE:
            return True, "Fijo"
        if self.num_type == phonenumbers.PhoneNumberType.VOIP:
            return True, "VoIP"
        if not self.is_mobile_number():
            return True, self.type_name  # premium, toll-free, UAN, pager...
        return False, "Móvil"

    # ------------------------------------------------------------------
    # 1-2. Info básica y ubicación aproximada
    # ------------------------------------------------------------------

    def get_basic_info(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            country_name = geocoder.description_for_number(self.parsed_number, "es") or "Desconocido"
            carrier_name = carrier.name_for_number(self.parsed_number, "es") or "Desconocida"

            return {
                "Número formateado": phonenumbers.format_number(
                    self.parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
                "E.164": phonenumbers.format_number(
                    self.parsed_number, phonenumbers.PhoneNumberFormat.E164),
                "País": country_name,
                "Código de país": self.country_code,
                "Operadora": carrier_name,
                "Zona horaria": list(timezone.time_zones_for_number(self.parsed_number)),
                "Es posible número": phonenumbers.is_possible_number(self.parsed_number),
                "Es válido número": self.is_valid,
                "Tipo de número": self.type_name,
                "Código nacional": self.parsed_number.national_number,
                "Código de área": self._get_area_code(),
                "Línea": self._get_line_number(),
                "Formato local": phonenumbers.format_number(
                    self.parsed_number, phonenumbers.PhoneNumberFormat.NATIONAL),
                "Nota": "Operadora y ubicación son metadatos del rango asignado; "
                        "la portabilidad puede hacer que no coincidan con el uso actual."
            }
        except Exception as e:
            logger.error("Error en get_basic_info para '%s': %s", self.raw_number, e)
            return {"error": str(e)}

    def _get_area_code(self) -> str:
        if not self._check_parsed_number():
            return "N/A"
        digits = AREA_CODE_RULES.get(self.country_code)
        if digits and len(self.national_number_str) > digits:
            return self.national_number_str[:digits]
        return "N/A"

    def _get_line_number(self) -> str:
        if not self._check_parsed_number():
            return "N/A"
        digits = LINE_RULES.get(self.country_code)
        if digits and len(self.national_number_str) >= digits:
            return self.national_number_str[-digits:]
        return self.last7 if len(self.national_number_str) >= 7 else self.national_number_str

    def get_approximate_location(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            region = geocoder.description_for_number(self.parsed_number, "es")
            country = geocoder.country_name_for_number(self.parsed_number, "es")
            timezones = timezone.time_zones_for_number(self.parsed_number)

            precision = ("Alta (Fijo/Geográfico)"
                         if self.num_type in (phonenumbers.PhoneNumberType.FIXED_LINE,)
                         else "Baja (Móvil/Solo país)")
            return {
                "Región_o_Ciudad": region if region else "No disponible",
                "País": country,
                "Zonas_horarias": list(timezones),
                "Precisión": precision,
            }
        except Exception as e:
            logger.error("Error en get_approximate_location para '%s': %s",
                         self.raw_number, e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 3. Geolocalización móvil (solo móviles reales)
    # ------------------------------------------------------------------

    def find_exact_location(self) -> Dict[str, Any]:
        """Máxima aproximación ética/legal para móviles: ciudad/región vía
        geocoder + CP probable vía búsqueda web + señales de perfiles.

        NO existe 'ping' que devuelva GPS: eso requiere SS7/operador y orden
        judicial. Todo lo que hay aquí es heurística pública.
        """
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            is_blocked, kind = self.is_voip_or_fixed()
            if is_blocked:
                return {
                    "ignorado": True,
                    "razon": f"Número {kind} - No se puede geolocalizar",
                    "notas": "Los números fijos, VoIP y de tarificación especial "
                             "no soportan geolocalización móvil.",
                }

            location_data: Dict[str, Any] = {
                "es_móvil": True,
                "ciudad_detectada": "",
                "región": "",
                "código_postal_sugerido": "",
                "fuentes_consultadas": [],
                "métodos_usados": [],
                "nivel_precisión": "Baja",
                "advertencia_legal": "Coordenadas GPS exactas requieren orden judicial "
                                     "y acceso al operador. OSINT solo ofrece aproximación.",
            }

            # Método 1: geocoder de phonenumbers
            city = geocoder.description_for_number(self.parsed_number, "es")
            country = geocoder.country_name_for_number(self.parsed_number, "es")
            location_data["ciudad_detectada"] = city or "No disponible"
            location_data["región"] = country or "No disponible"
            location_data["métodos_usados"].append("Geocoder estándar")
            location_data["fuentes_consultadas"].append("phonenumbers")

            if self.no_net:
                location_data["nivel_precisión"] = "Baja (solo geocoder, modo sin red)"
                return location_data

            # Método 2: código postal probable vía búsqueda web (1 consulta)
            res = self.search_client.search(
                f'"{self.e164_digits}" ("código postal" OR "postal code" OR "CP" OR "zip")',
                max_results=10)
            if not res.get("error"):
                location_data["fuentes_consultadas"].append(
                    f"Búsqueda web ({res.get('motor_usado')})")
                location_data["métodos_usados"].append("Búsqueda de código postal")
                cp_re = re.compile(r'\b(?:cp|c\.p\.|postal code|zip)\s*:?\s*([A-Z0-9]{4,10})\b',
                                   re.IGNORECASE)
                for hit in res.get("resultados", []):
                    texto = f'{hit.get("titulo", "")} {hit.get("snippet", "")}'
                    m = cp_re.search(texto)
                    if m:
                        location_data["código_postal_sugerido"] = m.group(1)
                        break

            # Método 3: señales de perfiles (Telegram alias numérico)
            messaging = self.check_messaging()
            tg = messaging.get("telegram", {})
            if "Existe" in str(tg.get("estado", "")):
                location_data["métodos_usados"].append("Redes (alias Telegram numérico)")
                location_data["nota_social"] = tg.get("nota", "")

            # Método 4: IP especulativa en páginas que citan el número
            ip_check = self._check_ip_geolocation()
            if ip_check.get("ip_encontrada"):
                location_data["ip_vinculada"] = ip_check.get("ip", "")
                location_data["ip_ubicación"] = ip_check.get("ip_location", {})
                location_data["ip_especulativa"] = True
                location_data["métodos_usados"].append("IP en páginas públicas (especulativo)")

            if location_data.get("código_postal_sugerido"):
                location_data["nivel_precisión"] = "Media-Baja (código postal sugerido)"
            elif location_data.get("ip_vinculada"):
                location_data["nivel_precisión"] = "Baja-Media (IP especulativa)"
            else:
                location_data["nivel_precisión"] = "Baja (solo ciudad/país)"
            return location_data
        except Exception as e:
            logger.error("Error en find_exact_location para '%s': %s", self.raw_number, e)
            return {"error": str(e)}

    def _check_ip_geolocation(self) -> Dict[str, Any]:
        """Busca IPs en páginas que citan el número y las geolocaliza con
        ip-api.com. MUY especulativo: esas IPs suelen ser de servidores web o
        de terceros, NO del teléfono."""
        result: Dict[str, Any] = {
            "ip_encontrada": False, "ip": "", "ip_location": {}, "fuente": "",
            "especulativo": True,
            "notas": "Las IPs halladas en páginas que citan el número suelen "
                     "ser de servidores web o de terceros, no del teléfono.",
        }
        if self.no_net:
            return result

        res = self.search_client.search(
            f'"{self.e164_digits}" ("ip address" OR "proxy" OR "host")',
            max_results=10)
        for hit in res.get("resultados", []):
            texto = f'{hit.get("titulo", "")} {hit.get("snippet", "")}'
            for cand in _IP_RE.findall(texto):
                octets = [int(x) for x in cand.split(".")]
                if not all(0 <= o <= 255 for o in octets):
                    continue
                if octets[0] in (0, 10, 127):
                    continue
                if octets[0] == 192 and octets[1] == 168:
                    continue
                if octets[0] == 172 and 16 <= octets[1] <= 31:
                    continue
                result.update({"ip_encontrada": True, "ip": cand,
                               "fuente": hit.get("url", "")})
                break
            if result["ip_encontrada"]:
                break

        if result["ip_encontrada"]:
            resp = make_request(
                f"http://ip-api.com/json/{result['ip']}"
                "?fields=status,country,regionName,city,isp,org,as&lang=es",
                timeout=8)
            if resp is not None and resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get("status") == "success":
                        result["ip_location"] = {
                            k: data.get(k) for k in
                            ("country", "regionName", "city", "isp", "org", "as")
                            if data.get(k)}
                except Exception as e:
                    logger.debug("ip-api sin JSON válido: %s", e)
        return result

    # ------------------------------------------------------------------
    # 4. Búsqueda web multi-motor (sustituye al scraping de Google)
    # ------------------------------------------------------------------

    _SOCIAL_HOSTS = {
        "facebook.com": "Facebook", "instagram.com": "Instagram",
        "tiktok.com": "TikTok", "x.com": "X/Twitter", "twitter.com": "X/Twitter",
        "vk.com": "VK", "linkedin.com": "LinkedIn",
        "t.me": "Telegram", "telegram.me": "Telegram", "wa.me": "WhatsApp",
        "pastebin.com": "Pastebin", "youtube.com": "YouTube",
    }

    def check_web_search(self) -> Dict[str, Any]:
        """Búsqueda del número en 2 formatos vía SearchClient (presupuesto
        compartido). Devuelve enlaces reales y hosts detectados; sin conteos
        inflados."""
        out: Dict[str, Any] = {
            "Consultas": [],
            "Total_resultados": 0,
            "Enlaces_relacionados": [],
            "Presencias_detectadas": [],
            "Motor": None,
        }
        if self.no_net:
            out.update(self._no_net())
            return out

        seen_urls = set()
        hosts_seen = set()
        for q in (f'"{self.e164_digits}"', f'"{self.national_number_str}"'):
            res = self.search_client.search(q, max_results=15)
            out["Consultas"].append({
                "consulta": q,
                "motor": res.get("motor_usado"),
                "resultados": len(res.get("resultados", [])),
                "error": res.get("error"),
            })
            if res.get("motor_usado") and res["motor_usado"] != "cache":
                out["Motor"] = res["motor_usado"]
            for hit in res.get("resultados", []):
                url = hit.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    out["Enlaces_relacionados"].append({
                        "titulo": hit.get("titulo", ""),
                        "url": url,
                        "snippet": hit.get("snippet", ""),
                    })
                host = urllib.parse.urlparse(url).netloc.lower()
                for dom, nombre in self._SOCIAL_HOSTS.items():
                    if host.endswith(dom) and nombre not in hosts_seen:
                        hosts_seen.add(nombre)
                        out["Presencias_detectadas"].append(
                            f"{nombre}: {url}")

        out["Enlaces_relacionados"] = out["Enlaces_relacionados"][:25]
        out["Total_resultados"] = len(out["Enlaces_relacionados"])
        stats = self.search_client.stats()
        out["Presupuesto"] = (f"{stats['consultas_usadas']}/"
                              f"{stats['presupuesto_total']} consultas")
        return out

    # ------------------------------------------------------------------
    # 5. Redes sociales (enlaces manuales, sin falsas verificaciones)
    # ------------------------------------------------------------------

    def check_social_media(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            ctx = self._fmt_ctx()
            enlaces = {name: self._safe_format(tpl, ctx)
                       for name, tpl in SOCIAL_MEDIA_TEMPLATES.items()}
            people = {name: self._safe_format(tpl, ctx)
                      for name, tpl in PEOPLE_SEARCH_TEMPLATES.items()}
            return {
                "enlaces": enlaces,
                "people_search": people,
                "nota": "Enlaces de búsqueda MANUAL. Ninguno verifica titularidad; "
                        "people-search es mayoritariamente EE. UU.",
            }
        except Exception as e:
            logger.error("Error en check_social_media: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 6. Mensajería (honesto)
    # ------------------------------------------------------------------

    def check_messaging(self) -> Dict[str, Any]:
        """Endpoints públicos de mensajería con honestidad total.

        - wa.me responde 200 para CUALQUIER número: NO es verificación;
          solo se ofrece el enlace de contacto.
        - t.me/<digits> solo indica si existe un usuario cuyo ALIAS es
          numérico e idéntico al número: no implica titularidad.
        """
        result: Dict[str, Any] = {
            "whatsapp": {
                "enlace": f"https://wa.me/{self.e164_digits}",
                "verificado": False,
                "nota": "wa.me responde 200 para cualquier número: sirve como "
                        "enlace de contacto, NO como prueba de existencia.",
            },
            "telegram": {
                "enlace": f"https://t.me/{self.e164_digits}",
                "estado": "sin verificar",
            },
            "nota": "Ninguna plataforma pública resuelve teléfono -> perfil. "
                    "Las verificaciones reales requieren la app y el contacto.",
        }
        if self.no_net:
            result.update(self._no_net())
            return result

        try:
            resp = make_request(f"https://t.me/{self.e164_digits}", timeout=8)
            tg = result["telegram"]
            if resp is None:
                tg["estado"] = "Error al verificar"
            elif resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                og = soup.find("meta", property="og:title")
                title = (og.get("content") if og else "") or ""
                body_text = soup.get_text(" ", strip=True).lower()
                # Página genérica de Telegram para alias inexistente
                generic = ("telegram: contact" in body_text
                           or "if you have telegram" in body_text) and not title
                if title and not generic:
                    tg["estado"] = "Existe un perfil de Telegram con alias numérico idéntico"
                    tg["alias_titulo"] = title
                    tg["nota"] = ("NO implica que sea el titular del teléfono: "
                                  "los alias de Telegram los elige el usuario.")
                else:
                    tg["estado"] = "Sin perfil público con alias numérico"
            else:
                tg["estado"] = f"Sin perfil público (HTTP {resp.status_code})"
        except Exception as e:
            logger.error("Error en check_messaging: %s", e)
            result["telegram"]["estado"] = f"Error: {e}"
        return result

    # ------------------------------------------------------------------
    # 7. Operadora
    # ------------------------------------------------------------------

    def check_carrier_info(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            carrier_name = carrier.name_for_number(self.parsed_number, "en") or "Desconocida"
            carrier_info: Dict[str, Any] = {
                "Operadora": carrier_name,
                "Fuente": "metadatos del rango (phonenumbers); la portabilidad "
                          "puede alterar la operadora real",
            }
            for name, data in CARRIERS_DB.items():
                if name.lower() in carrier_name.lower():
                    tld = data.get("tld", {}).get(self.country_code, "com")
                    sitio = self._safe_format(data["sitio"], {"tld": tld})
                    carrier_info.update({
                        "Identificada_en_BD": name,
                        "Sitio web oficial": f"https://www.{sitio}",
                        "Países de operación": data["países"],
                        "Servicios ofrecidos": data["tipo"],
                    })
                    break
            else:
                carrier_info["Identificada_en_BD"] = False
            return carrier_info
        except Exception as e:
            logger.error("Error en check_carrier_info: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 8. Reputación (heurística)
    # ------------------------------------------------------------------

    def check_number_reputation(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            risk_factors = 0
            matched_patterns = []
            for pattern in SUSPICIOUS_PATTERNS:
                if re.search(pattern, self.national_number_str):
                    risk_factors += 1
                    matched_patterns.append(pattern)
            for pattern in COUNTRY_SPECIFIC_RISKS.get(self.country_code, []):
                if re.search(pattern, self.national_number_str):
                    risk_factors += 2
                    matched_patterns.append(f"Específico_{self.country_code}:{pattern}")

            if risk_factors > 3:
                reputation = "Muy Alta"
            elif risk_factors > 2:
                reputation = "Alta"
            elif risk_factors > 1:
                reputation = "Media"
            else:
                reputation = "Baja"

            return {
                "Factores_de_riesgo": risk_factors,
                "Patrones_sospechosos": matched_patterns or "Ninguno detectado",
                "Calificación_de_reputación": reputation,
                "Recomendación": ("Extrema precaución" if risk_factors > 3 else
                                  "Precaución" if risk_factors > 1 else
                                  "Parece legítimo"),
                "Nota": "Heurística de patrones: un número 'raro' no es "
                        "necesariamente fraudulento.",
            }
        except Exception as e:
            logger.error("Error en check_number_reputation: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 9. Listas negras (enlaces manuales)
    # ------------------------------------------------------------------

    def check_phone_blacklists(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            ctx = self._fmt_ctx()
            enlaces = {site: self._safe_format(tpl, ctx)
                       for site, tpl in BLACKLIST_TEMPLATES.items()}
            return {
                "enlaces": enlaces,
                "nota": "Consulta manual en listas negras públicas; estos sitios "
                        "suelen bloquear el scraping automatizado.",
            }
        except Exception as e:
            logger.error("Error en check_phone_blacklists: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 10. Variaciones de formato
    # ------------------------------------------------------------------

    def check_phone_format_variations(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            return {
                "E164": phonenumbers.format_number(
                    self.parsed_number, phonenumbers.PhoneNumberFormat.E164),
                "Internacional": phonenumbers.format_number(
                    self.parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
                "Nacional": phonenumbers.format_number(
                    self.parsed_number, phonenumbers.PhoneNumberFormat.NATIONAL),
                "RFC3966": phonenumbers.format_number(
                    self.parsed_number, phonenumbers.PhoneNumberFormat.RFC3966),
                "Nacional_con_guiones": self.national_dashed,
                "Sin_formato": self.national_number_str,
                "Solo_código_de_área": self._get_area_code(),
                "Solo_línea": self._get_line_number(),
                "Sin_ceros": self.national_number_str.lstrip('0'),
                "Últimos_4_dígitos": self.last4,
                "Últimos_7_dígitos": self.last7,
            }
        except Exception as e:
            logger.error("Error en check_phone_format_variations: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 11. Detección VoIP (verdad de terreno + heurística de operadora)
    # ------------------------------------------------------------------

    def check_voip_providers(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            es_voip = self.num_type == phonenumbers.PhoneNumberType.VOIP
            carrier_name = carrier.name_for_number(self.parsed_number, "en") or ""

            proveedores = []
            for prov, info in VOIP_PROVIDER_INFO.items():
                kws = info.get("indicadores", [])
                if kws and any(k in carrier_name.lower() for k in kws):
                    proveedores.append({
                        "proveedor": prov,
                        "sitio_web": info.get("sitio", ""),
                        "notas": info.get("notas", ""),
                        "fuente": "coincidencia con el nombre de operadora (heurístico)",
                    })
                    es_voip = True

            return {
                "es_voip": es_voip,
                "tipo_de_línea": self.type_name,
                "operadora_reportada": carrier_name or "Desconocida",
                "proveedores_detectados": proveedores,
                "riesgo_voip": "Alto" if es_voip else "Bajo",
                "notas": "Detección principal por tipo de línea (metadata "
                         "phonenumbers). La coincidencia por nombre de operadora "
                         "es heurística.",
            }
        except Exception as e:
            logger.error("Error en check_voip_providers: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 12. Toll free
    # ------------------------------------------------------------------

    def check_toll_free(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            es_toll_free = self.num_type == phonenumbers.PhoneNumberType.TOLL_FREE
            fuente = "tipo de línea (metadata phonenumbers)" if es_toll_free else ""
            prefijos = TOLL_FREE_INFO.get(self.country_code, [])

            if not es_toll_free and prefijos:
                for prefix in prefijos:
                    if self.national_number_str.startswith(prefix):
                        es_toll_free = True
                        fuente = f"prefijo nacional {prefix} (metadato por país)"
                        break

            return {
                "es_toll_free": es_toll_free,
                "fuente_deteccion": fuente or "no detectado",
                "prefijos_referencia_pais": prefijos,
                "nota": "Los toll-free son gratuitos para el que llama; útiles "
                        "para identificar empresas/soporte.",
            }
        except Exception as e:
            logger.error("Error en check_toll_free: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 13. Premium rate (verdad de terreno + prefijos por país corregidos)
    # ------------------------------------------------------------------

    def check_premium_rate(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            is_premium = self.num_type == phonenumbers.PhoneNumberType.PREMIUM_RATE
            rate_info: Dict[str, Any] = {}
            fuente = ""

            if is_premium:
                fuente = "tipo de línea (metadata phonenumbers)"
                rate_info = {
                    "tipo": "Premium Rate",
                    "pais": self.country_code,
                    "riesgo": "Alto - número de tarificación elevada",
                    "recomendacion": "Evitar llamar: coste elevado por minuto/llamada.",
                }

            # Metadato por país: prefijos comparados contra el NACIONAL (v1
            # comparaba "1900"/"4470" contra el nacional y nunca matcheaba).
            country_info = PREMIUM_RATE_INFO.get(self.country_code, {})
            if not is_premium and country_info:
                for prefix, desc in country_info.get("prefijos", {}).items():
                    if self.national_number_str.startswith(prefix):
                        is_premium = True
                        fuente = f"prefijo nacional {prefix} (metadato por país)"
                        rate_info = {
                            "tipo": desc,
                            "prefijo": prefix,
                            "pais": self.country_code,
                            "riesgo": "Alto - tarificación adicional",
                            "recomendacion": "Evitar llamar; verificar tarifa con el operador.",
                        }
                        break

            return {
                "es_premium_rate": is_premium,
                "informacion_tarifa": rate_info,
                "fuente_deteccion": fuente or "no detectado",
                "notas_pais": country_info.get("notas", ""),
                "numero_tipo": "Premium Rate" if is_premium else "Estándar",
            }
        except Exception as e:
            logger.error("Error en check_premium_rate: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 14. Bases de filtraciones (enlaces correctos + búsqueda web)
    # ------------------------------------------------------------------

    def check_breach_databases(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            ctx = self._fmt_ctx()
            enlaces = {name: self._safe_format(data["url_template"], ctx)
                       for name, data in BREACH_SOURCES.items()}

            out: Dict[str, Any] = {
                "enlaces_verificacion": enlaces,
                "notas_enlaces": {name: data.get("notes", "")
                                  for name, data in BREACH_SOURCES.items()},
                "posibles_menciones_web": [],
                "nota": "La comprobación real requiere registro/clave en cada "
                        "servicio; aquí se ofrecen enlaces correctos y una "
                        "búsqueda web genérica.",
            }
            if self.no_net:
                out.update(self._no_net())
                return out

            res = self.search_client.search(
                f'"{self.e164_digits}" (leak OR dump OR breach OR pastebin OR "filtración")',
                max_results=10)
            if not res.get("error"):
                out["posibles_menciones_web"] = [
                    {"titulo": h.get("titulo", ""), "url": h.get("url", "")}
                    for h in res.get("resultados", [])[:8]
                ]
            return out
        except Exception as e:
            logger.error("Error en check_breach_databases: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 15. Cruce de correos (filtrado estricto + Gravatar)
    # ------------------------------------------------------------------

    def _generate_email_patterns(self) -> List[str]:
        patrones = []
        for pattern in EMAIL_PATTERNS:
            try:
                patrones.append(pattern.format(
                    number=self.e164_digits,
                    national=self.national_number_str,
                    last7=self.last7,
                    last4=self.last4,
                ))
            except Exception:
                continue
        seen, uniq = set(), []
        for p in patrones:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        return uniq

    def _email_relacionado(self, email: str, texto_visible: str) -> bool:
        """Acepta solo correos vinculados al número: la parte local contiene
        dígitos del número, O el email aparece a <120 chars del número."""
        local = email.split("@")[0].lower()
        for dig in (self.e164_digits, self.national_number_str, self.last7, self.last4):
            if dig and dig in local:
                return True
        for dig in (self.e164_digits, self.national_number_str):
            if not dig:
                continue
            i_num, i_mail = texto_visible.find(dig), texto_visible.find(email)
            if i_num >= 0 and i_mail >= 0 and abs(i_num - i_mail) <= 120:
                return True
        return False

    def cross_reference_emails(self) -> Dict[str, Any]:
        """Cruce con bases de filtraciones (enlaces) + cosecha web FILTRADA +
        verificación Gravatar de los patrones más probables.

        v1 aceptaba CUALQUIER email del SERP (correos ajenos): ahora se filtra
        por cercanía al número."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            cross: Dict[str, Any] = {
                "correos_hallados": [],
                "correos_descartados_por_filtro": 0,
                "gravatar_con_avatar": [],
                "patrones_probables": self._generate_email_patterns()[:12],
                "enlaces_verificacion": {},
                "nota": "Los patrones son HIPÓTESIS. Un email solo se acepta si "
                        "su parte local contiene dígitos del número o aparece "
                        "pegado a él en el texto. Gravatar solo prueba que "
                        "existe un avatar, no la titularidad.",
            }

            ctx = self._fmt_ctx()
            cross["enlaces_verificacion"] = {
                name: self._safe_format(data["url_template"], ctx)
                for name, data in BREACH_SOURCES.items()}

            if self.no_net:
                cross.update(self._no_net())
                return cross

            # 1) Cosecha web con filtro estricto
            queries = [
                f'"{self.e164_digits}" ("@gmail.com" OR "@yahoo.com" OR "@hotmail.com" OR "@outlook.com")',
                f'"{self.national_number_str}" ("correo" OR "email")',
            ]
            for q in queries:
                res = self.search_client.search(q, max_results=15)
                for hit in res.get("resultados", []):
                    texto = f'{hit.get("titulo", "")} {hit.get("snippet", "")}'
                    for email in _EMAIL_RE.findall(texto):
                        if email in cross["correos_hallados"]:
                            continue
                        if self._email_relacionado(email, texto):
                            cross["correos_hallados"].append(email)
                        else:
                            cross["correos_descartados_por_filtro"] += 1
                        if len(cross["correos_hallados"]) >= 15:
                            break
                    if len(cross["correos_hallados"]) >= 15:
                        break
                if len(cross["correos_hallados"]) >= 15:
                    break

            # 2) Gravatar de los 3 patrones más probables (d=404: solo 200 si existe)
            for email in cross["patrones_probables"][:3]:
                h = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
                resp = make_request(f"https://www.gravatar.com/avatar/{h}?d=404",
                                    timeout=6)
                if resp is not None and resp.status_code == 200:
                    cross["gravatar_con_avatar"].append({
                        "email": email,
                        "nota": "Existe avatar Gravatar; NO confirma titularidad.",
                    })
            return cross
        except Exception as e:
            logger.error("Error en cross_reference_emails: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 16. Patrones de email (hipótesis)
    # ------------------------------------------------------------------

    def check_email_patterns(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            patrones = self._generate_email_patterns()
            return {
                "patrones_generados": patrones,
                "total_patrones": len(patrones),
                "notas": "Patrones probables (hipótesis). Verificar con OSINT "
                         "de email adicional antes de dar nada por hecho.",
            }
        except Exception as e:
            logger.error("Error en check_email_patterns: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 17. Google Dorks (algunos ejecutados vía SearchClient, resto manual)
    # ------------------------------------------------------------------

    def check_google_dorks(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            ctx = self._fmt_ctx()
            consultas: List[Dict[str, str]] = []
            for categoria, plantillas in DORK_TEMPLATES.items():
                for tpl in plantillas:
                    consultas.append({"categoria": categoria,
                                      "consulta": self._safe_format(tpl, ctx)})

            out: Dict[str, Any] = {
                "ejecutadas": [],
                "enlaces_manual": {
                    c["consulta"]:
                        "https://www.google.com/search?q="
                        + urllib.parse.quote_plus(c["consulta"])
                    for c in consultas
                },
            }
            if self.no_net:
                out["ejecutadas"] = "omitido (modo sin red)"
                return out

            # Ejecutar como máximo 3 dorks con el presupuesto compartido
            for c in consultas[:3]:
                res = self.search_client.search(c["consulta"], max_results=8)
                out["ejecutadas"].append({
                    "categoria": c["categoria"],
                    "consulta": c["consulta"],
                    "motor": res.get("motor_usado"),
                    "error": res.get("error"),
                    "resultados": [
                        {"titulo": h.get("titulo", ""), "url": h.get("url", "")}
                        for h in res.get("resultados", [])[:5]
                    ],
                })
            return out
        except Exception as e:
            logger.error("Error en check_google_dorks: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 18. Huella de operadora
    # ------------------------------------------------------------------

    def check_carrier_footprint(self) -> Dict[str, Any]:
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}

            carrier_name = carrier.name_for_number(self.parsed_number, "en") or "Desconocida"
            country_data = COUNTRY_METADATA.get(self.country_code, {})
            return {
                "operadora": carrier_name,
                "infraestructura": {
                    "prefijos_operadora": country_data.get("carrier_prefixes", {}).get(
                        carrier_name, []),
                    "tipo_red": country_data.get("network_types", "Mixto"),
                    "portabilidad": country_data.get("number_portability", False),
                },
                "notas_pais": country_data.get("notas", ""),
                "advertencia": "Los prefijos por operadora son orientativos: "
                               "la portabilidad los invalida con frecuencia.",
            }
        except Exception as e:
            logger.error("Error en check_carrier_footprint: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 19. Enriquecimiento opcional vía APIs (solo con claves en entorno)
    # ------------------------------------------------------------------

    def check_enrichment(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"disponible": False, "consultas": []}
        if self.no_net:
            out["razon"] = "modo sin red"
            return out

        clave_numverify = os.environ.get(API_ENDPOINTS["numverify"]["auth_env"], "")
        sid = os.environ.get("DP_TWILIO_SID", "")
        token = os.environ.get("DP_TWILIO_TOKEN", "")

        if not clave_numverify and not (sid and token):
            out["razon"] = ("Sin claves: exporte DP_NUMVERIFY_KEY y/o "
                            "DP_TWILIO_SID + DP_TWILIO_TOKEN para enriquecer.")
            return out

        out["disponible"] = True
        if clave_numverify:
            url = self._safe_format(API_ENDPOINTS["numverify"]["url"],
                                    {"key": clave_numverify,
                                     "e164_digits": self.e164_digits})
            resp = make_request(url, timeout=10)
            entry: Dict[str, Any] = {"fuente": "numverify"}
            if resp is not None and resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get("error"):
                        entry["error"] = data["error"].get("info", "error de API")
                    else:
                        entry["datos"] = data
                except Exception as e:
                    entry["error"] = f"respuesta no JSON: {e}"
            else:
                entry["error"] = f"HTTP {getattr(resp, 'status_code', 'sin respuesta')}"
            out["consultas"].append(entry)

        if sid and token:
            url = self._safe_format(API_ENDPOINTS["twilio_lookup"]["url"],
                                    {"e164_digits": self.e164_digits})
            resp = make_request(url, timeout=10, auth=(sid, token))
            entry = {"fuente": "twilio_lookup"}
            if resp is not None and resp.status_code == 200:
                try:
                    entry["datos"] = resp.json()
                except Exception as e:
                    entry["error"] = f"respuesta no JSON: {e}"
            else:
                entry["error"] = f"HTTP {getattr(resp, 'status_code', 'sin respuesta')}"
            out["consultas"].append(entry)
        return out

    # ------------------------------------------------------------------
    # 20. Resumen de riesgo consolidado
    # ------------------------------------------------------------------

    def summarize_risk(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Consolida señales de todos los módulos en una puntuación 0-10."""
        senales: List[str] = []
        score = 0.0

        voip = data.get("Detección_VoIP", {}) or {}
        if voip.get("es_voip"):
            score += 3
            senales.append("Línea VoIP (anonimato barato, muy usado en fraudes)")
            for prov in voip.get("proveedores_detectados", []) or []:
                senales.append(f"Proveedor VoIP: {prov.get('proveedor', 'N/A')}")

        premium = data.get("Verificación_tarifa_premium", {}) or {}
        if premium.get("es_premium_rate"):
            score += 4
            senales.append("Número Premium Rate: llamar puede costarte dinero")

        rep = data.get("Reputación_del_número", {}) or {}
        factores = int(rep.get("Factores_de_riesgo", 0) or 0)
        if factores:
            score += min(3, factores)
            senales.append(f"Patrones sospechosos en el número ({factores})")

        web = data.get("Búsqueda_web", {}) or {}
        total_web = int(web.get("Total_resultados", 0) or 0)
        if total_web > 0:
            senales.append(f"Presencia web pública ({total_web} enlaces)")
        if web.get("Presencias_detectadas"):
            score += 1
            senales.append("El número aparece en redes/documentos indexados")

        mails = data.get("Cruce_correos", {}) or {}
        if mails.get("correos_hallados"):
            score += 1
            senales.append(f"{len(mails['correos_hallados'])} correo(s) "
                           "relacionado(s) en fuentes públicas")

        msg = data.get("Mensajería", {}) or {}
        if "Existe" in str((msg.get("telegram") or {}).get("estado", "")):
            senales.append("Alias de Telegram numérico existente (informativo)")

        score = max(0, min(10, round(score, 1)))
        if score >= 7:
            calificacion = "Crítico"
        elif score >= 5:
            calificacion = "Elevado"
        elif score >= 3:
            calificacion = "Moderado"
        else:
            calificacion = "Bajo"

        recomendaciones = []
        if premium.get("es_premium_rate"):
            recomendaciones.append("No devuelvas la llamada: puede ser de pago.")
        if voip.get("es_voip"):
            recomendaciones.append("Trata con cautela: los VoIP se descartan y recrean fácilmente.")
        if calificacion == "Bajo":
            recomendaciones.append("Sin señales significativas; verificación manual sugerida para decisiones sensibles.")

        return {
            "puntuación_riesgo": f"{score}/10",
            "calificación": calificacion,
            "señales": senales or ["Sin señales relevantes"],
            "recomendaciones": recomendaciones,
            "nota": "Heurístico y no vinculante; no es una verificación de identidad.",
        }

    # ------------------------------------------------------------------
    # Orquestación
    # ------------------------------------------------------------------

    def analyze_all(self) -> Dict[str, Any]:
        if not self._check_parsed_number():
            logger.warning("Intento de análisis para número no válido: '%s'",
                           self.raw_number)
            return {"error": "Número de teléfono no válido o no parseado."}

        check_functions = {
            "Información_básica": self.get_basic_info,
            "Ubicación_aproximada": self.get_approximate_location,
            "Geolocalización_móvil": self.find_exact_location,
            "Búsqueda_web": self.check_web_search,
            "Redes_sociales": self.check_social_media,
            "Mensajería": self.check_messaging,
            "Información_de_operadora": self.check_carrier_info,
            "Reputación_del_número": self.check_number_reputation,
            "Listas_negras": self.check_phone_blacklists,
            "Variaciones_de_formato": self.check_phone_format_variations,
            "Detección_VoIP": self.check_voip_providers,
            "Número_gratuito": self.check_toll_free,
            "Verificación_tarifa_premium": self.check_premium_rate,
            "Bases_de_filtraciones": self.check_breach_databases,
            "Cruce_correos": self.cross_reference_emails,
            "Patrones_de_email": self.check_email_patterns,
            "Google_Dorks": self.check_google_dorks,
            "Huella_de_operadora": self.check_carrier_footprint,
            "Enriquecimiento_API": self.check_enrichment,
        }

        data = parallel_check(self.raw_number, check_functions)
        data["Resumen_de_riesgo"] = self.summarize_risk(data)
        return data
