#!/usr/bin/env bash
set -euo pipefail
cd '/Users/marceloschmitz/Documents/Projetos/Pocs/turing-smart-screen-python'
mkdir -p pixel_ops/output
exec "${PIXEL_OPS_PYTHON:-python3}" pixel_ops/main.py --plugin pokemon --forever >> pixel_ops/output/runtime.log 2>&1
