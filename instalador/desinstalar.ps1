# Desinstalador do Axtel.
$ErrorActionPreference = 'Continue'
$pasta = Join-Path $env:LOCALAPPDATA 'Programs\Axtel'
Write-Host ''
Write-Host '  Desinstalar o Axtel' -ForegroundColor Yellow
try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:8501/api/fechar' -Method Post -Body '{}' -ContentType 'application/json' -TimeoutSec 3 | Out-Null
    Start-Sleep -Seconds 3
} catch { }

$resp = Read-Host '  Apagar também o seu histórico de corridas (pasta dados)? Digite S para apagar ou Enter para guardar'
$apagarDados = $resp -match '^[sS]'

Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Axtel.lnk') -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'Axtel') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Axtel' -Recurse -Force -ErrorAction SilentlyContinue
$inicio = Join-Path ([Environment]::GetFolderPath('Startup')) 'Axtel.bat'
Remove-Item $inicio -ErrorAction SilentlyContinue

if (Test-Path $pasta) {
    Get-ChildItem -Path $pasta -Force | Where-Object { $apagarDados -or $_.Name -ne 'dados' } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    if ($apagarDados) { Remove-Item $pasta -Recurse -Force -ErrorAction SilentlyContinue }
}
Write-Host ''
if ($apagarDados) {
    Write-Host '  O Axtel foi removido, junto com o histórico.' -ForegroundColor Green
} else {
    Write-Host '  O Axtel foi removido. Seu histórico ficou guardado em:' -ForegroundColor Green
    Write-Host "  $pasta\dados"
    Write-Host '  Se instalar de novo, ele volta a aparecer.'
}
Write-Host ''
Read-Host '  Aperte Enter para fechar'
