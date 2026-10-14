# -*- coding: utf-8 -*-
"""
phone_data.py - Bases de datos estaticas v2 del analizador OSINT.

Cambios v2 (auditoria):
- ELIMINADO LOCAL_FORMATS_DB: las lambdas perdian digitos (FR/AR). El formato
  local se obtiene con phonenumbers (PhoneNumberFormat.NATIONAL).
- ELIMINADOS los "number_patterns" regex de VoIP: eran irreparables
  (^44[0-9]{10}$ matcheaba TODO numero UK; ^1[0-9]{9}$ nunca matcheaba un US
  de 11 digitos). La deteccion VoIP/premium/toll-free usa
  phonenumbers.number_type() (verdad de terreno) en phone_analyzer.py.
  Aqui queda VOIP_PROVIDER_INFO solo como contexto (sitio web, indicadores).
- PREMIUM_RATE_INFO / TOLL_FREE_INFO: prefijos comparables contra el numero
  NACIONAL sin prefijo de pais (los antiguos "1900"/"4470" nunca matcheaban).
- HIBP: URL correcta de busqueda por telefono (/phone/, no /account/).
- Plantillas con placeholders unificados: {e164_digits}, {national},
  {national_dashed}, {region}, {region_lower}, {tld}, {last7}, {last4}.
- SOCIAL_MEDIA_TEMPLATES: solo enlaces de busqueda manual honestos; eliminados
  Signal (URL invalida) y LinkedIn/Snapchat (sin busqueda por telefono).
"""

import phonenumbers

# Mapeo de tipos de numero construido DESDE el enum (sin enteros magicos).
# El codigo original usaba enteros hardcodeados erroneos:
#   is_mobile -> [1, 3] cuando 3 es TOLL_FREE (no FIXED_LINE_OR_MOBILE=2)
#   is_voip   -> ==7 cuando 7 es PERSONAL_NUMBER (no VOIP=6)
NUMBER_TYPE_MAP = {
    phonenumbers.PhoneNumberType.FIXED_LINE: "Fijo",
    phonenumbers.PhoneNumberType.MOBILE: "Móvil",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fijo/Móvil",
    phonenumbers.PhoneNumberType.TOLL_FREE: "Toll Free (gratuito)",
    phonenumbers.PhoneNumberType.PREMIUM_RATE: "Premium Rate",
    phonenumbers.PhoneNumberType.SHARED_COST: "Coste compartido",
    phonenumbers.PhoneNumberType.VOIP: "VoIP",
    phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "Número personal",
    phonenumbers.PhoneNumberType.PAGER: "Pager",
    phonenumbers.PhoneNumberType.UAN: "UAN (número corporativo)",
    phonenumbers.PhoneNumberType.VOICEMAIL: "Buzón de voz",
    -1: "Desconocido",
}

# Mapeo de códigos de área por país (número de dígitos iniciales del nacional).
# Heurístico: la portabilidad y los prefijos geográficos variables lo limitan.
AREA_CODE_RULES = {
    "US": 3, "CA": 3, "BR": 2,
    "GB": 2, "DE": 2, "FR": 2, "ES": 3,
    "MX": 3, "AR": 4, "CO": 3, "CL": 1,
    "PE": 3, "AU": 1, "NZ": 1, "IN": 2
}

# Reglas por país para el número de línea (últimos dígitos). Heurístico.
LINE_RULES = {
    "US": 7, "CA": 7, "BR": 8,
    "ES": 6, "MX": 7, "AR": 6,
    "CO": 7, "CL": 8, "PE": 6,
    "FR": 8, "DE": 8, "IT": 7,
    "GB": 7, "AU": 8, "NZ": 7
}

