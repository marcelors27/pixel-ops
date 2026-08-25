#!/usr/bin/env bash
set -euo pipefail
cd '/Users/marceloschmitz/Documents/Projetos/Pocs/turing-smart-screen-python'
mkdir -p pixel_ops/output
echo $$ > pixel_ops/output/runtime.pid
exec "${PIXEL_OPS_PYTHON:-/Users/marceloschmitz/.asdf/installs/python/3.9.11/bin/python3}" pixel_ops/main.py --forever >> pixel_ops/output/runtime.log 2>&1
