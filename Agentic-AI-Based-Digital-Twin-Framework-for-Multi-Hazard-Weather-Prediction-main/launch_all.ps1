# ============================================================
# launch_all.ps1  –  Start all agent services as background jobs
# ============================================================
param([switch]$Stop)

$Root = $PSScriptRoot

$agents = @(
    @{ Name="Weather Analysis"; Dir="weather_analysis_agent"; Module="agents.weather_analysis.main:app"; Port=8001; Env=@{} },
    @{ Name="Prediction";       Dir="prediction_agent";       Module="agents.prediction.main:app";       Port=8002; Env=@{} },
    @{ Name="Alert & Risk";     Dir="alert_risk_agent";       Module="agents.alert_risk.main:app";       Port=8003; Env=@{
        PREDICTION_AGENT_URL="http://localhost:8002"
        WEATHER_AGENT_URL="http://localhost:8001"
    }},
    @{ Name="Digital Twin";     Dir="digital_twin_agent";     Module="agents.digital_twin.main:app";     Port=8004; Env=@{} },
    @{ Name="Report";           Dir="report_agent";           Module="agents.report.main:app";           Port=8006; Env=@{
        WEATHER_AGENT_URL="http://localhost:8001"
        PREDICTION_AGENT_URL="http://localhost:8002"
        ALERT_AGENT_URL="http://localhost:8003"
        DIGITAL_TWIN_AGENT_URL="http://localhost:8004"
    }},
    @{ Name="Orchestrator";     Dir="orchestrator_agent";     Module="agents.orchestrator.main:app";     Port=8005; Env=@{
        WEATHER_AGENT_URL="http://localhost:8001"
        PREDICTION_AGENT_URL="http://localhost:8002"
        ALERT_AGENT_URL="http://localhost:8003"
        DIGITAL_TWIN_AGENT_URL="http://localhost:8004"
        REPORT_AGENT_URL="http://localhost:8006"
        GROQ_API_KEY=$env:GROQ_API_KEY
        GROQ_MODEL="openai/gpt-oss-120b"
    }}
)

if ($Stop) {
    Write-Host "Stopping all agent jobs..." -ForegroundColor Yellow
    Get-Job -Name "Agent_*" | Stop-Job | Remove-Job
    Write-Host "All agent jobs stopped." -ForegroundColor Red
    exit
}

# Kill anything already on these ports
foreach ($a in $agents) {
    $proc = Get-NetTCPConnection -LocalPort $a.Port -State Listen -ErrorAction SilentlyContinue
    if ($proc) {
        $pid_ = $proc.OwningProcess | Select-Object -First 1
        Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Launching Weather Twin Agent Services" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$jobs = @()
foreach ($a in $agents) {
    $workDir = Join-Path $Root $a.Dir
    $module  = $a.Module
    $port    = $a.Port
    $envVars = $a.Env

    $job = Start-Job -Name "Agent_$($a.Name.Replace(' ','_'))" -ScriptBlock {
        param($dir, $mod, $p, $ev)
        Set-Location $dir
        foreach ($kv in $ev.GetEnumerator()) {
            [System.Environment]::SetEnvironmentVariable($kv.Key, $kv.Value, 'Process')
        }
        & uvicorn $mod --host 0.0.0.0 --port $p 2>&1
    } -ArgumentList $workDir, $module, $port, $envVars

    $jobs += $job
    Write-Host "  Started $($a.Name) (port $port) [Job: $($job.Id)]" -ForegroundColor Green
    Start-Sleep -Milliseconds 800
}

Write-Host ""
Write-Host "Waiting 12s for all services to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 12

Write-Host ""
Write-Host "Health Check:" -ForegroundColor Cyan
$allOk = $true
foreach ($a in $agents) {
    $port = $a.Port
    try {
        $r = (Invoke-WebRequest -Uri "http://localhost:$port/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop).StatusCode
        Write-Host "  [OK]  $($a.Name) :$port  -> HTTP $r" -ForegroundColor Green
    } catch {
        Write-Host "  [ERR] $($a.Name) :$port  -> $($_.Exception.Message)" -ForegroundColor Red
        $allOk = $false
    }
}

Write-Host ""
if ($allOk) {
    Write-Host "All agents healthy! System ready." -ForegroundColor Green
} else {
    Write-Host "Some agents may still be starting. Check with: Get-Job -Name 'Agent_*' | Receive-Job" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Orchestrator API  : http://localhost:8005/docs" -ForegroundColor White
Write-Host "  Weather Agent     : http://localhost:8001/docs" -ForegroundColor White
Write-Host "  Prediction Agent  : http://localhost:8002/docs" -ForegroundColor White
Write-Host "  Alert & Risk      : http://localhost:8003/docs" -ForegroundColor White
Write-Host "  Digital Twin      : http://localhost:8004/docs" -ForegroundColor White
Write-Host "  Report Agent      : http://localhost:8006/docs" -ForegroundColor White
Write-Host ""
Write-Host "To stop all: .\launch_all.ps1 -Stop" -ForegroundColor Gray
Write-Host ""
