# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y [Versionado Semántico](https://semver.org/lang/es/).

## [2.0.0] - 2026-10-14

Auditoría completa del código v1: corrección de bugs de fondo, honestidad en
las verificaciones y motor de búsqueda propio.

### Añadido
- `dp/search.py`: motor de búsqueda web multi-motor (DDG HTML → DDG Lite →
  Bing → Mojeek) con presupuesto de consultas compartido entre hilos,
  throttle por host, caché en disco (TTL 24 h) y detección de bloqueo por
  motor. Sustituye al scraping directo de Google (timeouts + 429 constantes).
- Resumen de riesgo consolidado (puntuación 0–10, señales, recomendaciones).
- CLI con argparse: `-n`, `-b`, `--region`, `--no-net`, `--max-queries`,
  `--workers`. Sin argumentos arranca el modo interactivo.
- Modo `--no-net`: análisis 100 % local sin peticiones de red.
- Enriquecimiento opcional numverify / Twilio vía variables de entorno
  (`DP_NUMVERIFY_KEY`, `DP_TWILIO_SID` + `DP_TWILIO_TOKEN`).
- Verificación Gravatar (`?d=404`, máx 3 patrones) en el cruce de correos.
- `.gitignore`, `requirements.txt`, `README.md`, `LICENSE`, `CHANGELOG.md`,
  `pyproject.toml`, `.env.example`, `examples/`.
- Reorganización en paquete `dp/` (antes ficheros planos) con entrada
  `python -m dp` y lanzador de compatibilidad `dp.py`.

### Corregido
- **Tipos de línea por enum, no enteros**: v1 detectaba móviles con `[1, 3]`
  (3 = TOLL_FREE) y VoIP con `== 7` (7 = PERSONAL_NUMBER; VOIP = 6). Ahora se
  compara con `phonenumbers.PhoneNumberType.*` por nombre.
- Geolocalización móvil: el regex `^44[0-9]{10}$` de "VoIP UK" de v1 excluía
  TODO número británico; ahora solo se excluyen líneas no móviles reales
  (verificado en vivo con móviles UK/ES y toll-free/premium US/ES).
- Premium rate: los prefijos por país (1900, 806, 4470...) se comparan contra
  el número NACIONAL; v1 los comparaba contra formatos que nunca matcheaban.
- HIBP: URL correcta de búsqueda por teléfono (`/phone/`, no `/account/`).
- Cruce de correos: v1 aceptaba CUALQUIER email del SERP (correos ajenos);
  ahora solo se aceptan emails vinculados al número y se cuentan los
  descartados por el filtro.
- Bing: sus enlaces llegan como redirect `bing.com/ck/a?...&u=a1<base64url>`;
  sin desenrutarlos, todos los resultados se filtraban y Bing devolvía 0 hits.
- Encoding: stdout/stderr forzados a UTF-8 con `errors="replace"` (las
  consolas cp1252 ya no revientan), log en UTF-8, CSV con BOM utf-8-sig,
  HTML escapado con `html.escape`.
- `parallel_check` ya no duerme entre sumisiones (solo el throttle real de
  red espacia peticiones) y cancela futuros en Ctrl+C.
- wa.me: documentado que responde 200 para CUALQUIER número (no es
  verificación de existencia); Telegram solo detecta alias numérico.

### Eliminado
- Scraping directo de Google (módulo `check_google_search` de v1).
- `LOCAL_FORMATS_DB` (las lambdas perdían dígitos); el formato local sale de
  `phonenumbers`.
- Regex de "patrones VoIP" por prefijo (irreparables: matcheaban todo un país
  o nada).
- Plantillas inválidas (Signal) y sin búsqueda por teléfono (LinkedIn,
  Snapchat).

## [1.0.0] - fecha inicial

- Versión original: analizador monolítico de 16 módulos con scraping de
  Google, detección VoIP por regex y exportes TXT/JSON/CSV/HTML.
