# Checks whether your Meta app is subscribed to the WhatsApp Business Account,
# and subscribes it if not.
#
# Ticking "messages" in the app dashboard is NOT enough on its own: the app must
# also be subscribed to the WABA, or Meta accepts the webhook and then delivers
# nothing. This is the most common reason inbound messages never arrive.
#
# Run:  powershell -ExecutionPolicy Bypass -File tools\check-waba-subscription.ps1

param(
    [string]$WabaId = "1639455334242993",
    [string]$AppId  = "1562370408465939"
)

Write-Host ""
Write-Host "Paste your Meta access token (starts with EAA), then press Enter." -ForegroundColor Cyan
Write-Host "Get a fresh one from: WhatsApp -> Step 1. Try it out -> Generate token"
Write-Host ""
$token = Read-Host "Token"

if (-not $token -or $token.Length -lt 50) {
    Write-Host "That does not look like an access token (too short)." -ForegroundColor Red
    exit 1
}

$headers = @{ Authorization = "Bearer $token" }
$url = "https://graph.facebook.com/v21.0/$WabaId/subscribed_apps"

Write-Host ""
Write-Host "1. Checking current subscription..." -ForegroundColor Cyan
try {
    $current = Invoke-RestMethod -Uri $url -Headers $headers -Method Get -ErrorAction Stop
} catch {
    Write-Host "Request failed:" -ForegroundColor Red
    Write-Host $_.ErrorDetails.Message
    Write-Host ""
    Write-Host "If this says code 190 / OAuthException, the token has expired." -ForegroundColor Yellow
    Write-Host "Generate a new one and run this again."
    exit 1
}

$apps = @($current.data)
Write-Host "   subscribed apps: $($apps.Count)"
$apps | ForEach-Object { Write-Host "   - $($_.whatsapp_business_api_data.name) (id $($_.whatsapp_business_api_data.id))" }

# A WABA is usually already subscribed to Meta's own "WA DevX Webhook Events 1P
# App", which is what powers the dashboard's test-webhook panel. That is NOT
# your app, and it is easy to mistake for a working subscription.
$mine = $apps | Where-Object { $_.whatsapp_business_api_data.id -eq $AppId }
if ($mine) {
    Write-Host ""
    Write-Host "Your app ($AppId) is already subscribed. This was not the problem." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "   Your app ($AppId) is NOT in that list - THIS IS THE BUG." -ForegroundColor Yellow
Write-Host "   Meta was delivering to its own app, never to your webhook." -ForegroundColor Yellow
Write-Host "2. Subscribing the app to the WABA..." -ForegroundColor Cyan
try {
    $result = Invoke-RestMethod -Uri $url -Headers $headers -Method Post -ErrorAction Stop
    Write-Host "   success: $($result.success)" -ForegroundColor Green
} catch {
    Write-Host "Subscribe failed:" -ForegroundColor Red
    Write-Host $_.ErrorDetails.Message
    exit 1
}

Write-Host ""
Write-Host "3. Verifying..." -ForegroundColor Cyan
$after = Invoke-RestMethod -Uri $url -Headers $headers -Method Get
@($after.data) | ForEach-Object { Write-Host "   - $($_.whatsapp_business_api_data.name) (id $($_.whatsapp_business_api_data.id))" }
if (@($after.data) | Where-Object { $_.whatsapp_business_api_data.id -eq $AppId }) {
    Write-Host "   your app is now subscribed" -ForegroundColor Green
} else {
    Write-Host "   your app still missing - the token may belong to a different app" -ForegroundColor Red
}
Write-Host ""
Write-Host "Done. Send a WhatsApp message to the test number now." -ForegroundColor Green
