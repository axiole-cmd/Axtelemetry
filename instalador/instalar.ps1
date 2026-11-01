# Instalador do Axtel: copia para a pasta do usuário, cria atalhos e abre o Axtel.
# O Axtel.exe instala o Python sozinho na primeira vez, se ele faltar.
$ErrorActionPreference = 'Stop'
$versao  = '__VERSAO__'
$origem  = $PSScriptRoot
$destino = Join-Path $env:LOCALAPPDATA 'Programs\Axtel'

function Titulo($t) { Write-Host ''; Write-Host "  $t" -ForegroundColor Yellow }
function Ok($t)     { Write-Host "  [ok] $t" -ForegroundColor Green }

Write-Host ''
Write-Host '  AXTEL' -ForegroundColor DarkYellow -NoNewline; Write-Host " $versao - instalação"
Write-Host '  Telemetria de sim racing'

# 1. Se o Axtel estiver aberto, fecha (a sessão em andamento fica salva)
try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:8501/api/fechar' -Method Post -Body '{}' -ContentType 'application/json' -TimeoutSec 3 | Out-Null
    Titulo 'Fechando o Axtel que estava aberto...'
    Start-Sleep -Seconds 3
} catch { }

# 2. Copia os arquivos (a pasta dados, com seu histórico, nunca é tocada)
Titulo "Copiando para $destino"
if ((Resolve-Path $origem).Path.TrimEnd('\') -ne $destino.TrimEnd('\')) {
    New-Item -ItemType Directory -Force -Path $destino | Out-Null
    robocopy $origem $destino /E /XD dados /XF 'Instalar Axtel.bat' 'instalar.ps1' /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "A cópia dos arquivos falhou (robocopy $LASTEXITCODE)." }
}
Get-ChildItem -Path $destino -Recurse -File | Unblock-File
Ok 'Arquivos copiados'

# 3. Atalhos na Área de Trabalho e no Menu Iniciar
$shell = New-Object -ComObject WScript.Shell
$exe   = Join-Path $destino 'Axtel.exe'
$icone = Join-Path $destino 'painel\axtel.ico'
$menu  = Join-Path ([Environment]::GetFolderPath('Programs')) 'Axtel'
New-Item -ItemType Directory -Force -Path $menu | Out-Null
foreach ($lnk in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Axtel.lnk'), (Join-Path $menu 'Axtel.lnk'))) {
    $s = $shell.CreateShortcut($lnk); $s.TargetPath = $exe; $s.WorkingDirectory = $destino
    $s.IconLocation = $icone; $s.Description = 'Axtel - telemetria de sim racing'; $s.Save()
}
$d = $shell.CreateShortcut((Join-Path $menu 'Desinstalar Axtel.lnk'))
$d.TargetPath = 'powershell.exe'
$d.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $destino 'desinstalar.ps1')`""
$d.WorkingDirectory = $destino; $d.IconLocation = $icone; $d.Save()
$m = $shell.CreateShortcut((Join-Path $menu 'Manual do Axtel.lnk'))
$m.TargetPath = (Join-Path $destino 'documentacao\Manual do Axtel.html'); $m.Save()
Ok 'Atalhos criados (Área de Trabalho e Menu Iniciar)'

# 4. Aparece em Configurações > Aplicativos, com opção de desinstalar
$chave = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Axtel'
New-Item -Path $chave -Force | Out-Null
$valores = @{
    DisplayName = 'Axtel'; DisplayVersion = $versao; Publisher = 'Leonardo Axiole'; DisplayIcon = $icone
    InstallLocation = $destino
    UninstallString = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $destino 'desinstalar.ps1')`""
}
foreach ($k in $valores.Keys) { New-ItemProperty -Path $chave -Name $k -Value $valores[$k] -PropertyType String -Force | Out-Null }
foreach ($k in @('NoModify', 'NoRepair')) { New-ItemProperty -Path $chave -Name $k -Value 1 -PropertyType DWord -Force | Out-Null }
Ok 'Registrado em Configurações > Aplicativos'

# 5. Abre o Axtel (na primeira vez ele oferece instalar o Python, se faltar)
Titulo 'Abrindo o Axtel...'
Start-Process -FilePath $exe -WorkingDirectory $destino
Write-Host ''
Write-Host '  Pronto! Da próxima vez, abra pelo atalho Axtel na Área de Trabalho.' -ForegroundColor Green
Write-Host '  Se o Windows perguntar sobre a rede, marque Redes privadas e clique em Permitir.'
Write-Host ''
Start-Sleep -Seconds 6
