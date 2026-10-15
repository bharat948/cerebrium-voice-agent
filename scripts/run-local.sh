#!/usr/bin/env bash
set -euo pipefail
if [ ! -f .env ]; then cp .env.example .env; echo 'Created .env. Configure secrets before live calling.'; fi
docker compose up --build -d
echo 'Voice Foundry: http://localhost:8000'
echo 'Admin API key: see APP_API_KEY in .env'
