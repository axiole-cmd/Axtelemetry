#!/bin/bash
# Compila o Axtel.exe (lançador do Windows) a partir de qualquer sistema com Go 1.21+.
# O ícone vem do rsrc_windows_amd64.syso (gerado a partir do axtel.ico).
set -e
cd "$(dirname "$0")"
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags "-H windowsgui -s -w" -o Axtel.exe .
echo "Axtel.exe pronto ($(du -h Axtel.exe | cut -f1))"
