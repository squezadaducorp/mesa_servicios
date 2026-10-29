# Publica la Mesa de Servicios en internet con Cloudflare Tunnel (Windows, PowerShell).
# Guía: docs\11-publicar-en-internet.md
#   .\deploy\publicar.ps1 -Modo prueba     dirección temporal *.trycloudflare.com para mostrarla hoy
#   .\deploy\publicar.ps1 -Modo publico    dirección fija (CLOUDFLARE_TUNNEL_TOKEN en .env)
#   .\deploy\publicar.ps1 -Modo detener    deja de publicar; la Mesa sigue funcionando en la red local
# Si Windows no permite ejecutar scripts:  powershell -ExecutionPolicy Bypass -File .\deploy\publicar.ps1 -Modo prueba
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("prueba", "publico", "detener")]
    [string]$Modo
)

Set-Location (Split-Path -Parent $PSScriptRoot)
$compose = @("compose", "-f", "docker-compose.yml", "-f", "docker-compose.publico.yml")

function Salir([string]$mensaje) {
    Write-Host $mensaje -ForegroundColor Red
    exit 1
}

# Lee el .env (el mismo que usa Docker Compose)
if (-not (Test-Path ".env")) { Salir "No existe el archivo .env en $(Get-Location)." }
$cfg = @{}
foreach ($linea in Get-Content ".env" -Encoding UTF8) {
    if ($linea -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        $cfg[$Matches[1]] = ($Matches[2] -replace '\s+#.*$', '').Trim().Trim('"')
    }
}

if ($Modo -eq "detener") {
    & docker @compose --profile prueba --profile publico rm -s -f tunel tunel-prueba
    Write-Host "La Mesa ya no está publicada en internet. Sigue disponible en la red local." -ForegroundColor Green
    exit 0
}

if ($Modo -eq "publico") {
    if (-not $cfg["CLOUDFLARE_TUNNEL_TOKEN"]) { Salir "Falta CLOUDFLARE_TUNNEL_TOKEN en .env (paso 3 de la guía)." }
    if (-not ("" + $cfg["APP_URL"]).StartsWith("https://")) { Salir "APP_URL en .env debe ser la dirección pública con https://, por ejemplo https://mesa.aducorp.com.ec" }
}

# 1. Ninguna cuenta con la contraseña inicial publicada en el README puede quedar abierta a internet
Write-Host "Revisando contraseñas iniciales..." -ForegroundColor Cyan
$base = if ($cfg["DB_NAME"]) { $cfg["DB_NAME"] } else { "AducorpMesaServicios" }
Get-Content "deploy\cloudflare\antes-de-publicar.sql" -Raw -Encoding UTF8 |
    & docker compose exec -T -e "SQLCMDPASSWORD=$($cfg['SA_PASSWORD'])" sqlserver `
        /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -I -b -W -d $base
if ($LASTEXITCODE -ne 0) { Salir "No se publicó. Corrija lo indicado arriba y vuelva a ejecutar." }

# 2. Levanta el túnel (Nginx se reinicia unos segundos para tomar la IP real de los usuarios)
Write-Host "Levantando el túnel..." -ForegroundColor Cyan
& docker @compose --profile $Modo up -d
if ($LASTEXITCODE -ne 0) { Salir "Docker no pudo levantar el túnel." }

if ($Modo -eq "publico") {
    Write-Host "Listo. La Mesa queda publicada en $($cfg['APP_URL']) (puede tardar un minuto)." -ForegroundColor Green
    exit 0
}

# 3. Modo prueba: busca la dirección temporal en los registros del túnel
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    $registro = (& docker @compose --profile prueba logs tunel-prueba 2>&1) -join "`n"
    if ($registro -match 'https://[a-z0-9-]+\.trycloudflare\.com') {
        Write-Host ""
        Write-Host "Dirección temporal de la Mesa: $($Matches[0])" -ForegroundColor Green
        Write-Host "Cambia cada vez que se reinicia el túnel o el PC. Para dejarla fija siga el paso 3 de la guía."
        exit 0
    }
}
Salir "El túnel no entregó una dirección. Revise: docker compose -f docker-compose.yml -f docker-compose.publico.yml logs tunel-prueba"
