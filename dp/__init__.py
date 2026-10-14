# -*- coding: utf-8 -*-
"""
Donkey Punch Phone Recognizer - OSINT ético de números telefónicos.

Uso como biblioteca:
    from dp import PhoneNumberAnalyzer
    a = PhoneNumberAnalyzer("+34612345678", no_net=True)
    datos = a.analyze_all()

Uso como CLI:
    python dp.py            (lanzador de compatibilidad en la raíz)
    python -m dp            (equivalente)
    dp                      (tras `pip install -e .`)
"""

__version__ = "2.0.0"
__all__ = ["PhoneNumberAnalyzer", "__version__"]

# API pública mínima; cli NO se importa aquí para no tocar la consola
# al usar el paquete como biblioteca.
from .analyzer import PhoneNumberAnalyzer
