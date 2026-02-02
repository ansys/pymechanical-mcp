#!/bin/bash

echo "=== Initial launch log ==="
cat mechanical_launch.log 2>/dev/null || echo "No launch log found"

echo "=== Initial container log ==="
cat mechanical_initial.log 2>/dev/null || echo "No initial log found"

echo "=== All captured log files ==="
ls -la mechanical_*.log 2>/dev/null || echo "No log files found"

echo "=== Full Mechanical Container Logs (stdout + stderr) ==="
docker logs mechanical 2>&1 || echo "Could not retrieve container logs"

echo "=== Docker Container Status ==="
docker ps -a --filter "name=mechanical"

echo "=== Docker Container Inspection ==="
docker inspect mechanical 2>&1 || echo "Could not inspect container"

echo "=== Docker Container Stats (if running) ==="
docker stats mechanical --no-stream 2>&1 || echo "Container not running"
