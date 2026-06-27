#!/bin/bash
#SBATCH --job-name=grobid-pipeline
#SBATCH --partition=main
#SBATCH --nodes=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=24G
#SBATCH --time=144:00:00
#SBATCH --output=/data/la_360k_sample/intermediate_results/pipeline_%j.log

echo "=== Job started: $(date) ==="
echo "=== Running on node: $(hostname) ==="

# --- Move into grobid directory so grobid.sif resolves correctly ---
cd /data/la_360k_sample/intermediate_results/grobid

# --- Prep writable tmp directory GROBID needs ---
mkdir -p /tmp/grobid_tmp

# --- Java heap + clean environment ---
unset APPTAINERENV_LD_LIBRARY_PATH
unset APPTAINERENV_JAVA_OPTS
export APPTAINERENV_JAVA_OPTS="-Xmx8g -Xms2g -Djava.io.tmpdir=/tmp"

# --- Start GROBID in background ---
echo "=== Starting GROBID server ==="
apptainer exec \
    --cleanenv \
    --writable-tmpfs \
    -B /tmp:/tmp \
    -B /tmp/grobid_tmp:/opt/grobid/grobid-home/tmp \
    -B /dev/shm:/dev/shm \
    -B /data/la_360k_sample/intermediate_results/grobid/grobid_local.yaml:/opt/grobid/grobid-home/config/grobid.yaml \
    --pwd /opt/grobid \
    grobid.sif \
    ./grobid-service/bin/grobid-service server grobid-home/config/grobid.yaml \
    > /data/la_360k_sample/intermediate_results/grobid/grobid_server.log 2>&1 &

GROBID_PID=$!
echo "GROBID started with PID: $GROBID_PID"

# --- Poll until alive (max 5 minutes) ---
echo "=== Waiting for GROBID to become ready ==="
MAX_WAIT=300
ELAPSED=0
until curl -sf http://localhost:8070/api/isalive > /dev/null 2>&1; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "ERROR: GROBID did not start after ${MAX_WAIT}s. Last 30 lines of server log:"
        tail -30 /data/la_360k_sample/intermediate_results/grobid/grobid_server.log
        kill $GROBID_PID 2>/dev/null
        exit 1
    fi
    echo "  Not ready yet... (${ELAPSED}s elapsed)"
    sleep 15
    ELAPSED=$((ELAPSED + 15))
done
echo "=== GROBID is alive after ${ELAPSED}s ==="

# --- Load Python environment ---
echo "=== Loading Python environment ==="
enable_lmod
module load container_env python3/2023.2-py310

# --- Run the extraction pipeline ---
echo "=== Launching extraction pipeline ==="
crun -p ~/envs/r_004 python /scripts/longitudinal_analysis/stage4_convert_pdf_to_xml.py

PIPELINE_EXIT=$?
echo "=== Pipeline exited with code: $PIPELINE_EXIT ==="

# --- Clean shutdown of GROBID ---
echo "=== Shutting down GROBID (PID $GROBID_PID) ==="
kill $GROBID_PID
wait $GROBID_PID 2>/dev/null

echo "=== Job complete: $(date) ==="
exit $PIPELINE_EXIT