# Base local de operadoras: coincidencia por subcadena del nombre que devuelve
# phonenumbers. "sitio" admite {tld}; el TLD se resuelve con el mapa "tld".
CARRIERS_DB = {
    "Movistar": {
        "países": ["ES", "AR", "CL", "PE", "CO", "EC", "UY", "VE"],
        "sitio": "movistar.{tld}",
        "tld": {"ES": "es", "AR": "com.ar", "CL": "cl", "PE": "pe", "CO": "co",
                "EC": "ec", "UY": "com.uy", "VE": "com.ve"},
        "tipo": ["Móvil", "Fijo", "Internet"]
    },
    "Vodafone": {
        "países": ["ES", "GB", "DE", "IT", "PT", "IE", "NL", "GR"],
        "sitio": "vodafone.{tld}",
        "tld": {"ES": "es", "GB": "co.uk", "DE": "de", "IT": "it", "PT": "pt",
                "IE": "ie", "NL": "nl", "GR": "gr"},
        "tipo": ["Móvil", "Fijo", "Internet"]
    },
    "Orange": {
        "países": ["ES", "FR", "PL", "BE", "RO", "SK", "MD"],
        "sitio": "orange.{tld}",
        "tld": {"ES": "es", "FR": "fr", "PL": "pl", "BE": "be", "RO": "ro",
                "SK": "sk", "MD": "md"},
        "tipo": ["Móvil", "Fijo", "Internet", "TV"]
    },
    "Claro": {
        "países": ["BR", "MX", "AR", "CO", "CL", "PE", "EC", "DO", "PA", "NI",
                   "GT", "SV", "HN", "CR"],
        "sitio": "claro{tld}",
        "tld": {"BR": ".com.br", "MX": ".com.mx", "AR": ".com.ar",
                "CO": ".com.co", "CL": ".cl", "PE": ".pe", "EC": ".com.ec"},
        "tipo": ["Móvil", "Fijo", "Internet", "TV"]
    },
    "T-Mobile": {
        "países": ["US", "DE", "PL", "CZ", "HU", "AT", "NL"],
        "sitio": "t-mobile.{tld}",
        "tld": {"US": "com", "DE": "de", "PL": "pl", "CZ": "cz", "HU": "hu",
                "AT": "at", "NL": "nl"},
        "tipo": ["Móvil", "Internet"]
    },
    "AT&T": {
        "países": ["US", "MX"],
        "sitio": "att.{tld}",
        "tld": {"US": "com", "MX": "com.mx"},
        "tipo": ["Móvil", "Fijo", "Internet", "TV"]
    },
    "Verizon": {
        "países": ["US"],
        "sitio": "verizon.{tld}",
        "tld": {"US": "com"},
        "tipo": ["Móvil", "Fijo", "Internet", "TV"]
    },
    "O2": {
        "países": ["GB", "DE", "ES", "CZ"],
        "sitio": "o2.{tld}",
        "tld": {"GB": "co.uk", "DE": "de", "ES": "es", "CZ": "cz"},
        "tipo": ["Móvil", "Internet"]
    },
    "EE": {
        "países": ["GB"],
        "sitio": "ee.{tld}",
        "tld": {"GB": "co.uk"},
        "tipo": ["Móvil", "Internet"]
    },
    "Three": {
        "países": ["GB", "IT", "SE", "DK", "AT", "HK"],
        "sitio": "three.{tld}",
        "tld": {"GB": "co.uk", "IT": "it", "SE": "se", "DK": "dk", "AT": "at"},
        "tipo": ["Móvil", "Internet"]
    },
    "Telcel": {
        "países": ["MX"],
        "sitio": "telcel.{tld}",
        "tld": {"MX": "com"},
        "tipo": ["Móvil", "Internet"]
    },
    "Jazztel": {
        "países": ["ES"],
        "sitio": "jazztel.{tld}",
        "tld": {"ES": "com"},
        "tipo": ["Móvil", "Fijo", "Internet"]
    },
    "Yoigo": {
        "países": ["ES"],
        "sitio": "yoigo.{tld}",
        "tld": {"ES": "com"},
        "tipo": ["Móvil", "Internet"]
    },
    "SFR": {
        "países": ["FR"],
        "sitio": "sfr.{tld}",
        "tld": {"FR": "fr"},
        "tipo": ["Móvil", "Fijo", "Internet", "TV"]
    },
    "Bouygues Telecom": {
        "países": ["FR"],
        "sitio": "bouyguestelecom.{tld}",
        "tld": {"FR": "fr"},
        "tipo": ["Móvil", "Fijo", "Internet", "TV"]
    },
    "Free": {
        "países": ["FR"],
        "sitio": "free.{tld}",
        "tld": {"FR": "fr"},
        "tipo": ["Móvil", "Fijo", "Internet", "TV"]
    },
}

