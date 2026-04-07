# Offline Package Preparation Script for AIS (Vessel Management System)
# This script creates a complete offline deployment package with Docker images, data, and deployment scripts

$ErrorActionPreference = "Stop"

# 1. Configuration
$projectRoot = $PSScriptRoot
$packageDir = Join-Path $projectRoot "AIS_offline_package"

Write-Host "=== Offline Package Preparation ===" -ForegroundColor Cyan
Write-Host "Project: $projectRoot" -ForegroundColor Yellow
Write-Host "Package: $packageDir" -ForegroundColor Yellow

# 2. Create package directory structure
Write-Host "`n=== Creating Directory Structure ===" -ForegroundColor Cyan

if (Test-Path $packageDir) {
    Write-Host "Removing existing package directory..." -ForegroundColor Yellow
    Remove-Item -Path $packageDir -Recurse -Force
}

New-Item -Path $packageDir -ItemType Directory | Out-Null
New-Item -Path "$packageDir\docker_images" -ItemType Directory | Out-Null
New-Item -Path "$packageDir\data" -ItemType Directory | Out-Null

Write-Host "Created: $packageDir\docker_images" -ForegroundColor Green
Write-Host "Created: $packageDir\data" -ForegroundColor Green

# 3. Save Docker images
Write-Host "`n=== Saving Docker Images ===" -ForegroundColor Cyan

$images = @(
    "postgres:15",
    "ais-vessel_api",
    "ais-vessel_frontend",
    "ais-vesselfinder_scraper"
)

foreach ($img in $images) {
    $sanitizedName = $img -replace "[:/]", "_"
    $tarFile = "$packageDir\docker_images\$sanitizedName.tar"
    
    Write-Host "Saving: $img -> $sanitizedName.tar" -ForegroundColor Yellow
    
    $filePath = "$packageDir\docker_images\$sanitizedName.tar"
    if (Test-Path $filePath) {
        Remove-Item -Path $filePath -Force
    }
    
    $result = docker save -o $filePath $img 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        $size = [math]::Round((Get-Item $filePath).Length / 1MB, 2)
        Write-Host "Saved: $sanitizedName.tar ($size MB)" -ForegroundColor Green
    } else {
        Write-Host "Error saving $img : $result" -ForegroundColor Red
        throw "Failed to save Docker image: $img"
    }
}

# 4. Copy data directories
Write-Host "`n=== Copying Data Directories ===" -ForegroundColor Cyan

$dataItems = @(
    @{Source = "data\postgres"; Dest = "$packageDir\data\postgres"},
    @{Source = "data\vessel_images"; Dest = "$packageDir\data\vessel_images"}
)

foreach ($item in $dataItems) {
    $src = Join-Path $projectRoot $item.Source
    $dst = $item.Dest
    
    if (Test-Path $src) {
        Write-Host "Copying: $($item.Source) ..." -ForegroundColor Yellow
        Copy-Item -Path $src -Destination $dst -Recurse -Force
        
        $fileCount = (Get-ChildItem -Path $dst -Recurse -File).Count
        Write-Host "Copied: $($item.Source) ($fileCount files)" -ForegroundColor Green
    } else {
        Write-Host "Warning: $($item.Source) not found, skipping" -ForegroundColor Yellow
    }
}

# 5. Copy essential files
Write-Host "`n=== Copying Essential Files ===" -ForegroundColor Cyan

$essentialFiles = @(
    "docker-compose.yml",
    "init.sql",
    ".env"
)

foreach ($file in $essentialFiles) {
    $srcFile = Join-Path $projectRoot $file
    $dstFile = Join-Path $packageDir $file
    
    if (Test-Path $srcFile) {
        Copy-Item -Path $srcFile -Destination $dstFile -Force
        Write-Host "Copied: $file" -ForegroundColor Green
    } else {
        Write-Host "Warning: $file not found" -ForegroundColor Yellow
    }
}

# 6. Create deployment scripts
Write-Host "`n=== Creating Deployment Scripts ===" -ForegroundColor Cyan

# 6.1 Create image loading script
$loadScript = @'
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
'@

$loadScript | Out-File -FilePath "$packageDir\1_load_images.ps1" -Encoding UTF8
Write-Host "Created: 1_load_images.ps1" -ForegroundColor Green

