"""
Este módulo contiene todas las constantes y bases de datos estáticas
utilizadas por el analizador de números telefónicos.
"""

# Mapeo extendido de tipos de número de phonenumbers
NUMBER_TYPE_MAP = {
    0: "Fijo",
    1: "Móvil",
    2: "Fijo",
    3: "Móvil",
    4: "Toll Free",
    5: "Premium Rate",
    6: "Shared Cost",
    7: "VoIP",
    8: "Personal Number",
    9: "Pager",
    10: "UAN",
    11: "Desconocido",
    12: "Emergencia",
    13: "Voicemail",
    14: "Servicio Corto"
}

# Base de datos de formatos locales por país (para `get_country_specific_info` y `get_local_format`)
LOCAL_FORMATS_DB = {
    "US": lambda national_num: f"({national_num[:3]}) {national_num[3:6]}-{national_num[6:]}",
    "ES": lambda national_num: f"{national_num[:3]} {national_num[3:6]} {national_num[6:]}",
    "MX": lambda national_num: f"{national_num[:3]} {national_num[3:7]} {national_num[7:]}",
    "AR": lambda national_num: f"{national_num[:4]} {national_num[4:8]}",
    "BR": lambda national_num: f"({national_num[:2]}) {national_num[2:7]}-{national_num[7:]}",
    "CO": lambda national_num: f"{national_num[:3]} {national_num[3:6]} {national_num[6:]}",
    "CL": lambda national_num: f"{national_num[:1]} {national_num[1:5]} {national_num[5:]}",
    "PE": lambda national_num: f"{national_num[:3]} {national_num[3:6]} {national_num[6:]}",
    "FR": lambda national_num: f"{national_num[:1]} {national_num[1:2]} {national_num[2:4]} {national_num[4:6]} {national_num[6:8]}",
    "DE": lambda national_num: f"{national_num[:2]}-{national_num[2:4]}-{national_num[4:]}",
    "IT": lambda national_num: f"{national_num[:3]} {national_num[3:7]} {national_num[7:]}",
    "GB": lambda national_num: f"{national_num[:4]} {national_num[4:6]} {national_num[6:]}"
}

# Mapeo de códigos de área por país (número de dígitos)
AREA_CODE_RULES = {
    "US": 3, "CA": 3, "BR": 2,
    "GB": 2, "DE": 2, "FR": 2, "ES": 3,
    "MX": 3, "AR": 4, "CO": 3, "CL": 1,
    "PE": 3, "AU": 1, "NZ": 1, "IN": 2
}

# Reglas por país para el número de línea (últimos dígitos)
LINE_RULES = {
    "US": 7, "CA": 7, "BR": 8,
    "ES": 6, "MX": 7, "AR": 6,
    "CO": 7, "CL": 8, "PE": 6,
    "FR": 8, "DE": 8, "IT": 7,
    "GB": 7, "AU": 8, "NZ": 7
}

# Base de datos local de operadoras
CARRIERS_DB = {
    "Movistar": {
        "países": ["ES", "AR", "CL", "PE", "CO", "EC", "UY", "VE"],
        "sitio": "movistar.{tld}",
        "tld": {"ES": "es", "AR": "com.ar", "CL": "cl", "PE": "pe", "CO": "co", "EC": "ec", "UY": "com.uy", "VE": "com.ve"},
        "tipo": ["Móvil", "Fijo", "Internet"]
    },
    "Vodafone": {
        "países": ["ES", "GB", "DE", "IT", "PT", "IE", "NL", "GR"],
        "sitio": "vodafone.{tld}",
        "tld": {"ES": "es", "GB": "co.uk", "DE": "de", "IT": "it", "PT": "pt", "IE": "ie", "NL": "nl", "GR": "gr"},
        "tipo": ["Móvil", "Fijo", "Internet"]
    },
    "Claro": {
        "países": ["BR", "MX", "AR", "CO", "CL", "PE", "EC", "DO", "PA", "NI", "GT", "SV", "HN", "CR"],
        "sitio": "claro{tld}",
        "tld": {"BR": ".com.br", "MX": ".com.mx", "AR": ".com.ar", "CO": ".com.co", "CL": ".cl", "PE": ".pe", "EC": ".com.ec"},
        "tipo": ["Móvil", "Fijo", "Internet", "TV"]
    },
    "T-Mobile": {
        "países": ["US", "DE", "PL", "CZ", "HU", "AT", "NL"],
        "sitio": "t-mobile.{tld}",
        "tld": {"US": "com", "DE": "de", "PL": "pl", "CZ": "cz", "HU": "hu", "AT": "at", "NL": "nl"},
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
        "sitio": "verizon.com",
        "tipo": ["Móvil", "Fijo", "Internet", "TV"]
    },
    "Orange": {
        "países": ["ES", "FR", "PL", "BE", "RO", "SK", "MD"],
        "sitio": "orange.{tld}",
        "tld": {"ES": "es", "FR": "fr", "PL": "pl", "BE": "be", "RO": "ro", "SK": "sk", "MD": "md"},
        "tipo": ["Móvil", "Fijo", "Internet", "TV"]
    }
}