# Patrones de números sospechosos para análisis de reputación (heurístico).
SUSPICIOUS_PATTERNS = [
    r'(\d)\1{5,}',       # 6+ dígitos repetidos
    r'123456\d*',        # Secuencia ascendente
    r'654321\d*',        # Secuencia descendente
    r'(\d{3})\1',        # Patrones repetidos (ej: 123123)
    r'^0{5,}',           # Muchos ceros al inicio
    r'^1{5,}',           # Muchos unos al inicio
    r'^(\d)\d\1\d\1\d',  # Patrón alternante (ej: 121212)
    r'^555\d{4}',        # Números ficticios (US)
    r'^999\d{4}',        # Números ficticios (UK)
    r'^123123',
    r'^321321',
    r'^(\d{2})\1\1',
    r'^(\d)\1(\d)\2(\d)\3'
]

# Reglas específicas por país para reputación, comparadas contra el número
# NACIONAL (sin código de país, sin 0 inicial). v1 comparaba prefijos con el
# prefijo de país incluido ("^4479") y nunca matcheaba.
COUNTRY_SPECIFIC_RISKS = {
    "US": ["^555", "^900", "^976", "^411"],
    "GB": ["^999", "^555", "^70", "^90"],
    "ES": ["^900", "^901", "^902", "^803", "^806", "^807"],
    "MX": ["^900"],
    "FR": ["^0899", "^0897", "^0892", "^0891"],
}

# Enlaces de búsqueda MANUAL en redes (no afirman verificación).
SOCIAL_MEDIA_TEMPLATES = {
    "Facebook (recuperación por teléfono)":
        "https://www.facebook.com/login/identify/?ctx=recover&phone={e164_digits}",
    "X/Twitter (búsqueda)":
        "https://x.com/search?q=%22{e164_digits}%22&src=typed_query",
    "Instagram (recuperación)":
        "https://www.instagram.com/accounts/account_recovery/?phone_number={e164_digits}",
    "TikTok (búsqueda)":
        "https://www.tiktok.com/search?q={e164_digits}",
    "VK (búsqueda de personas)":
        "https://vk.com/people/{e164_digits}",
    "Telegram (búsqueda web del alias)":
        "https://t.me/{national}",
}

# Enlaces a listas negras públicas (verificación manual).
BLACKLIST_TEMPLATES = {
    "ShouldIAnswer": "https://www.shouldianswer.com/phone-number/{e164_digits}",
    "CallerCenter": "https://callercenter.com/{e164_digits}",
    "SpamCalls.net": "https://spamcalls.net/en/number/%2B{e164_digits}",
    "Tellows": "https://www.tellows.{tld}/num/{e164_digits}",
    "Sync.me": "https://sync.me/search/?number=%2B{e164_digits}",
    "Truecaller": "https://www.truecaller.com/search/{region_lower}/{national}",
    "WhoCallsMe (UK)": "https://whocallsme.com/Phone-Number.aspx/{national}",
}

# TLDs de Tellows por país (fallback "com" para el resto).
TELLOWS_TLDS = {
    "ES": "es", "GB": "co.uk", "DE": "de", "FR": "fr", "IT": "it",
    "US": "com", "NL": "nl", "AT": "at", "CH": "ch", "PT": "pt",
    "PL": "pl", "SE": "se", "DK": "dk", "NO": "no", "FI": "fi",
}

# People-search (enlaces manuales; la mayoría son EE. UU.).
PEOPLE_SEARCH_TEMPLATES = {
    "TruePeopleSearch (US)": "https://www.truepeoplesearch.com/results?phoneno={e164_digits}",
    "FastPeopleSearch (US)": "https://www.fastpeoplesearch.com/{e164_digits}",
    "That'sThem (US)": "https://thatsthem.com/phone/{e164_digits}",
    "Spokeo (US)": "https://www.spokeo.com/{national_dashed}",
    "Whitepages (US)": "https://www.whitepages.com/phone/{e164_digits}",
    "Sync.me (global)": "https://sync.me/search/?number=%2B{e164_digits}",
}

# User-Agents modernos para rotación.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Android 14; Mobile; rv:126.0) Gecko/126.0 Firefox/126.0",
]

