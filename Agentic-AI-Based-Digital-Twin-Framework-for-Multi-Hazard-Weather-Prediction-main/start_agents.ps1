# ============================================================
# start_agents.ps1
# ============================================================
# Starts all agent microservices in separate PowerShell windows
# for local development WITHOUT Docker.
#
# Prerequisites:
#   pip install -r <agent>/requirements.txt  (per agent)
#   Python 3.10+
#
# Usage:
#   .\start_agents.ps1
#
# Each agent opens in its own terminal window.
# Close any window to stop that agent.
# ============================================================

$Root = $PSScriptRoot

function Start-Agent {
    param(
        [string]$Name,
        [string]$Module,
        [int]$Port,
        [string]$WorkDir,
        [hashtable]$Env = @{}
    )

    $envBlock = ""
    foreach ($kv in $Env.GetEnumerator()) {
        $envBlock += "`$env:$($kv.Key) = '$($kv.Value)'; "
    }

    $cmd = "$envBlock cd '$WorkDir'; uvicorn $Module`:app --host 0.0.0.0 --port $Port --reload"
    
    Write-Host "Starting $Name on port $Port..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd -WindowStyle Normal
}

# ── Agent 2: Weather Analysis Agent (Port 8001) ────────────────────────────────
Start-Agent -Name "Weather Analysis Agent" `
    -Module "agents.weather_analysis.main" `
    -Port 8001 `
    -WorkDir "$Root"

Start-Sleep -Seconds 2

# ── Agent 3: Prediction Agent (Port 8002) ─────────────────────────────────────
Start-Agent -Name "Prediction Agent" `
    -Module "agents.prediction.main" `
    -Port 8002 `
    -WorkDir "$Root"

Start-Sleep -Seconds 2

# ── Agent 4: Alert & Risk Agent (Port 8003) ───────────────────────────────────
Start-Agent -Name "Alert & Risk Agent" `
    -Module "agents.alert_risk.main" `
    -Port 8003 `
    -WorkDir "$Root" `
    -Env @{
        PREDICTION_AGENT_URL = "http://localhost:8002"
        WEATHER_AGENT_URL    = "http://localhost:8001"
    }

Start-Sleep -Seconds 2

# ── Agent 5: Digital Twin Agent (Port 8004) ───────────────────────────────────
Start-Agent -Name "Digital Twin Agent" `
    -Module "agents.digital_twin.main" `
    -Port 8004 `
    -WorkDir "$Root"

Start-Sleep -Seconds 2

# ── Agent 6: Report Agent (Port 8006) ─────────────────────────────────────────
Start-Agent -Name "Report Agent" `
    -Module "agents.report.main" `
    -Port 8006 `
    -WorkDir "$Root" `
    -Env @{
        WEATHER_AGENT_URL     = "http://localhost:8001"
        PREDICTION_AGENT_URL  = "http://localhost:8002"
        ALERT_AGENT_URL       = "http://localhost:8003"
        DIGITAL_TWIN_AGENT_URL = "http://localhost:8004"
    }

Start-Sleep -Seconds 2

# ── Agent 1: Orchestrator Agent (Port 8005) ───────────────────────────────────
Start-Agent -Name "Orchestrator Agent" `
    -Module "agents.orchestrator.main" `
    -Port 8005 `
    -WorkDir "$Root" `
    -Env @{
        WEATHER_AGENT_URL     = "http://localhost:8001"
        PREDICTION_AGENT_URL  = "http://localhost:8002"
        ALERT_AGENT_URL       = "http://localhost:8003"
        DIGITAL_TWIN_AGENT_URL = "http://localhost:8004"
        REPORT_AGENT_URL      = "http://localhost:8006"
    }

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  All agents started!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Agent URLs:" -ForegroundColor Yellow
Write-Host "    Orchestrator  : http://localhost:8005/docs" -ForegroundColor White
Write-Host "    Weather       : http://localhost:8001/docs" -ForegroundColor White
Write-Host "    Prediction    : http://localhost:8002/docs" -ForegroundColor White
Write-Host "    Alert & Risk  : http://localhost:8003/docs" -ForegroundColor White
Write-Host "    Digital Twin  : http://localhost:8004/docs" -ForegroundColor White
Write-Host "    Report        : http://localhost:8006/docs" -ForegroundColor White
Write-Host ""
Write-Host "  Backend proxy (POST /api/v1/agents/orchestrator/query)" -ForegroundColor Yellow
Write-Host ""
