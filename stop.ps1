# Stops everything start.ps1 launched.
#
#   .\stop.ps1

$stopped = 0

# n8n and the classifier, by the port they listen on.
foreach ($p in 8000, 5678, 4040) {
    $pids = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        try {
            $name = (Get-Process -Id $procId -ErrorAction Stop).ProcessName
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Write-Host "stopped $name on port $p" -ForegroundColor DarkGray
            $stopped++
        } catch { }
    }
}

if ($stopped -eq 0) { Write-Host "nothing was running" -ForegroundColor DarkGray }
else { Write-Host "$stopped process(es) stopped" -ForegroundColor Green }