# Info de contexto de proveedores VoIP: la DETECCIÓN se hace por tipo de línea
# (number_type) y de forma heurística por el nombre de operadora ("indicadores"
# son subcadenas a buscar en carrier.name_for_number). No hay regex de números.
VOIP_PROVIDER_INFO = {
    "Google Voice": {
        "sitio": "voice.google.com",
        "indicadores": ["google voice", "grand central"],
        "notas": "Números gratuitos de Google, muy usados para verificaciones."
    },
    "Twilio": {
        "sitio": "twilio.com",
        "indicadores": ["twilio"],
        "notas": "CPaaS; usado por bots y servicios automatizados."
    },
    "Skype": {
        "sitio": "skype.com",
        "indicadores": ["skype"],
        "notas": "Números de Skype para llamadas externas."
    },
    "Vonage/Nexmo": {
        "sitio": "vonage.com",
        "indicadores": ["vonage", "nexmo"],
        "notas": "VoIP empresarial y APIs de mensajería."
    },
    "Bandwidth": {
        "sitio": "bandwidth.com",
        "indicadores": ["bandwidth"],
        "notas": "Operadora VoIP/CPaaS mayorista en EE. UU."
    },
    "Telnyx": {
        "sitio": "telnyx.com",
        "indicadores": ["telnyx"],
        "notas": "CPaaS mayorista."
    },
    "Plivo": {
        "sitio": "plivo.com",
        "indicadores": ["plivo"],
        "notas": "CPaaS."
    },
    "Sinch": {
        "sitio": "sinch.com",
        "indicadores": ["sinch"],
        "notas": "CPaaS."
    },
    "TextNow": {
        "sitio": "textnow.com",
        "indicadores": ["textnow"],
        "notas": "VoIP gratuito para mensajería/llamadas en EE. UU. y Canadá."
    },
    "Zoom Phone": {
        "sitio": "zoom.us",
        "indicadores": ["zoom phone", "zoom telephony"],
        "notas": "Telefonía corporativa en la nube."
    },
    "Microsoft Teams Phone": {
        "sitio": "microsoft.com",
        "indicadores": ["microsoft teams", "microsoft phone"],
        "notas": "Telefonía corporativa en la nube."
    },
}

# Fuentes de filtraciones: enlaces de verificación MANUAL.
# HIBP: la búsqueda por teléfono es /phone/%2BXXXXXXXX (no /account/).
BREACH_SOURCES = {
    "HaveIBeenPwned": {
        "url_template": "https://haveibeenpwned.com/phone/%2B{e164_digits}",
        "notes": "Búsqueda por teléfono (cuenta no requerida para la vista web)."
    },
    "BreachDirectory": {
        "url_template": "https://breachdirectory.org/?query={e164_digits}",
        "notes": "Motor de búsqueda de filtraciones."
    },
    "LeakCheck": {
        "url_template": "https://leakcheck.io/search?q={e164_digits}",
        "notes": "Requiere interacción; disponibilidad intermitente."
    },
    "DeHashed": {
        "url_template": "https://dehashed.com/search?query=%22{e164_digits}%22",
        "notes": "Requiere cuenta para ver resultados."
    },
}

# Patrones de email PROBABLES (hipótesis, no verificaciones).
EMAIL_PATTERNS = [
    "{number}@gmail.com",
    "{number}@yahoo.com",
    "{number}@hotmail.com",
    "{number}@outlook.com",
    "{national}@gmail.com",
    "{last7}@gmail.com",
    "{last4}@gmail.com",
    "phone{number}@gmail.com",
    "num{national}@yahoo.com",
]

# Prefijos PREMIUM comparables contra el número NACIONAL sin prefijo de país.
# v1 usaba "1900" (US) y "4470" (GB) contra el nacional: nunca matcheaban.
# La detección principal es number_type()==PREMIUM_RATE; esto es metadato.
PREMIUM_RATE_INFO = {
    "US": {
        "prefijos": {
            "900": "Premium 1-900",
            "976": "Premium 1-976",
        },
        "notas": "1-900/1-976: tarificación elevada por llamada/minuto."
    },
    "ES": {
        "prefijos": {
            "803": "Ocio y entretenimiento",
            "806": "Ocio y entretenimiento",
            "807": "Ocio y entretenimiento",
            "905": "Micropagos",
            "909": "Tarificación adicional",
            "901": "Tarificación adicional",
            "902": "Tarificación adicional (empresas)",
        },
        "notas": "803/806/807 son tarificación adicional; 902 puede ser costoso desde móvil."
    },
    "GB": {
        "prefijos": {
            "90": "Premium 090x",
            "871": "Servicio 0871",
            "872": "Servicio 0872",
            "873": "Servicio 0873",
            "118": "Directorios 118",
            "70": "Personal 070 (coste elevado)",
        },
        "notas": "090 y 070 son los más caros; 0871-0873 y 118 tarificación adicional."
    },
    "MX": {
        "prefijos": {
            "900": "Tarificación especial",
        },
        "notas": "Prefijos 900 de tarificación especial."
    },
}

