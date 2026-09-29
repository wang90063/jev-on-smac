#!/bin/bash
# Download a Hugging Face model via hf-mirror, with retries.
set -u
export PATH="/opt/homebrew/Caskroom/miniconda/base/bin:$PATH"
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HUB_DISABLE_XET=1

REPO="${1:-aac6fef/laya-typed-decisions-mlx}"
DEST="${2:-./$(basename "$REPO")}"
LOG="./$(basename "$DEST").download.log"

mkdir -p "$DEST"

echo "repo=$REPO dest=$DEST log=$LOG endpoint=$HF_ENDPOINT" | tee "$LOG"

for i in $(seq 1 200); do
  echo "===== attempt $i  $(date '+%F %T')  workers=16 =====" | tee -a "$LOG"
  hf download "$REPO" \
    --local-dir "$DEST" \
    --max-workers 16 \
    >>"$LOG" 2>&1
  if [ $? -eq 0 ]; then
    echo "===== DOWNLOAD COMPLETE $(date '+%F %T') =====" | tee -a "$LOG"
    exit 0
  fi
  echo "----- attempt $i failed, retry in 15s -----" | tee -a "$LOG"
  sleep 15
done
echo "===== GAVE UP after 200 attempts =====" | tee -a "$LOG"
exit 1
