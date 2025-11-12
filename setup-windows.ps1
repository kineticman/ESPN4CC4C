# ESPN4CC4C Setup Script for Windows
# Run this in PowerShell to set up ESPN4CC4C with Docker

Write-Host "=== ESPN4CC4C Setup for Windows ===" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    $dockerVersion = docker version 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed"
    }
    Write-Host "✓ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker Desktop is not running or not installed" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Docker Desktop from: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
    Write-Host "Then start Docker Desktop and run this script again." -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Create required directories
Write-Host "Creating directories..." -ForegroundColor Yellow
$directories = @("data", "out", "logs")
foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "✓ Created $dir/" -ForegroundColor Green
    } else {
        Write-Host "✓ $dir/ already exists" -ForegroundColor Green
    }
}

Write-Host ""

# Detect IP address
Write-Host "Detecting network configuration..." -ForegroundColor Yellow
try {
    $ipAddress = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.PrefixOrigin -eq "Dhcp"
    } | Select-Object -First 1).IPAddress

    if ($ipAddress) {
        Write-Host "✓ Detected IP address: $ipAddress" -ForegroundColor Green
        Write-Host ""
        Write-Host "IMPORTANT: Update docker-compose.yml with your IP:" -ForegroundColor Yellow
        Write-Host "  Change: VC_RESOLVER_BASE_URL=http://YOUR_LAN_IP:8094" -ForegroundColor Cyan
        Write-Host "  To:     VC_RESOLVER_BASE_URL=http://${ipAddress}:8094" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Also update CC_HOST if using Chrome Capture:" -ForegroundColor Yellow
        Write-Host "  Change: CC_HOST=YOUR_LAN_IP" -ForegroundColor Cyan
        Write-Host "  To:     CC_HOST=${ipAddress}" -ForegroundColor Cyan
        Write-Host ""
    }
} catch {
    Write-Host "⚠ Could not auto-detect IP address" -ForegroundColor Yellow
    Write-Host "  Use ipconfig to find your IP and update docker-compose.yml manually" -ForegroundColor Yellow
    Write-Host ""
}

# Check if image should be pulled or built
Write-Host "=== Docker Image Setup ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Choose an option:" -ForegroundColor Yellow
Write-Host "  1) Pull pre-built image (recommended - faster)" -ForegroundColor White
Write-Host "  2) Build image locally (for development)" -ForegroundColor White
Write-Host ""
$choice = Read-Host "Enter choice (1 or 2)"

if ($choice -eq "1") {
    Write-Host ""
    Write-Host "Pulling pre-built image..." -ForegroundColor Yellow
    docker-compose pull
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Image pulled successfully" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to pull image" -ForegroundColor Red
        Write-Host "  The image might not be published yet. Try option 2 to build locally." -ForegroundColor Yellow
        exit 1
    }
} elseif ($choice -eq "2") {
    Write-Host ""
    Write-Host "Building image locally (this may take a few minutes)..." -ForegroundColor Yellow
    docker-compose build
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Image built successfully" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to build image" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Invalid choice. Run the script again." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== Setup Complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Edit docker-compose.yml - set VC_RESOLVER_BASE_URL to your IP" -ForegroundColor White
Write-Host "  2. If using Chrome Capture, set CC_HOST to your IP" -ForegroundColor White
Write-Host "  3. Run: docker-compose up -d" -ForegroundColor White
Write-Host "  4. Check logs: docker-compose logs -f" -ForegroundColor White
Write-Host "  5. Visit: http://localhost:8094/health" -ForegroundColor White
Write-Host ""
Write-Host "Endpoints:" -ForegroundColor Cyan
Write-Host "  Health:  http://localhost:8094/health" -ForegroundColor Yellow
if ($ipAddress) {
    Write-Host "  EPG:     http://${ipAddress}:8094/epg.xml" -ForegroundColor Yellow
    Write-Host "  M3U:     http://${ipAddress}:8094/playlist.m3u" -ForegroundColor Yellow
} else {
    Write-Host "  EPG:     http://YOUR_IP:8094/epg.xml" -ForegroundColor Yellow
    Write-Host "  M3U:     http://YOUR_IP:8094/playlist.m3u" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "For Channels DVR, use your LAN IP, not localhost!" -ForegroundColor Yellow
Write-Host ""