# Prefijos toll-free de referencia (detección principal: number_type()).
TOLL_FREE_INFO = {
    "US": ["800", "833", "844", "855", "866", "877", "888"],
    "ES": ["900"],
    "GB": ["800", "808"],
    "MX": ["800"],
    "FR": ["80"],
    "DE": ["800"],
}

# Dorks con placeholders; el analizador ejecuta algunos vía SearchClient y el
# resto queda como enlaces manuales a Google.
DORK_TEMPLATES = {
    "presencia_general": [
        '"{e164_digits}"',
        '"{national}" OR "{last7}"',
    ],
    "redes_sociales": [
        '"{e164_digits}" (site:facebook.com OR site:instagram.com OR site:tiktok.com OR site:x.com OR site:vk.com)',
    ],
    "mensajeria": [
        '"{e164_digits}" (site:wa.me OR site:t.me OR site:telegram.me)',
    ],
    "filtraciones": [
        '"{e164_digits}" (dump OR leak OR breach OR pastebin OR "filtración")',
    ],
    "documentos": [
        '"{e164_digits}" (filetype:pdf OR filetype:xls OR filetype:xlsx OR filetype:csv OR filetype:txt)',
    ],
    "reputacion": [
        '"{e164_digits}" (spam OR scam OR estafa OR fraude OR review)',
    ],
    "clasificados": [
        '"{e164_digits}" (site:milanuncios.com OR site:wallapop.com OR site:craigslist.org)',
    ],
}

# Metadatos por país para OSINT avanzado (contexto, no hechos).
COUNTRY_METADATA = {
    "US": {
        "network_types": "CDMA/GSM/LTE/5G",
        "number_portability": True,
        "carrier_prefixes": {
            "Verizon": ["201", "202", "203"],
            "AT&T": ["204", "205", "206"],
            "T-Mobile": ["207", "208", "209"]
        },
        "area_code_database": "https://www.area-codes.com/",
        "notas": "Alta portabilidad numérica: la operadora actual puede no ser la original."
    },
    "ES": {
        "network_types": "GSM/LTE/5G",
        "number_portability": True,
        "carrier_prefixes": {
            "Movistar": ["600", "610", "620"],
            "Vodafone": ["650", "660", "670"],
            "Orange": ["680", "690"]
        },
        "notas": "Los prefijos 600/700 son móviles; 900 tarificación especial."
    },
    "MX": {
        "network_types": "GSM/LTE/5G",
        "number_portability": True,
        "carrier_prefixes": {
            "Telcel": ["55", "56", "81"],
            "Movistar": ["44", "45"],
            "AT&T": ["48", "49"]
        },
        "notas": "Desde 2019 el marcado a 10 dígitos es obligatorio; la LADA ya no identifica región."
    },
    "GB": {
        "network_types": "GSM/LTE/5G",
        "number_portability": True,
        "carrier_prefixes": {
            "EE": ["74", "75", "77"],
            "O2": ["73", "78"],
            "Vodafone": ["71", "72", "79"]
        },
        "notas": "Números 07x son móviles; 0800 gratuitos."
    }
}

# APIs de enriquecimiento OPCIONAL: se usan solo si hay claves en el entorno.
API_ENDPOINTS = {
    "numverify": {
        "url": "https://apilayer.net/api/validate?access_key={key}&number={e164_digits}",
        "auth_env": "DP_NUMVERIFY_KEY",
        "notas": "Freemium: HTTPS solo en plan de pago (el plan gratuito puede usar http://)."
    },
    "twilio_lookup": {
        "url": "https://lookups.twilio.com/v1/PhoneNumbers/%2B{e164_digits}?Type=carrier",
        "auth_env": ["DP_TWILIO_SID", "DP_TWILIO_TOKEN"],
        "notas": "HTTP Basic con Account SID + Auth Token."
    },
}
