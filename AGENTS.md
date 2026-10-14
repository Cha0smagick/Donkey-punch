# AGENTS.md - Donkey Punch Phone OSINT Tool

## Quick Start
```bash
python dp.py                      # modo interactivo (lanzador de compatibilidad)
python -m dp                      # equivalente, vía paquete
python dp.py -n +34612345678      # un número
python dp.py -n +34... -n +52...  # varios
python dp.py -b examples/lote_ejemplo.txt   # lote desde fichero
python dp.py -n +34612345678 --no-net   # solo módulos locales
python dp.py -n +34612345678 --max-queries 4 --workers 2
```
Required packages (`requirements.txt`): `phonenumbers`, `requests`, `beautifulsoup4`.
Opcional: `pip install -e .` instala el comando `dp`.

## Repository Layout
```
dp.py                  # shim de compatibilidad -> dp.cli.main
dp/                    # paquete principal
  __init__.py          # __version__ + API pública (PhoneNumberAnalyzer)
  __main__.py          # entrada de python -m dp
  cli.py               # CLI: argparse, display, batch, exportes
  analyzer.py          # núcleo: 19 módulos + resumen de riesgo
  search.py            # motor multi-motor, presupuesto y caché
  utils.py             # logging, HTTP con throttle, paralelismo, exportes
  data.py              # BD estática: carriers, prefijos, plantillas, APIs
examples/lote_ejemplo.txt
README.md / LICENSE / CHANGELOG.md / pyproject.toml / .env.example
```
Las importaciones entre módulos del paquete son RELATIVAS (`from .utils
import ...`): un módulo nuevo dentro de `dp/` debe seguirlas.

## Architecture (v2)
- **dp/cli.py** - CLI con argparse (`-n/-b/--region/--no-net/--max-queries/--workers`), display a las claves v2, reportes en `reports/`, Ctrl+C limpio, stdout/stderr forzados a UTF-8 (consolas cp1252 no revientan).
- **dp/analyzer.py** - `PhoneNumberAnalyzer` con 19 módulos + resumen de riesgo consolidado. Úsalo como biblioteca: `from dp import PhoneNumberAnalyzer`.
- **dp/search.py** - Motor de búsqueda web multi-motor con degradación: DDG HTML → DDG Lite → Bing → Mojeek. Presupuesto de consultas compartido entre hilos, throttle por host, caché en `dp_cache/search/` (TTL 24 h), detección de bloqueo por motor. Bing trae sus enlaces como redirect `bing.com/ck/a?...&u=a1<base64url>` (desenrutar SIEMPRE o `_dedupe` los filtra). DDG suele devolver 202 (bloqueo suave anti-bot) intermitentemente: no es 429, se marca motor bloqueado y salta al siguiente.
- **dp/data.py** - BD estática: carriers, reglas por país, proveedores VoIP, tarifas premium/toll-free por país, fuentes de filtraciones, plantillas (redes, people-search, dorks, blacklist) y endpoints de API con claves por entorno.
- **dp/utils.py** - Log UTF-8, `make_request` (sesión por hilo + throttle por host + auth opcional), `parallel_check` (futuros con cancelación en Ctrl+C), exportes TXT/JSON/CSV (utf-8-sig)/HTML (con `html.escape`), todo en `reports/`.

