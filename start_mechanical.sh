
docker run \
    --name mechanical \
    --restart always \
    -e ANSYSLMD_LICENSE_FILE=1055@${LICENSE_SERVER} \
    -e ANSYS_LOCK="OFF" \
    -p ${PYMECHANICAL_PORT}:10000 \
    --shm-size=2gb \
    -w /jobs \
    -u=0:0 \
    --memory=6656MB \
    --memory-swap=16896MB \
    ${MECHANICAL_IMAGE}
