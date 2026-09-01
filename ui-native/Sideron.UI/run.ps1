$ErrorActionPreference = "Stop"

$Project = Join-Path $PSScriptRoot "Sideron.UI.csproj"
$SideronRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$MainCore = [System.IO.Path]::GetFullPath((Join-Path $SideronRoot "main_core.py"))
$DevPython = Join-Path $SideronRoot ".venv\Scripts\python.exe"
$ProjectConfig = Join-Path $SideronRoot "config\sideron.json"
$RuntimeConfig = Join-Path $env:LOCALAPPDATA "SIDERON\config\sideron.json"

$SideronApiBaseUrl = "https://atlasbot.freeboxos.fr/sideron-api/"
$SideronAccessPath = Join-Path $env:LOCALAPPDATA "SIDERON\auth\access.bin"

function Ensure-SideronDevApiAccess
{
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    if (Test-Path $SideronAccessPath) {
        Write-Host "Accès OpenAI SIDERON déjà configuré pour cet utilisateur." -ForegroundColor DarkGray
        return
    }

    Write-Host "Accès SIDERON absent : provisionnement du profil de développement..." -ForegroundColor Cyan
    Add-Type -AssemblyName System.Security

    $RegisterUri = $SideronApiBaseUrl.TrimEnd('/') + "/v1/install/register"
    $Payload = @{
        install_id = [Guid]::NewGuid().ToString("D")
        version = $Version
    } | ConvertTo-Json -Compress

    $Response = $null
    $LastError = $null

    for ($Attempt = 1; $Attempt -le 3; $Attempt++) {
        try {
            $Response = Invoke-RestMethod `
                -Uri $RegisterUri `
                -Method Post `
                -ContentType "application/json; charset=utf-8" `
                -Body $Payload `
                -TimeoutSec 20 `
                -ErrorAction Stop

            $Token = [string]$Response.access_token
            if ([string]::IsNullOrWhiteSpace($Token) -or -not $Token.StartsWith("sideron_")) {
                throw "Le relais SIDERON a renvoyé une réponse de provisionnement invalide."
            }

            break
        }
        catch {
            $LastError = $_.Exception.Message
            $Response = $null

            if ($Attempt -lt 3) {
                Start-Sleep -Seconds 2
            }
        }
    }

    if ($null -eq $Response) {
        throw "Impossible de provisionner l'accès SIDERON pour le développement : $LastError"
    }

    $AccessBytes = [Text.Encoding]::ASCII.GetBytes([string]$Response.access_token)
    try {
        $Protected = [Security.Cryptography.ProtectedData]::Protect(
            $AccessBytes,
            $null,
            [Security.Cryptography.DataProtectionScope]::CurrentUser
        )

        $AccessDirectory = Split-Path -Path $SideronAccessPath -Parent
        [IO.Directory]::CreateDirectory($AccessDirectory) | Out-Null
        [IO.File]::WriteAllBytes($SideronAccessPath, $Protected)
    }
    finally {
        if ($null -ne $AccessBytes) {
            [Array]::Clear($AccessBytes, 0, $AccessBytes.Length)
        }
    }

    Write-Host "Accès SIDERON de développement configuré." -ForegroundColor Green
}

if (-not (Test-Path $Project)) {
    throw "Projet WinUI introuvable : $Project"
}

if (-not (Test-Path $MainCore)) {
    throw "Core Python de développement introuvable : $MainCore"
}

if (-not (Test-Path $DevPython)) {
    throw "Environnement Python de développement introuvable : $DevPython"
}

# Un test de développement ne doit jamais réutiliser le Core installé ou un
# SIDERON.Core.exe potentiellement ancien présent dans l'arborescence projet.
Stop-Service -Name "SIDERONService" -Force -ErrorAction SilentlyContinue

Get-Process -Name "SIDERON.Core", "SIDERON.Service" -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue

# Arrête uniquement un ancien Core Python appartenant à CE projet.
Get-CimInstance Win32_Process `
    -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" `
    -ErrorAction SilentlyContinue |
    Where-Object {
        $CommandLine = [string]$_.CommandLine
        $CommandLine -and $CommandLine.IndexOf(
            $MainCore,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

# Le Core et l'UI doivent utiliser exactement la même configuration runtime.
# Si elle n'existe pas encore sur un poste de développement, initialise-la à
# partir de la configuration du projet sans écraser une configuration existante.
if (-not (Test-Path $RuntimeConfig)) {
    if (-not (Test-Path $ProjectConfig)) {
        throw "Configuration SIDERON introuvable : $ProjectConfig"
    }

    $RuntimeConfigDirectory = Split-Path -Parent $RuntimeConfig
    New-Item -ItemType Directory -Path $RuntimeConfigDirectory -Force | Out-Null
    Copy-Item -Path $ProjectConfig -Destination $RuntimeConfig -Force:$false
}

if (-not (Test-Path $ProjectConfig)) {
    throw "Configuration SIDERON introuvable : $ProjectConfig"
}

try {
    $ProjectConfigData = Get-Content -Path $ProjectConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    $DevVersion = [string]$ProjectConfigData.sideron.version
}
catch {
    throw "Impossible de lire la version SIDERON dans $ProjectConfig : $($_.Exception.Message)"
}

if ([string]::IsNullOrWhiteSpace($DevVersion)) {
    throw "Version SIDERON absente de la configuration projet : $ProjectConfig"
}

Ensure-SideronDevApiAccess -Version $DevVersion

$previousConfigPath = $env:SIDERON_CONFIG_PATH
$env:SIDERON_CONFIG_PATH = $RuntimeConfig

$coreProcess = $null

try {
    Write-Host "Démarrage du Core Python de développement..." -ForegroundColor Cyan

    $coreProcess = Start-Process `
        -FilePath $DevPython `
        -ArgumentList @($MainCore) `
        -WorkingDirectory $SideronRoot `
        -PassThru `
        -WindowStyle Hidden

    # L'IPC Core -> UI sait se reconnecter. Le Core est volontairement lancé
    # avant l'UI afin que CoreProcessService détecte sa connexion pendant sa
    # fenêtre de grâce et n'essaie pas de démarrer un SIDERON.Core.exe ancien.
    Start-Sleep -Milliseconds 350

    Write-Host "Démarrage de Sideron.UI en Debug..." -ForegroundColor Cyan

    dotnet run `
        --project $Project `
        -c Debug `
        -p:Platform=x64
}
finally {
    if ($coreProcess -and -not $coreProcess.HasExited) {
        Write-Host "Arrêt du Core Python de développement..." -ForegroundColor DarkGray
        Stop-Process -Id $coreProcess.Id -Force -ErrorAction SilentlyContinue
    }

    if ($null -eq $previousConfigPath) {
        Remove-Item Env:SIDERON_CONFIG_PATH -ErrorAction SilentlyContinue
    }
    else {
        $env:SIDERON_CONFIG_PATH = $previousConfigPath
    }
}
