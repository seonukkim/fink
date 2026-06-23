#!/usr/bin/env bash
set -euo pipefail

source "$HOME/fai/fink-env.sh"

mkdir -p \
  "$PRIVATE_ROOT/runtime" \
  "$PRIVATE_ROOT/models/huggingface" \
  "$PRIVATE_ROOT/models/quantized" \
  "$PRIVATE_ROOT/model-research/raw" \
  "$PRIVATE_ROOT/model-research/benchmarks" \
  "$PRIVATE_ROOT/model-research/manifests"

cat > "$PRIVATE_ROOT/runtime/fink-model.env" <<EOF
HF_HOME=$HOME/.cache/huggingface
HF_HUB_CACHE=$HOME/.cache/huggingface/hub
HF_HUB_DISABLE_TELEMETRY=1
DO_NOT_TRACK=1

FINK_MODEL_ROOT=$PRIVATE_ROOT/models
FINK_HF_MODEL_ROOT=$PRIVATE_ROOT/models/huggingface
FINK_QUANTIZED_MODEL_ROOT=$PRIVATE_ROOT/models/quantized
FINK_MODEL_RESEARCH_ROOT=$PRIVATE_ROOT/model-research

FINK_RUNTIME_REMOTE_API_ALLOWED=false
FINK_RUNTIME_OFFLINE=true
FINK_MODEL_DOWNLOAD_ALLOWED=false
EOF

chmod 600 "$PRIVATE_ROOT/runtime/fink-model.env"

echo "Created: $PRIVATE_ROOT/runtime/fink-model.env"
echo "No token was copied into the file."
