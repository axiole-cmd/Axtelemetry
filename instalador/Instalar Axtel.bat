@echo off
title Instalar Axtel
if not exist "%~dp0instalar.ps1" (
  echo.
  echo Extraia o zip antes de instalar: clique com o botao direito no arquivo .zip,
  echo escolha "Extrair tudo" e rode o "Instalar Axtel" de dentro da pasta extraida.
  echo.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
if errorlevel 1 (
  echo.
  echo Algo deu errado na instalacao. Tire um print desta janela e mande para o Leo.
  pause
)
