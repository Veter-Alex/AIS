# Load Docker Images Script
# Run this script on the target machine to load all Docker images

$ErrorActionPreference = "Stop"

Write-Host "=== Loading Docker Images ===" -ForegroundColor Cyan

$imageFiles = Get-ChildItem -Path ".\docker_images\*.tar"

foreach ($file in $imageFiles) {
    Write-Host "Loading: $($file.Name) ..." -ForegroundColor Yellow
    docker load -i $file.FullName
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Loaded: $($file.Name)" -ForegroundColor Green
    } else {
        Write-Host "Error loading: $($file.Name)" -ForegroundColor Red
    }
}

Write-Host "`n=== Loaded Images ===" -ForegroundColor Cyan
docker images

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. docker compose up -d" -ForegroundColor White
Write-Host "2. Open browser: http://localhost:3000" -ForegroundColor White
