# Starts the whole stack: classifier, n8n, and the public tunnel.
#
#   .\start.ps1
#
# Secrets come from .env.local (gitignored) so nothing is typed twice and no
# token ends up in your shell history.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$envFile = Join-Path $root ".env.local"

# ---------------------------------------------------------------- config
if (-not (Test-Path $envFile)) {
    Write-Host ""
    Write-Host "No .env.local found." -ForegroundColor Yellow
    Write-Host "Copy .env.local.example to .env.local and fill in your values:"
    Write-Host "  copy .env.local.example .env.local" -ForegroundColor Cyan
    exit 1
}

$cfg = @{}
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $k, $v = $line.Split("=", 2)
        $cfg[$k.Trim()] = $v.Trim().Trim('"')
    }
}

foreach ($key in @("WA_PHONE_NUMBER_ID", "WA_TOKEN")) {
    if (-not $cfg[$key] -or $cfg[$key] -like "*your_*") {
        Write-Host "$key is not set in .env.local" -ForegroundColor Red
        exit 1
    }
}
if (-not $cfg["SERVICE_TOKEN"]) { $cfg["SERVICE_TOKEN"] = "dev-secret-123" }

$ngrok = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe"
if (-not (Test-Path $ngrok)) { $ngrok = "ngrok" }

function Test-Port($port) {
    [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}

function Wait-Port($port, $name, $seconds = 90) {
    for ($i = 0; $i -lt $seconds; $i++) {
        if (Test-Port $port) { Write-Host "  $name ready" -ForegroundColor Green; return $true }
        Start-Sleep -Seconds 1
    }
    Write-Host "  $name did not start within ${seconds}s" -ForegroundColor Red
    return $false
}

Write-Host ""
Write-Host "Starting COD confirmation stack" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------- classifier
if (Test-Port 8000) {
    Write-Host "1. classifier already running on 8000" -ForegroundColor DarkGray
} else {
    Write-Host "1. classifier..."
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "Set-Location '$root'; `$host.UI.RawUI.WindowTitle='classifier :8000'; uvicorn service:app --port 8000"
    )
    if (-not (Wait-Port 8000 "classifier")) { exit 1 }
}

# ---------------------------------------------------------------- n8n
if (Test-Port 5678) {
    Write-Host "2. n8n already running on 5678" -ForegroundColor DarkGray
} else {
    Write-Host "2. n8n..."
    # N8N_BLOCK_ENV_ACCESS_IN_NODE must be false or every node reading $env
    # fails with "access to env vars denied" (n8n 2.x default).
    $n8nCmd = @(
        "`$env:N8N_BLOCK_ENV_ACCESS_IN_NODE='false'",
        "`$env:WA_PHONE_NUMBER_ID='$($cfg['WA_PHONE_NUMBER_ID'])'",
        "`$env:WA_TOKEN='$($cfg['WA_TOKEN'])'",
        "`$env:SERVICE_TOKEN='$($cfg['SERVICE_TOKEN'])'",
        "`$host.UI.RawUI.WindowTitle='n8n :5678'",
        "n8n start"
    ) -join "; "
    Start-Process powershell -ArgumentList @("-NoExit", "-Command", $n8nCmd)
    if (-not (Wait-Port 5678 "n8n")) { exit 1 }
    Start-Sleep -Seconds 8   # give it a moment to register webhooks
}

# ---------------------------------------------------------------- tunnel
if (Test-Port 4040) {
    Write-Host "3. ngrok already running" -ForegroundColor DarkGray
} else {
    Write-Host "3. tunnel..."
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "`$host.UI.RawUI.WindowTitle='ngrok'; & '$ngrok' http 5678"
    )
    if (-not (Wait-Port 4040 "ngrok")) { exit 1 }
    Start-Sleep -Seconds 3
}

# ---------------------------------------------------------------- report
$publicUrl = $null
for ($i = 0; $i -lt 10; $i++) {
    try {
        $t = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 5
        $publicUrl = ($t.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1).public_url
        if ($publicUrl) { break }
    } catch { Start-Sleep -Seconds 2 }
}

Write-Host ""
Write-Host "Running:" -ForegroundColor Cyan
Write-Host "  dashboard   http://localhost:8000"
Write-Host "  n8n editor  http://localhost:5678"

if ($publicUrl) {
    $callback = "$publicUrl/webhook/whatsapp-reply"
    Write-Host "  callback    $callback"

    # ngrok's free plan hands out a new hostname on every restart, and Meta
    # keeps calling the old one until you update it. Say so loudly.
    $cache = Join-Path $root ".ngrok-url"
    $previous = if (Test-Path $cache) { (Get-Content $cache -Raw).Trim() } else { "" }
    Write-Host ""
    if ($previous -and $previous -ne $callback) {
        Write-Host "TUNNEL URL CHANGED since last run." -ForegroundColor Yellow
        Write-Host "Meta still points at:" -ForegroundColor Yellow
        Write-Host "  $previous" -ForegroundColor DarkGray
        Write-Host "Update the Callback URL here, or no messages will arrive:" -ForegroundColor Yellow
        Write-Host "  https://developers.facebook.com/apps/1562370408465939/use_cases/customize/wa-configurations-v2/?product_route=whatsapp-business" -ForegroundColor Cyan
    } elseif ($previous) {
        Write-Host "Tunnel URL unchanged - Meta is still pointing at the right place." -ForegroundColor Green
    } else {
        Write-Host "First run: set this as the Callback URL in Meta." -ForegroundColor Yellow
    }
    Set-Content -Path $cache -Value $callback -Encoding utf8
}

Write-Host ""
Write-Host "Stop everything with: .\stop.ps1" -ForegroundColor DarkGray
Write-Host ""
