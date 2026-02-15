#!/bin/bash
# Rebuild and restart ESPN4CC4C container

set -e

cd ~/Projects/ESPN4CC4C

echo "🔨 Building new container image..."
docker build -t espn4cc4c:latest .

echo ""
echo "🛑 Stopping current container..."
docker stop espn4cc4c || true

echo ""
echo "🗑️  Removing old container..."
docker rm espn4cc4c || true

echo ""
echo "🚀 Starting new container..."
docker run -d \
  --name espn4cc4c \
  --restart unless-stopped \
  -p 8094:8094 \
  -v ~/Projects/ESPN4CC4C/data:/app/data \
  -v ~/Projects/ESPN4CC4C/out:/app/out \
  -v ~/Projects/ESPN4CC4C/logs:/app/logs \
  -v ~/Projects/ESPN4CC4C/filters.ini:/app/filters.ini:ro \
  --env-file ~/Projects/ESPN4CC4C/.env \
  espn4cc4c:latest

echo ""
echo "⏳ Waiting for container to start..."
sleep 3

echo ""
echo "📋 Container status:"
docker ps | grep espn4cc4c

echo ""
echo "📝 Recent logs:"
docker logs --tail 30 espn4cc4c

echo ""
echo "✅ Container rebuilt and restarted successfully!"
echo "📊 Check scheduler status at: http://localhost:8094/admin/refresh"