# Patrones de números sospechosos para análisis de reputación
SUSPICIOUS_PATTERNS = [
    r'(\d)\1{5,}',      # 6+ dígitos repetidos
    r'123456\d*',        # Secuencia ascendente
    r'654321\d*',        # Secuencia descendente
    r'(\d{3})\1',        # Patrones repetidos (ej: 123123)
    r'^0{5,}',           # Muchos ceros al inicio
    r'^1{5,}',           # Muchos unos al inicio
    r'^(\d)\d\1\d\1\d',  # Patrón alternante (ej: 121212)
    r'^555\d{4}',        # Números ficticios (US)
    r'^999\d{4}',        # Números ficticios (UK)
    r'^123123',          # Patrón obvio
    r'^321321',          # Patrón obvio inverso
    r'^(\d{2})\1\1',     # Repetición de pares (ej: 121212)
    r'^(\d)\1(\d)\2(\d)\3'  # Patrón AABBCC
]

# Reglas específicas por país para reputación
COUNTRY_SPECIFIC_RISKS = {
    "US": ["^555", "^800", "^900", "^456", "^411"],
    "GB": ["^999", "^555", "^4479", "^4480"],
    "ES": ["^900", "^901", "^902", "^803", "^806", "^807"],
    "MX": ["^900", "^800", "^555", "^123"]
}

# Plantillas de enlaces para redes sociales
SOCIAL_MEDIA_TEMPLATES = {
    "Facebook": "https://www.facebook.com/login/identify/?ctx=recover&phone={clean_num}",
    "Twitter": "https://twitter.com/search?q={clean_num}&src=typed_query",
    "Instagram": "https://www.instagram.com/accounts/account_recovery/?phone_number={clean_num}",
    "LinkedIn": "https://www.linkedin.com/pub/dir/?phone={clean_num}",
    "VK": "https://vk.com/people/{clean_num}",
    "Telegram": "https://t.me/{clean_num}",
    "WhatsApp": "https://wa.me/{clean_num}",
    "Signal": "https://signal.me/#p/{clean_num}",
    "TikTok": "https://www.tiktok.com/search?q={clean_num}",
    "Snapchat": "https://www.snapchat.com/add/{clean_num}"
}

# Plantillas de enlaces para listas negras públicas
BLACKLIST_TEMPLATES = {
    "ShouldIAnswer": "https://www.shouldianswer.com/phone/{clean_num}",
    "CallerCenter": "https://callercenter.com/{clean_num}",
    "PhoneBook": "https://www.phonebook.com/phone/{clean_num}",
    "SpamCalls": "https://spamcalls.net/en/search?q={clean_num}",
    "Numspy": "https://numspy.io/number/{clean_num}",
    "Tellows": "https://www.tellows.es/num/{clean_num}",
    "Sync.me": "https://sync.me/search/?number={clean_num}",
    "Truecaller": "https://www.truecaller.com/search/{clean_num}"
}

# Lista de User-Agents para rotación y evasión de bloqueos en búsquedas web
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"
]