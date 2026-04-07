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
```powershell
.\1_load_images.ps1
```

This will load all Docker images from .tar files (~2.5 GB total)

### Step 3: Start Services
```powershell
docker compose up -d
```

This will start:
- PostgreSQL database (port 5432)
- Vessel API backend (port 8001)
- Vessel frontend (port 3000)
- VesselFinder scraper (background)

### Step 4: Verify Deployment
1. Check running containers:
   ```powershell
   docker compose ps
   ```

2. View logs:
   ```powershell
   docker compose logs -f
   ```

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
```powershell
docker images  # Check if images loaded
.\1_load_images.ps1  # Re-run if needed
```

### Services Not Starting
```powershell
docker compose logs vessel_api  # Check API logs
docker compose logs db  # Check database logs
docker compose restart vessel_api  # Restart specific service
```

### Port Conflicts
If ports are already in use, edit docker-compose.yml:
- Frontend: change "3000:80"
- API: change "8001:8001"
- Database: change "5432:5432"

### Database Issues
```powershell
docker compose down -v  # Remove volumes
docker compose up -d  # Recreate
```

## Stopping Services

```powershell
docker compose down  # Stop all services
docker compose down -v  # Stop and remove volumes
```

## Additional Information

For more details, see README.md in the original project repository.
