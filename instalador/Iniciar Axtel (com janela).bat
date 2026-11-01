@echo off
title Axtel
cd /d "%~dp0"
rem Abre o Axtel mostrando as mensagens (use se o Axtel.exe nao abrir).
py -3 -c "import sys" >nul 2>nul && (py -3 axtel.py & goto fim)
python -c "import sys" >nul 2>nul && (python axtel.py & goto fim)
echo Python nao encontrado. Abra o Axtel.exe uma vez: ele oferece instalar o Python.
:fim
pause