## Analysis Modules (19 + resumen)
1. Información básica
2. Ubicación aproximada (geocoder phonenumbers)
3. **Geolocalización móvil** (solo móviles reales; ignora VoIP/fijo/premium/toll-free)
4. Búsqueda web (multi-motor vía `dp.search.SearchClient`, presencias por host)
5. Redes sociales (enlaces manuales + people-search, sin falsas verificaciones)
6. Mensajería (honesto: wa.me responde 200 para cualquier número = solo enlace; Telegram solo detecta alias numérico vía `og:title`)
7. Información de operadora
8. Reputación del número (heurística de patrones)
9. Listas negras (enlaces manuales)
10. Variaciones de formato
11. Detección VoIP (tipo de línea + heurística de operadora)
12. Número gratuito (toll-free)
13. Verificación tarifa premium
14. Bases de filtraciones (enlaces correctos, HIBP `/phone/%2B{e164}` + búsqueda web)
15. **Cruce de correos** (cosecha filtrada: solo emails con dígitos del número o adyacentes a él en el texto + Gravatar md5 `?d=404`, máx 3)
16. Patrones de email (hipótesis)
17. Google Dorks (máx 3 ejecutados vía SearchClient, resto enlaces a Google)
18. Huella de operadora
19. Enriquecimiento API opcional (`DP_NUMVERIFY_KEY`, `DP_TWILIO_SID`+`DP_TWILIO_TOKEN` en entorno; sin claves se omite)
20. **Resumen de riesgo** (puntuación 0-10, Bajo/Moderado/Elevado/Crítico, señales y recomendaciones)

## Truth of terrain (tipos de línea)
- NUNCA usar enteros mágicos: comparar con `phonenumbers.PhoneNumberType.*` por nombre. Enum real: `MOBILE=1, FIXED_LINE_OR_MOBILE=2, TOLL_FREE=3, PREMIUM_RATE=4, VOIP=6, PERSONAL_NUMBER=7`. El código v1 usaba `[1,3]` (3 = Toll Free, no móvil) y `==7` para VoIP (7 = Personal Number): ambos bugs corregidos.
- `is_mobile_number()` → MOBILE o FIXED_LINE_OR_MOBILE.
- `is_voip_or_fixed()` → FIXED_LINE, VOIP o cualquier tipo no móvil (premium, toll-free, UAN...).
- Geolocalización móvil solo corre si NO es voip_or_fixed. Verificado en vivo: +447911123456 (móvil UK) se geolocaliza; +18005551234 (toll-free US) y +34806123456 (premium ES) se ignoran.

## Key Features
- **Búsqueda web con presupuesto** - Máx `--max-queries` (default 8) consultas por número, compartidas entre los 19 módulos; resultados cacheados 24 h.
- **Geolocalización móvil honesta** - Geocoder + CP probable + señales públicas; IP especulativa marcada como tal (ip-api.com, 1.5 s de throttle). No existe "ping GPS" sin operador/orden judicial.
- **Cruce de correos sin ruido** - v1 aceptaba CUALQUIER email del SERP; v2 filtra por vinculación con el número y cuenta los descartados.
- **Verificación Premium Rate** - Por tipo de línea + prefijos por país (comparados contra el NACIONAL, v1 los comparaba contra formatos que nunca matcheaban).
- Reportes en `reports/reporte_{number}_{timestamp}.{json|txt|html}` + CSV/JSON combinados en batch.

## Quirks (v2)
- Sin sleeps entre sumisiones de parallel_check; el throttle real vive en dp/search y dp/utils por host con jitter.
- `SearchClient.search()` nunca lanza: errores y bloqueos van en el dict (`error`, `motor_usado`, `motores_bloqueados` en `stats()`).
- dp/utils REPORTS_DIR = `reports/` (creado al vuelo); CSV con BOM utf-8-sig para Excel.
- Los parsers de motores son defensivos: si el HTML cambia, ese motor devuelve 0 hits y el siguiente toma el relevo. Revisar selectores si TODOS devuelven 0.
- No tests, no linter, no type checker.

## Lógica de geolocalización
- `is_mobile_number()` - enum por nombre (MOBILE / FIXED_LINE_OR_MOBILE).
- `is_voip_or_fixed()` - fijo/VoIP/premium/toll-free/UAN → omitir geolocalización.
- `find_exact_location()` - solo móviles: Geocoder estándar → CP probable (1 búsqueda) → señales de perfiles (Telegram alias numérico) → IP especulativa (etiquetada).
- Métodos devuelven nivel de precisión explícito (Baja / Baja-Media / Media-Baja) y advertencia legal.
