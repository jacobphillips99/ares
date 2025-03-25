#!/bin/bash
# Script to download data from Hugging Face hub, covering roughly 5000 rollouts from the Open X-Embodiment project. Includes:
#   - robot_data.db (StructuredDatabase SQLite database)
#   - embedding_data (EmbeddingDatabase IndexManager)
#   - annotation_mongodump (AnnotationDatabase MongoDB dump)
#   - videos (videos and frames)
# Usage: ./pull_from_hub.sh [output_directory]

set -euo pipefail

OUTDIR="${1:-$HOME/ares/data}"
HF_REPO="jacobphillips99/ares-data"
HF_BASE="https://huggingface.co/datasets/$HF_REPO"
HF_DOWNLOAD="$HF_BASE/resolve/main"

# Check for HF token
if [ -z "${HUGGINGFACE_API_KEY:-}" ]; then
    echo "Error: HUGGINGFACE_API_KEY environment variable is not set"
    exit 1
fi

mkdir -p "$OUTDIR"

echo "downloading robot_data.db..."
curl -L -H "Authorization: Bearer $HUGGINGFACE_API_KEY" "$HF_DOWNLOAD/robot_data.db" -o "$OUTDIR/robot_data.db"

echo "downloading embedding_data..."
curl -L -H "Authorization: Bearer $HUGGINGFACE_API_KEY" "$HF_DOWNLOAD/embedding_data.tar.gz" -o "$OUTDIR/embedding_data.tar.gz"
tar -xzf "$OUTDIR/embedding_data.tar.gz" -C "$OUTDIR"
rm "$OUTDIR/embedding_data.tar.gz"

echo "downloading annotation_mongodump..."
curl -L -H "Authorization: Bearer $HUGGINGFACE_API_KEY" "$HF_DOWNLOAD/annotation_mongodump.tar.gz" -o "$OUTDIR/annotation_mongodump.tar.gz"
tar -xzf "$OUTDIR/annotation_mongodump.tar.gz" -C "$OUTDIR"
rm "$OUTDIR/annotation_mongodump.tar.gz"

echo "restoring mongo backup..."
mongorestore --uri="mongodb://localhost:27017" "$OUTDIR/annotation_mongodump"

echo "downloading videos..."
mkdir -p "$OUTDIR/videos"

# Get list of video dataset tars from HF hub
echo "fetching video datasets..."
API_URL="https://huggingface.co/api/datasets/$HF_REPO/tree/main/videos"
echo "Fetching from: $API_URL"
for tar_file in $(curl -s -H "Authorization: Bearer $HUGGINGFACE_API_KEY" "$API_URL" | grep -o '"path":"videos/[^"]*\.tar\.gz"' | cut -d'"' -f4 | cut -d'/' -f2); do
    echo "Found tar file: $tar_file"
    echo "downloading and extracting $tar_file..."
    curl -L -H "Authorization: Bearer $HUGGINGFACE_API_KEY" "$HF_DOWNLOAD/videos/$tar_file" -o "$OUTDIR/videos/$tar_file"
    tar -xzf "$OUTDIR/videos/$tar_file" -C "$OUTDIR"
    rm "$OUTDIR/videos/$tar_file"
done

echo "done."