# 6.2 Create deployment guide
$guide = @"
# AIS Offline Deployment Guide

## Package Contents

- **docker_images/** - Docker image archives (.tar files)
  - postgres_15.tar (~140 MB)
  - ais-vessel_api.tar (~950 MB)
  - ais-vessel_frontend.tar (~260 MB)
  - ais-vesselfinder_scraper.tar (~1100 MB)

- **data/** - Application data
  - postgres/ - Database files
  - vessel_images/ - Vessel photo gallery

- **docker-compose.yml** - Docker Compose configuration
- **init.sql** - Database initialization script
- **.env** - Environment variables
- **1_load_images.ps1** - Image loading script

## Prerequisites on Target Machine

1. Docker Desktop installed
2. PowerShell 5.1 or higher
3. At least 10 GB free disk space

## Deployment Steps

### Step 1: Copy Package
Transfer the entire AIS_offline_package folder to the target machine

### Step 2: Load Docker Images
Open PowerShell in the package directory and run:
``````powershell
.\1_load_images.ps1
``````

This will load all Docker images from .tar files (~2.5 GB total)

### Step 3: Start Services
``````powershell
docker compose up -d
``````

This will start:
- PostgreSQL database (port 5432)
- Vessel API backend (port 8001)
- Vessel frontend (port 3000)
- VesselFinder scraper (background)

### Step 4: Verify Deployment
1. Check running containers:
   ``````powershell
   docker compose ps
   ``````

2. View logs:
   ``````powershell
   docker compose logs -f
   ``````

3. Open browser: http://localhost:3000

## Service Details

- **Frontend**: React + TypeScript + Vite (http://localhost:3000)
- **Backend API**: FastAPI (http://localhost:8001)
- **Database**: PostgreSQL 15 (port 5432)
- **Scraper**: Selenium + BeautifulSoup (background service)

## Data Persistence

All data is stored in:
- ./data/postgres/ - Database files
- ./data/vessel_images/ - Vessel photos

## Troubleshooting

### Images Not Loading
``````powershell
docker images  # Check if images loaded
.\1_load_images.ps1  # Re-run if needed
``````

### Services Not Starting
``````powershell
docker compose logs vessel_api  # Check API logs
docker compose logs db  # Check database logs
docker compose restart vessel_api  # Restart specific service
``````

### Port Conflicts
If ports are already in use, edit docker-compose.yml:
- Frontend: change "3000:80"
- API: change "8001:8001"
- Database: change "5432:5432"

### Database Issues
``````powershell
docker compose down -v  # Remove volumes
docker compose up -d  # Recreate
``````

## Stopping Services

``````powershell
docker compose down  # Stop all services
docker compose down -v  # Stop and remove volumes
``````

## Additional Information

For more details, see README.md in the original project repository.
"@

$guide | Out-File -FilePath "$packageDir\DEPLOY_GUIDE.md" -Encoding UTF8
Write-Host "Created: DEPLOY_GUIDE.md" -ForegroundColor Green

# 7. Package statistics
Write-Host "`n=== Package Statistics ===" -ForegroundColor Cyan

$totalSize = [math]::Round((Get-ChildItem -Path $packageDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB, 2)
$fileCount = (Get-ChildItem -Path $packageDir -Recurse -File).Count

Write-Host "Directory: $packageDir" -ForegroundColor Yellow
Write-Host "Total Size: $totalSize GB" -ForegroundColor Yellow
Write-Host "Total Files: $fileCount" -ForegroundColor Yellow

Write-Host "`n=== Package Structure ===" -ForegroundColor Cyan
Get-ChildItem -Path $packageDir -Recurse -Depth 1 | Select-Object FullName, Length

Write-Host "`n=== OFFLINE PACKAGE READY ===" -ForegroundColor Green
Write-Host "`nNext Steps:" -ForegroundColor Cyan
Write-Host "1. Copy '$packageDir' to target machine" -ForegroundColor White
Write-Host "2. On target machine run: .\1_load_images.ps1" -ForegroundColor White
Write-Host "3. Then run: docker compose up -d" -ForegroundColor White
Write-Host "4. Open browser: http://localhost:3000" -ForegroundColor White
Write-Host "`nSee details: $packageDir\DEPLOY_GUIDE.md" -ForegroundColor Yellow
