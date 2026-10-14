# 🔍 Donkey Punch Phone Recognizer

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Plataforma](https://img.shields.io/badge/plataforma-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

**Navaja suiza OSINT para el análisis de números telefónicos**: identidad de la línea, operadora, reputación, detección VoIP/premium, presencia pública, cruce de correos y más — con honestidad técnica sobre lo que cada módulo puede y no puede demostrar.

> ⚖️ Herramienta de reconocimiento pasivo sobre **fuentes públicas**. No existe "ping GPS" ni consulta al operador: todo lo que hay aquí es heurística OSINT. Úsala con responsabilidad (ver [Uso ético](#-uso-ético-y-legal)).

---

## ✨ Características

- **20 módulos de análisis** orquestados en paralelo con presupuesto de búsquedas compartido
- **Motor de búsqueda web multi-motor** (DuckDuckGo HTML → DDG Lite → Bing → Mojeek) con degradación automática, throttle por host y caché de 24 h — sin claves de API
- **Verdad de terreno en tipos de línea**: detección VoIP / premium rate / toll-free vía `phonenumbers.number_type()`, no regex frágiles
- **Geolocalización móvil honesta**: solo móviles reales; reporta nivel de precisión y marca las IP especulativas como tales
- **Cruce de correos sin ruido**: filtra emails ajenos del SERP (solo acepta los vinculados al número) + verificación Gravatar
- **Resumen de riesgo consolidado** 0–10 con señales y recomendaciones
- **Exportes** TXT / JSON / CSV / HTML en `reports/`
- **Modo sin red** (`--no-net`) para análisis 100 % locales
- **Enriquecimiento opcional** con numverify / Twilio si defines claves en el entorno

## 📦 Instalación

```bash
git clone https://github.com/Cha0smagick/Donkey-punch.git
cd Donkey-punch

# (recomendado) entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows
# source .venv/bin/activate         # Linux/macOS

pip install -r requirements.txt
```

Instalación como comando global (opcional):

```bash
pip install -e .
dp --help
```

## 🚀 Uso

```bash
python dp.py                      # modo interactivo
python -m dp                      # equivalente
python dp.py -n +34612345678      # un número
python dp.py -n +34... -n +52...  # varios
python dp.py -b examples/lote_ejemplo.txt   # lote desde fichero
python dp.py -n +34612345678 --no-net       # solo módulos locales
```

### Opciones

| Flag | Descripción |
|------|-------------|
| `-n, --numero` | Número a analizar (internacional, ej. `+34612345678`). Repetible |
| `-b, --batch` | Fichero con un número por línea (`#` = comentario) |
| `--region ISO` | Región de fallback para números sin `+` (ej. `ES`) |
| `--no-net` | Solo módulos locales; ninguna petición de red |
| `--max-queries N` | Presupuesto de búsquedas web por número (default: 8) |
| `--workers N` | Hilos de análisis en paralelo (default: 4) |

### Uso como biblioteca

```python
from dp import PhoneNumberAnalyzer

analyzer = PhoneNumberAnalyzer("+34612345678", no_net=True)
datos = analyzer.analyze_all()
print(datos["Resumen_de_riesgo"]["calificación"])
```

## 📁 Estructura del proyecto

```
├── dp.py                  # Lanzador de compatibilidad (python dp.py)
├── dp/                    # Paquete principal
│   ├── __init__.py        # API pública (PhoneNumberAnalyzer)
│   ├── __main__.py        # Entrada para python -m dp
│   ├── cli.py             # CLI: argparse, display, batch, exportes
│   ├── analyzer.py        # Núcleo: 19 módulos + resumen de riesgo
│   ├── search.py          # Motor multi-motor con presupuesto y caché
│   ├── utils.py           # Logging, HTTP con throttle, paralelismo, exportes
│   └── data.py            # BD estática: carriers, prefijos, plantillas, APIs
├── examples/
│   └── lote_ejemplo.txt   # Ejemplo de fichero de lote
├── reports/               # Reportes generados (gitignored)
├── requirements.txt
├── pyproject.toml
├── CHANGELOG.md
├── LICENSE
└── .env.example           # Claves opcionales de enriquecimiento
```

## 🧩 Módulos de análisis

| # | Módulo | Qué hace (y qué no) |
|---|--------|---------------------|
| 1 | Información básica | Formatos, país, zona horaria, validez |
| 2 | Ubicación aproximada | Región/país por geocoder; precisión baja para móviles |
| 3 | Geolocalización móvil | Solo móviles: ciudad + CP probable + señales públicas; **no GPS** |
| 4 | Búsqueda web | Presencia pública multi-motor, presencias por host |
| 5 | Redes sociales | Enlaces de búsqueda manual + people-search (mayormente EE. UU.) |
| 6 | Mensajería | wa.me = solo enlace (responde 200 siempre); Telegram = alias numérico |
| 7 | Información de operadora | Metadatos del rango; la portabilidad puede desmentirlos |
| 8 | Reputación | Heurística de patrones sospechosos |
| 9 | Listas negras | Enlaces de consulta manual |
| 10 | Variaciones de formato | E.164, nacional, RFC3966, últimos dígitos... |
| 11 | Detección VoIP | Por tipo de línea + heurística de operadora |
| 12 | Número gratuito | Toll-free por tipo de línea + prefijos por país |
| 13 | Tarifa premium | Por tipo de línea + prefijos nacionales; advierte el coste |
| 14 | Bases de filtraciones | Enlaces correctos (HIBP `/phone/`) + menciones web |
| 15 | Cruce de correos | Cosecha **filtrada** por vinculación + Gravatar (`?d=404`) |
| 16 | Patrones de email | Hipótesis de direcciones probables |
| 17 | Google Dorks | 3 ejecutados vía motor propio + enlaces manuales a Google |
| 18 | Huella de operadora | Prefijos y tipo de red (orientativo por portabilidad) |
| 19 | Enriquecimiento API | numverify / Twilio **solo con claves en el entorno** |
| 20 | Resumen de riesgo | Puntuación 0–10, señales, recomendaciones |

## 🔑 Variables de entorno (opcionales)

```bash
cp .env.example .env    # y rellena lo que tengas; sin claves, el módulo se omite
```

| Variable | Servicio |
|----------|----------|
| `DP_NUMVERIFY_KEY` | [numverify](https://numverify.com/) — lookup enriquecido |
| `DP_TWILIO_SID` + `DP_TWILIO_TOKEN` | [Twilio Lookup](https://www.twilio.com/docs/lookup) |

## 📊 Salidas

- `reports/reporte_{numero}_{timestamp}.txt | .json | .html` — reporte individual
- `reports/batch_report_{timestamp}.json` + `reporte_lote_{timestamp}.csv` — reportes de lote
- `dp_analysis.log` — log detallado de todas las fases
- `dp_cache/search/` — caché de búsquedas (TTL 24 h) para re-análisis rápidos

## ⚖️ Uso ético y legal

Esta herramienta **solo consulta fuentes públicas** y está pensada para:

- Investigación de seguridad y OSINT defensivo
- Verificación de números sospechosos (fraude, spam, premium rate)
- CTFs y laboratorios de reconocimiento

**No uses esta herramienta** para acoso, doxxing, suplantación o cualquier fin ilegal. La titularidad de una línea **no puede demostrarse** con OSINT: ningún módulo de esta herramienta afirma titularidad. Eres responsable del uso que hagas de los resultados y de cumplir la legislación de tu jurisdicción (protección de datos, RGPD, etc.).

## 📄 Licencia

[MIT](LICENSE) — © 2026 Cha0smagick

## 🔄 Changelog

Ver [CHANGELOG.md](CHANGELOG.md).
