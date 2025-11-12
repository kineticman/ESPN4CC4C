#!/bin/bash
#
# ESPN4CC4C Setup Script for Linux/Mac
# Run this to set up ESPN4CC4C with Docker
#

set -e

echo "=== ESPN4CC4C Setup for Linux/Mac ==="
echo ""

# Check if Docker is running
echo "Checking Docker..."
if ! docker version &> /dev/null; then
    echo "✗ Docker is not running or not installed"
    echo ""
    echo "Please install Docker:"
    echo "  Linux: https://docs.docker.com/engine/install/"
    echo "  Mac: https://www.docker.com/products/docker-desktop/"
    exit 1
fi
echo "✓ Docker is running"
echo ""

# Create required directories
echo "Creating directories..."
for dir in data out logs; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "✓ Created $dir/"
    else
        echo "✓ $dir/ already exists"
    fi
done
echo ""

# Detect IP address
echo "Detecting network configuration..."
if command -v hostname &> /dev/null; then
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [ -n "$IP" ]; then
        echo "✓ Detected IP address: $IP"
        echo ""
        echo "IMPORTANT: Update docker-compose.yml with your IP:"
        echo "  Change: VC_RESOLVER_BASE_URL=http://YOUR_LAN_IP:8094"
        echo "  To:     VC_RESOLVER_BASE_URL=http://${IP}:8094"
        echo ""
        echo "  Also update CC_HOST if using Chrome Capture:"
        echo "  Change: CC_HOST=YOUR_LAN_IP"
        echo "  To:     CC_HOST=${IP}"
        echo ""
    fi
fi

# Check if image should be pulled or built
echo "=== Docker Image Setup ==="
echo ""
echo "Choose an option:"
echo "  1) Pull pre-built image (recommended - faster)"
echo "  2) Build image locally (for development)"
echo ""
read -p "Enter choice (1 or 2): " choice

if [ "$choice" = "1" ]; then
    echo ""
    echo "Pulling pre-built image..."
    if docker-compose pull; then
        echo "✓ Image pulled successfully"
    else
        echo "✗ Failed to pull image"
        echo "  The image might not be published yet. Try option 2 to build locally."
        exit 1
    fi
elif [ "$choice" = "2" ]; then
    echo ""
    echo "Building image locally (this may take a few minutes)..."
    if docker-compose build; then
        echo "✓ Image built successfully"
    else
        echo "✗ Failed to build image"
        exit 1
    fi
else
    echo "Invalid choice. Run the script again."
    exit 1
fi

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit docker-compose.yml - set VC_RESOLVER_BASE_URL to your IP"
echo "  2. If using Chrome Capture, set CC_HOST to your IP"
echo "  3. Run: docker-compose up -d"
echo "  4. Check logs: docker-compose logs -f"
echo "  5. Visit: http://localhost:8094/health"
echo ""
echo "Endpoints:"
echo "  Health:  http://localhost:8094/health"
echo "  EPG:     http://${IP:-localhost}:8094/epg.xml"
echo "  M3U:     http://${IP:-localhost}:8094/playlist.m3u"
echo ""
echo "For Channels DVR, use your LAN IP (${IP:-YOUR_IP}), not localhost!"
echo ""
