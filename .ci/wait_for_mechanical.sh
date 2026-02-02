#!/bin/bash

echo "Waiting for Mechanical to start..."
for i in {1..5}; do
    # Capture logs continuously for debugging
    docker logs mechanical > "mechanical_logs_attempt_${i}.log" 2>&1 || true

    # Check container status
    CONTAINER_STATUS=$(docker inspect -f '{{.State.Status}}' mechanical 2>/dev/null || echo "not found")
    echo "Attempt $i/5: Container status: $CONTAINER_STATUS"

    if [ "$CONTAINER_STATUS" = "exited" ]; then
        echo "ERROR: Container has exited!"
        docker logs mechanical 2>&1
        exit 1
    fi

    # Check for ready message in logs
    if docker logs mechanical 2>&1 | grep -q "Server listening on"; then
        echo "Mechanical is ready!"
        echo "=== Final Mechanical logs ==="
        docker logs mechanical 2>&1
        exit 0
    fi

    # Show last 20 lines of logs for debugging
    echo "Latest logs:"
    docker logs --tail 20 mechanical 2>&1 || echo "No logs yet"

    sleep 2
done

echo "Mechanical failed to start within 120 seconds"
echo "=== Container status ==="
docker ps -a
echo "=== Full container logs ==="
docker logs mechanical 2>&1
echo "=== Container inspection ==="
docker inspect mechanical
exit 1
