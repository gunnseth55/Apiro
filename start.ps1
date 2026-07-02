# Apiro AI Detective — PowerShell Startup Script
# ================================================
# Run from the project root:  .\start.ps1
# Reads settings from .env, opens http://localhost:PORT automatically.

Write-Host ""
Write-Host " ==========================================" -ForegroundColor Cyan
Write-Host "  Apiro Clinical AI Detective" -ForegroundColor Cyan
Write-Host " ==========================================" -ForegroundColor Cyan
Write-Host ""

# Load .env file if it exists
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Write-Host " [*] Loading .env configuration..." -ForegroundColor DarkGray
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]*)=(.*)$") {
            $name  = $Matches[1].Trim()
            $value = $Matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

# Resolve active settings
$ollamaUrl = $env:OLLAMA_BASE_URL ?? "http://localhost:11434"
$model     = $env:PRIMARY_MODEL   ?? "mistral:latest"
$port      = $env:APP_PORT        ?? "8000"

Write-Host " [*] Ollama : $ollamaUrl" -ForegroundColor DarkGray
Write-Host " [*] Model  : $model" -ForegroundColor DarkGray
Write-Host " [*] Port   : $port" -ForegroundColor DarkGray
Write-Host ""

# Check if Ollama is running
try {
    $response = Invoke-WebRequest -Uri "$ollamaUrl/api/tags" -Method GET -TimeoutSec 5 -UseBasicParsing
    Write-Host " [+] Ollama is running." -ForegroundColor Green
    $models = ($response.Content | ConvertFrom-Json).models.name -join ", "
    Write-Host "     Available models: $models" -ForegroundColor DarkGray
} catch {
    Write-Host " [!] Ollama is not running at $ollamaUrl" -ForegroundColor Red
    Write-Host "     Start it with:   ollama serve" -ForegroundColor Yellow
    Write-Host "     Or use Docker:   docker compose up" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Activate virtual environment
Write-Host " [*] Activating virtual environment..." -ForegroundColor DarkGray
& "$PSScriptRoot\venv\Scripts\Activate.ps1"

Write-Host " [*] Starting Apiro on http://localhost:$port" -ForegroundColor Green
Write-Host " [*] Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

# Open browser after a short delay
Start-Job -ScriptBlock {
    param($p)
    Start-Sleep -Seconds 4
    Start-Process "http://localhost:$p"
} -ArgumentList $port | Out-Null

# Start uvicorn
uvicorn scripts.app:app --host 0.0.0.0 --port $port
