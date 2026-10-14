#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dp.py - Lanzador de compatibilidad en la raíz del repositorio.

El código vive en el paquete dp/; este fichero solo conserva la invocación
histórica `python dp.py` (la forma moderna es `python -m dp`, o el comando
`dp` tras un `pip install -e .`).
"""

import sys

from dp.cli import main

if __name__ == "__main__":
    sys.exit(main())
