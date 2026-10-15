$ErrorActionPreference = 'Stop'
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env'; Write-Host 'Created .env. Configure secrets before live calling.' }
docker compose up --build -d
Write-Host 'Voice Foundry: http://localhost:8000'
Write-Host 'Admin API key: see APP_API_KEY in .env'
