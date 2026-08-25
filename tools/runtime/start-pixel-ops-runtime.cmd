@echo off
cd /d "/Users/marceloschmitz/Documents/Projetos/Pocs/turing-smart-screen-python"
if not exist pixel_ops\output mkdir pixel_ops\output
set PYTHON_CMD=%PIXEL_OPS_PYTHON%
if "%PYTHON_CMD%"=="" set PYTHON_CMD=/Users/marceloschmitz/.asdf/installs/python/3.9.11/bin/python3
"%PYTHON_CMD%" pixel_ops/main.py --forever >> pixel_ops\output\runtime.log 2>&1
