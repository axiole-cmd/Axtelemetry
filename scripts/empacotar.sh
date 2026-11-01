#!/bin/bash
# Monta o pacote de instalação em dist/Axtel-vX.Y.zip
set -e
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
V=$(sed -n 's/^VERSAO = "\(.*\)"/\1/p' "$RAIZ/app/axtel_app/servidor.py")
SAIDA="$RAIZ/dist/Axtel"
rm -rf "$RAIZ/dist" && mkdir -p "$SAIDA/documentacao"

# Axtel.exe (compila se tiver Go; senão usa um já compilado)
if command -v go >/dev/null; then bash "$RAIZ/lancador/compilar.sh" >/dev/null; fi
[ -f "$RAIZ/lancador/Axtel.exe" ] || { echo "Falta o lancador/Axtel.exe (instale o Go 1.21+)"; exit 1; }
cp "$RAIZ/lancador/Axtel.exe" "$SAIDA/"

cp -r "$RAIZ/app/axtel.py" "$RAIZ/app/axtel_app" "$RAIZ/app/painel" "$SAIDA/"
find "$SAIDA" -name "__pycache__" -type d -prune -exec rm -rf {} +
cp "$RAIZ/instalador/"*.bat "$RAIZ/instalador/desinstalar.ps1" "$SAIDA/"
sed "s/__VERSAO__/$V/" "$RAIZ/instalador/instalar.ps1" > "$SAIDA/instalar.ps1"
cp "$RAIZ/docs/manual.html" "$SAIDA/documentacao/Manual do Axtel.html"

# PDF do manual, se o Playwright estiver instalado
python3 - "$RAIZ/docs/manual.html" "$SAIDA/documentacao/Manual do Axtel.pdf" <<'PY' || echo "(sem Playwright: o PDF do manual ficou de fora)"
import pathlib, sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    pg.goto(pathlib.Path(sys.argv[1]).resolve().as_uri())
    pg.pdf(path=sys.argv[2], format="A4", print_background=True, margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
    b.close()
PY

printf 'AXTEL %s - telemetria de sim racing\r\n=====================================\r\n\r\nINSTALAR: dois cliques em "Instalar Axtel".\r\n  Cria os atalhos e abre o Axtel. Se faltar o Python, ele oferece instalar.\r\nSEM INSTALAR: dois cliques em Axtel.exe.\r\nFECHAR: no painel, Configuracoes > Fechar o Axtel.\r\nDESINSTALAR: Menu Iniciar > Axtel > Desinstalar Axtel.\r\n\r\nJogos: AC EVO, Assetto Corsa, ACC, iRacing, Automobilista 2, F1 25 e Forza.\r\nComo ligar a telemetria de cada jogo: no painel, Configuracoes > Telemetria dos jogos.\r\nManual completo: documentacao\\Manual do Axtel.html\r\n' "$V" > "$SAIDA/LEIA-ME.txt"

cd "$RAIZ/dist"
zip -qr "Axtel-v$V.zip" Axtel
echo "dist/Axtel-v$V.zip ($(du -h "Axtel-v$V.zip" | cut -f1))"
