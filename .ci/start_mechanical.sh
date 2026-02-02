#!/bin/bash
echo "Starting Mechanical container with verbose logging..."
docker run --name mechanical -d \
    -p ${PYMECHANICAL_PORT}:10000 \
    --entrypoint /bin/bash \
    --env ANSYSLMD_LICENSE_FILE=1055@${LICENSE_SERVER} \
    --env ANSYS_LOCK='OFF' \
    --shm-size=2gb \
    ${MECHANICAL_IMAGE} \
    > mechanical_launch.log 2>&1

echo "Container started. Container ID:"
docker ps -a --filter "name=mechanical" --format "{{.ID}} {{.Status}} {{.Command}}"

echo "Capturing initial container logs..."
docker logs mechanical > mechanical_initial.log 2>&1 || true
cat mechanical_initial.log
