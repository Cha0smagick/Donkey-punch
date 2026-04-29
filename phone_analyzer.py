import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
import random
import phonenumbers
from phonenumbers import carrier, geocoder, timezone
from typing import Dict, Any, List, Optional, Tuple
import json
import time
import hashlib
import base64

import logging

from phone_data import (
    NUMBER_TYPE_MAP, LOCAL_FORMATS_DB, AREA_CODE_RULES, LINE_RULES,
    CARRIERS_DB, SUSPICIOUS_PATTERNS, COUNTRY_SPECIFIC_RISKS,
    SOCIAL_MEDIA_TEMPLATES, BLACKLIST_TEMPLATES, USER_AGENTS,
    VOIP_PROVIDERS, BREACH_SOURCES, EMAIL_PATTERNS,
    PREMIUM_RATE_RANGES, COUNTRY_METADATA, API_ENDPOINTS
)
from dp_utils import parallel_check, logger, make_request, check_url_status



class PhoneNumberAnalyzer:
    """
    Clase para analizar un número telefónico, obteniendo información básica,
    ubicación, reputación, presencia en línea y variaciones de formato.
    """
    
    def __init__(self, number: str):
        """
        Inicializa el analizador con el número de teléfono.
        
        Args:
            number: El número de teléfono en formato internacional (ej: +34123456789).
        """
        self.raw_number = number
        self.parsed_number: Optional[phonenumbers.PhoneNumber] = None
        self.country_code: Optional[str] = None
        self.national_number_str: Optional[str] = None
        
        try:
            self.parsed_number = phonenumbers.parse(number, None)
            if not phonenumbers.is_valid_number(self.parsed_number):
                raise ValueError("Número de teléfono no válido.")
            self.country_code = phonenumbers.region_code_for_number(self.parsed_number)
            self.national_number_str = str(self.parsed_number.national_number)
        except Exception as e:
            self.parsed_number = None # Asegurarse de que sea None si hay un error
            logger.error(f"Error al inicializar PhoneNumberAnalyzer para '{number}': {e}")

    def _check_parsed_number(self) -> bool:
        """Verifica si el número fue parseado correctamente."""
        if not self.parsed_number:
            return False
        return True

    def _get_area_code(self) -> str:
        """Obtiene el código de área con mayor precisión."""
        if not self._check_parsed_number():
            return "N/A"
        
        digits = AREA_CODE_RULES.get(self.country_code.upper())
        if digits and len(self.national_number_str) > digits:
            return self.national_number_str[:digits]
        
        return "N/A"

    def _get_line_number(self) -> str:
        """Obtiene el número de línea (últimos dígitos)."""
        if not self._check_parsed_number():
            return "N/A"
        
        digits = LINE_RULES.get(self.country_code.upper())
        if digits and len(self.national_number_str) >= digits:
            return self.national_number_str[-digits:]
        
        return self.national_number_str[-7:] if len(self.national_number_str) >= 7 else self.national_number_str

    def _get_local_format(self) -> str:
        """Devuelve el formato local estándar para el número."""
        if not self._check_parsed_number():
            return "N/A"
        
        formatter = LOCAL_FORMATS_DB.get(self.country_code.upper())
        if formatter:
            return formatter(self.national_number_str)
        
        return phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.NATIONAL)

    def _get_country_specific_info(self) -> Dict[str, Any]:
        """Información específica según el país."""
        info = {}
        if not self._check_parsed_number():
            return info
        
        country_code_upper = self.country_code.upper()
        
        # Información adicional por país
        if country_code_upper == "US":
            info["Notas"] = "Código de área de 3 dígitos, número local de 7 dígitos"
        elif country_code_upper == "ES":
            info["Notas"] = "Prefijo provincial de 3 dígitos, número local de 6 dígitos"
        elif country_code_upper == "MX":
            info["Notas"] = "LADA de 3 dígitos, número local de 7 u 8 dígitos"
        
        return info

    def get_basic_info(self) -> Dict[str, Any]:
        """Obtiene información básica mejorada con datos específicos por país."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            country_name = geocoder.description_for_number(self.parsed_number, "es") or "Desconocido"
            carrier_name = carrier.name_for_number(self.parsed_number, "es") or "Desconocida"
            
            basic_info = {
                "Número formateado": phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
                "País": country_name,
                "Código de país": self.country_code,
                "Operadora": carrier_name,
                "Zona horaria": timezone.time_zones_for_number(self.parsed_number),
                "Es posible número": phonenumbers.is_possible_number(self.parsed_number),
                "Es válido número": phonenumbers.is_valid_number(self.parsed_number),
                "Tipo de número": NUMBER_TYPE_MAP.get(phonenumbers.number_type(self.parsed_number), "Desconocido"),
                "Código nacional": self.parsed_number.national_number,
                "Código de área": self._get_area_code(),
                "Línea": self._get_line_number(),
                "Formato local": self._get_local_format()
            }
            
            basic_info.update(self._get_country_specific_info())
            
            return basic_info
        except Exception as e:
            logger.error(f"Error en get_basic_info para '{self.raw_number}': {e}")
            return {"error": f"Error al analizar información básica: {str(e)}"}

    def get_approximate_location(self) -> Dict[str, Any]:
        """Obtiene localización aproximada detallada."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            region = geocoder.description_for_number(self.parsed_number, "es")
            country = geocoder.country_name_for_number(self.parsed_number, "es")
            timezones = timezone.time_zones_for_number(self.parsed_number)
            
            return {
                "Región_o_Ciudad": region if region else "No disponible",
                "País": country,
                "Zonas_horarias": list(timezones),
                "Precisión": "Alta (Fijo/Geográfico)" if phonenumbers.number_type(self.parsed_number) in [0, 2] else "Baja (Móvil/País)"
            }
        except Exception as e:
            logger.error(f"Error en get_approximate_location para '{self.raw_number}': {e}")
            return {"error": f"Error al obtener ubicación aproximada: {str(e)}"}

    def check_google_search(self) -> Dict[str, Any]:
        """Búsqueda en Google mejorada con múltiples formatos."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            formats = [
                phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.E164).replace("+", ""),
                phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
                phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.NATIONAL),
                phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.RFC3966),
                self.national_number_str,
                self.national_number_str[-7:]  # Últimos 7 dígitos
            ]
            
            formats = list(set(formats)) # Eliminar duplicados
            
            results = {
                "Enlaces_relacionados": set(),
                "Menciones": 0,
                "Formatos_buscados": formats,
                "Resultados_por_formato": {}
            }
            
            for num_format in formats:
                clean_num = re.sub(r'[^0-9]', '', num_format)
                if not clean_num:
                    continue
                    
                url = f"https://www.google.com/search?q={urllib.parse.quote(clean_num)}"
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                
                try:
                    response = requests.get(url, headers=headers, timeout=10)
                    
                    if response.status_code == 429:
                        logger.warning(f"Google bloqueó la solicitud para '{num_format}' ({self.raw_number}). Demasiadas solicitudes.")
                        results["Resultados_por_formato"][num_format] = "Bloqueado (Too Many Requests)"
                        continue
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    mentions = response.text.count(clean_num)
                    results["Menciones"] += mentions
                    results["Resultados_por_formato"][num_format] = mentions
                    
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        if "http" in href and not any(x in href for x in ["google.com", "youtube.com"]):
                            clean_link = re.sub(r'&sa=.*', '', href.replace("/url?q=", ""))
                            results["Enlaces_relacionados"].add(urllib.parse.unquote(clean_link))
                    
                    # time.sleep(random.uniform(1, 3)) # Se maneja en parallel_check
                except Exception as e:
                    logger.error(f"Error al buscar '{num_format}' en Google para '{self.raw_number}': {e}")
                    results["Resultados_por_formato"][num_format] = f"Error: {str(e)}"
                    continue
            
            results["Enlaces_relacionados"] = list(results["Enlaces_relacionados"])[:10]
            return results
        except Exception as e:
            logger.error(f"Error general en check_google_search para '{self.raw_number}': {e}")
            return {"error": f"Búsqueda en Google fallida: {str(e)}"}

    def check_social_media(self) -> Dict[str, str]:
        """Genera enlaces para buscar en redes sociales."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            clean_num = phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.E164).replace("+", "")
            
            social_media_links = {
                platform: template.format(clean_num=clean_num)
                for platform, template in SOCIAL_MEDIA_TEMPLATES.items()
            }
            
            return social_media_links
        except Exception as e:
            logger.error(f"Error en check_social_media para '{self.raw_number}': {e}")
            return {"error": f"No se pudieron generar enlaces de redes sociales: {str(e)}"}

    def check_carrier_info(self) -> Dict[str, Any]:
        """Información detallada de la operadora con base de datos local."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            carrier_name = carrier.name_for_number(self.parsed_number, "en") or "Desconocida"
            
            carrier_info = {"Operadora": carrier_name}
            
            for name, data in CARRIERS_DB.items():
                if name.lower() in carrier_name.lower():
                    tld = data.get("tld", {}).get(self.country_code, "com")
                    sitio = data["sitio"].format(tld=tld)
                    
                    carrier_info.update({
                        "Sitio web oficial": f"https://www.{sitio}",
                        "Países de operación": data["países"],
                        "Servicios ofrecidos": data["tipo"],
                        "Identificada_en_BD": True
                    })
                    break
            else:
                carrier_info["Identificada_en_BD"] = False
            
            return carrier_info
        except Exception as e:
            logger.error(f"Error en check_carrier_info para '{self.raw_number}': {e}")
            return {"error": f"No se pudo obtener información de la operadora: {str(e)}"}

    def check_number_reputation(self) -> Dict[str, Any]:
        """Análisis de reputación mejorado con detección de patrones."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            risk_factors = 0
            matched_patterns = []
            
            for pattern in SUSPICIOUS_PATTERNS:
                if re.search(pattern, self.national_number_str):
                    risk_factors += 1
                    matched_patterns.append(pattern)
            
            if self.country_code.upper() in COUNTRY_SPECIFIC_RISKS:
                for pattern in COUNTRY_SPECIFIC_RISKS[self.country_code.upper()]:
                    if re.search(pattern, self.national_number_str):
                        risk_factors += 2  # Más riesgo si coincide con patrones del país
                        matched_patterns.append(f"Específico_{self.country_code.upper()}:{pattern}")
            
            reputation = "Baja"
            if risk_factors > 3:
                reputation = "Muy Alta"
            elif risk_factors > 2:
                reputation = "Alta"
            elif risk_factors > 1:
                reputation = "Media"
            
            return {
                "Factores_de_riesgo": risk_factors,
                "Patrones_sospechosos": matched_patterns if matched_patterns else "Ninguno detectado",
                "Calificación_de_reputación": reputation,
                "Recomendación": "Extrema precaución" if risk_factors > 3 else 
                                "Precaución" if risk_factors > 1 else 
                                "Parece legítimo",
                "Notas": "Números con patrones repetitivos o secuenciales son comúnmente usados para spam/fraude" if risk_factors > 0 else ""
            }
        except Exception as e:
            logger.error(f"Error en check_number_reputation para '{self.raw_number}': {e}")
            return {"error": f"Error al verificar reputación del número: {str(e)}"}

    def check_phone_blacklists(self) -> Dict[str, str]:
        """Verificación en listas negras públicas."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            clean_num = phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.E164).replace("+", "")
            
            blacklist_links = {
                site: template.format(clean_num=clean_num)
                for site, template in BLACKLIST_TEMPLATES.items()
            }
            
            return blacklist_links
        except Exception as e:
            logger.error(f"Error en check_phone_blacklists para '{self.raw_number}': {e}")
            return {"error": f"No se pudieron generar enlaces de listas negras: {str(e)}"}

    def check_phone_format_variations(self) -> Dict[str, str]:
        """Genera todas las variaciones de formato posibles."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            variations = {
                "E164": phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.E164),
                "Internacional": phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
                "Nacional": phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.NATIONAL),
                "RFC3966": phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.RFC3966),
                "Sin_formato": self.national_number_str,
                "Solo_código_de_área": self._get_area_code(),
                "Solo_línea": self._get_line_number(),
                "Sin_ceros": self.national_number_str.lstrip('0'),
                "Últimos_4_dígitos": self.national_number_str[-4:],
                "Últimos_7_dígitos": self.national_number_str[-7:] if len(self.national_number_str) >= 7 else self.national_number_str,
                "Con_guiones": re.sub(r'(\d{3})(\d{3})(\d{4})', r'\1-\2-\3', self.national_number_str) if len(self.national_number_str) == 10 else self.national_number_str,
                "Con_espacios": re.sub(r'(\d{3})(\d{3})(\d{4})', r'\1 \2 \3', self.national_number_str) if len(self.national_number_str) == 10 else self.national_number_str
            }
            
            return variations
        except Exception as e:
            logger.error(f"Error en check_phone_format_variations para '{self.raw_number}': {e}")
            return {"error": f"Error al generar variaciones de formato: {str(e)}"}

    def check_voip_providers(self) -> Dict[str, Any]:
        """Identifica si el número pertenece a proveedores VoIP conocidos."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            e164 = phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.E164)
            national = self.national_number_str
            
            voip_matches = []
            for provider, patterns in VOIP_PROVIDERS.items():
                for pattern in patterns.get("number_patterns", []):
                    if re.match(pattern, national) or re.match(pattern, e164.replace("+", "")):
                        voip_matches.append({
                            "proveedor": provider,
                            "tipo": patterns.get("type", "VoIP"),
                            "sitio_web": patterns.get("website", "N/A"),
                            "notas": patterns.get("notes", "")
                        })
            
            return {
                "es_voip": len(voip_matches) > 0,
                "proveedores_detectados": voip_matches,
                "riesgo_voip": "Alto" if len(voip_matches) > 0 else "Bajo",
                "notas": "Los números VoIP son comúnmente usados para spam/scam debido a su fácil adquisición"
            }
        except Exception as e:
            logger.error(f"Error en check_voip_providers para '{self.raw_number}': {e}")
            return {"error": str(e)}

    def check_breach_databases(self) -> Dict[str, Any]:
        """Verifica si el número aparece en bases de datos de filtraciones conocidas."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            clean_num = phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.E164).replace("+", "")
            
            breach_results = {
                "enlaces_verificacion": {},
                "menciones_en_filtraciones": 0,
                "bases_consultadas": []
            }
            
            for source_name, source_data in BREACH_SOURCES.items():
                url = source_data["url_template"].format(clean_num=clean_num)
                breach_results["enlaces_verificacion"][source_name] = url
                breach_results["bases_consultadas"].append(source_name)
            
            return breach_results
        except Exception as e:
            logger.error(f"Error en check_breach_databases para '{self.raw_number}': {e}")
            return {"error": str(e)}

    def check_email_patterns(self) -> Dict[str, List[str]]:
        """Genera posibles patrones de email asociados al número."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            clean_num = phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.E164).replace("+", "")
            national = self.national_number_str
            
            possible_emails = []
            for pattern in EMAIL_PATTERNS:
                email = pattern.format(
                    number=clean_num,
                    national=national,
                    last7=national[-7:] if len(national) >= 7 else national,
                    last4=national[-4:] if len(national) >= 4 else national
                )
                possible_emails.append(email)
            
            return {
                "patrones_generados": list(set(possible_emails)),
                "total_patrones": len(possible_emails),
                "notas": "Estos son patrones probables. Verificar con OSINT de email adicional."
            }
        except Exception as e:
            logger.error(f"Error en check_email_patterns para '{self.raw_number}': {e}")
            return {"error": str(e)}

    def check_premium_rate(self) -> Dict[str, Any]:
        """Verifica si el número es un número premium rate (tarificación adicional)."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            national = self.national_number_str
            country = self.country_code.upper()
            
            is_premium = False
            rate_info = {}
            
            if country in PREMIUM_RATE_RANGES:
                for rate_type, ranges in PREMIUM_RATE_RANGES[country].items():
                    for prefix in ranges:
                        if national.startswith(prefix):
                            is_premium = True
                            rate_info = {
                                "tipo": rate_type,
                                "prefijo": prefix,
                                "pais": country,
                                "riesgo": "Alto - Números costosos",
                                "recomendacion": "Evitar llamar, pueden tener costos elevados"
                            }
                            break
            
            return {
                "es_premium_rate": is_premium,
                "informacion_tarifa": rate_info if is_premium else {},
                "numero_tipo": "Premium Rate" if is_premium else "Estándar"
            }
        except Exception as e:
            logger.error(f"Error en check_premium_rate para '{self.raw_number}': {e}")
            return {"error": str(e)}

    def advanced_google_dorks(self) -> Dict[str, List[str]]:
        """Genera dorks avanzados de Google para investigación profunda."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            clean_num = phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.E164).replace("+", "")
            national = self.national_number_str
            intl = phonenumbers.format_number(self.parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            
            dorks = {
                "whatsapp": [
                    f'"{clean_num}" site:wa.me',
                    f'"{national}" "WhatsApp" "última vez"'
                ],
                "telegram": [
                    f'"{clean_num}" site:t.me',
                    f'"{national}" "Telegram" user'
                ],
                "foros": [
                    f'"{clean_num}" "foro" OR "forum" OR "hilo"',
                    f'"{national}" "spam" OR "estafa" OR "fraude"'
                ],
                "redes_sociales": [
                    f'"{clean_num}" site:facebook.com OR site:instagram.com',
                    f'"{national}" "perfil" OR "usuario" OR "contacto"'
                ],
                "noticias": [
                    f'"{clean_num}" "noticia" OR "news" OR "prensa"',
                    f'"{national}" "llamadas" OR "teléfono" OR "denuncia"'
                ],
                "laboral": [
                    f'"{clean_num}" "CV" OR "curriculum" OR "LinkedIn"',
                    f'"{national}" "contacto" OR "oficina" OR "trabajo"'
                ]
            }
            
            return dorks
        except Exception as e:
            logger.error(f"Error en advanced_google_dorks para '{self.raw_number}': {e}")
            return {"error": str(e)}

    def check_carrier_footprint(self) -> Dict[str, Any]:
        """Analiza la huella digital de la operadora y su infraestructura."""
        try:
            if not self._check_parsed_number():
                return {"error": "Número no válido o no parseado."}
            
            carrier_name = carrier.name_for_number(self.parsed_number, "en") or "Desconocida"
            
            footprint = {
                "operadora": carrier_name,
                "infraestructura": {},
                "rangos_asignados": {},
                "tecnologias": []
            }
            
            if self.country_code.upper() in COUNTRY_METADATA:
                country_data = COUNTRY_METADATA[self.country_code.upper()]
                footprint["infraestructura"] = {
                    "prefijos_operadora": country_data.get("carrier_prefixes", {}).get(carrier_name, []),
                    "tipo_red": country_data.get("network_types", "Mixto"),
                    "portabilidad": country_data.get("number_portability", False)
                }
            
            return footprint
        except Exception as e:
            logger.error(f"Error en check_carrier_footprint para '{self.raw_number}': {e}")
            return {"error": str(e)}

    def analyze_all(self) -> Dict[str, Any]:
        """
        Ejecuta todas las verificaciones de análisis en paralelo.
        
        Returns:
            Un diccionario con los resultados de todas las verificaciones.
        """
        if not self._check_parsed_number():
            logger.warning(f"Intento de análisis para número no válido: '{self.raw_number}'")
            return {"error": "Número de teléfono no válido o no parseado. No se puede realizar el análisis."}

        check_functions = {
            "Información_básica": self.get_basic_info,
            "Ubicación_aproximada": self.get_approximate_location,
            "Búsqueda_en_Google": self.check_google_search,
            "Redes_sociales": self.check_social_media,
            "Información_de_operadora": self.check_carrier_info,
            "Reputación_del_número": self.check_number_reputation,
            "Listas_negras": self.check_phone_blacklists,
            "Variaciones_de_formato": self.check_phone_format_variations,
            "Proveedores_VoIP": self.check_voip_providers,
            "Bases_de_filtraciones": self.check_breach_databases,
            "Patrones_de_email": self.check_email_patterns,
            "Verificación_tarifa_premium": self.check_premium_rate,
            "Google_Dorks_avanzados": self.advanced_google_dorks,
            "Huella_de_operadora": self.check_carrier_footprint
        }
        
        # parallel_check es una función de utilidad, no un método de la clase
        return parallel_check(self.raw_number, check_functions)