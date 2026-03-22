#!/bin/bash
# End-to-end: prepare data, setup server, train, evaluate, make submission, test on L4.
#
# Prerequisites:
#   - data/annotations.json and data/images/*.jpg (as downloaded from competition)
#   - vast.ai instance running with SSH access
#   - GCP L4 instance (test-l4) available
#
# Usage:
#   ./run.sh                          # full pipeline
#   ./run.sh --skip-train             # skip training, use existing best.pt
#   ./run.sh --epochs 120             # custom epoch count
set -e
cd "$(dirname "$0")"

VAST_SSH="ssh -o StrictHostKeyChecking=no -p 46442 root@38.117.87.49"
VAST_SCP_HOST="root@38.117.87.49"
VAST_SCP_PORT="46442"
SKIP_TRAIN=false
EPOCHS=60
BATCH=16
DEVICE="0,1,2,3"
NAME="yolov8x"

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-train) SKIP_TRAIN=true; shift ;;
        --epochs) EPOCHS=$2; shift 2 ;;
        --batch) BATCH=$2; shift 2 ;;
        --device) DEVICE=$2; shift 2 ;;
        --name) NAME=$2; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

REMOTE_DIR="/root/johan"

# ── Step 0: Prepare YOLO dataset locally ──────────────────────────────────────
if [ ! -d dataset/train/images ]; then
    echo "=== Step 0: Preparing YOLO dataset ==="
    python3 prepare_data.py
else
    echo "=== Step 0: Dataset already prepared ==="
fi

# ── Step 1: Setup server ─────────────────────────────────────────────────────
echo "=== Step 1: Setup server ==="
$VAST_SSH "mkdir -p $REMOTE_DIR"
$VAST_SSH "pip install -q ultralytics==8.4.24 pycocotools opencv-python-headless numpy==1.26.4 2>&1 | tail -1"

if $VAST_SSH "test -f $REMOTE_DIR/dataset/train/images/img_00001.jpg" 2>/dev/null; then
    echo "Data already on server"
else
    echo "Uploading data..."
    tar chf /tmp/v2_upload.tar dataset/ data/annotations.json dataset.yaml
    scp -o StrictHostKeyChecking=no -P $VAST_SCP_PORT /tmp/v2_upload.tar $VAST_SCP_HOST:$REMOTE_DIR/
    $VAST_SSH "cd $REMOTE_DIR && tar xf v2_upload.tar && rm v2_upload.tar && mv data/annotations.json . && rmdir data"
    rm /tmp/v2_upload.tar
    $VAST_SSH "sed -i 's|^path:.*|path: $REMOTE_DIR/dataset|' $REMOTE_DIR/dataset.yaml"
fi

scp -o StrictHostKeyChecking=no -P $VAST_SCP_PORT train.py evaluate.py $VAST_SCP_HOST:$REMOTE_DIR/

# ── Step 2: Train ────────────────────────────────────────────────────────────
if [ "$SKIP_TRAIN" = true ]; then
    echo "=== Step 2: Skipping training ==="
else
    echo "=== Step 2: Training ($EPOCHS epochs, device=$DEVICE, batch=$BATCH) ==="
    $VAST_SSH "cd $REMOTE_DIR && python3 train.py --epochs $EPOCHS --batch $BATCH --device $DEVICE --name $NAME 2>&1" | tail -20
fi

BEST_PT="$REMOTE_DIR/runs/$NAME/weights/best.pt"

# ── Step 3: Evaluate on val ──────────────────────────────────────────────────
echo "=== Step 3: Evaluate on val ==="
$VAST_SSH "cd $REMOTE_DIR && python3 evaluate.py $BEST_PT --device cuda:0"

# ── Step 4: Export ONNX ──────────────────────────────────────────────────────
echo "=== Step 4: Export ONNX ==="
$VAST_SSH "cd $REMOTE_DIR && python3 -c \"
import torch
torch.load = (lambda _orig: lambda *a, **kw: _orig(*a, **{**kw, 'weights_only': False}))(torch.load)
from ultralytics import YOLO
model = YOLO('$BEST_PT')
model.export(format='onnx', imgsz=1280, opset=17, simplify=True, half=False)
\"" 2>&1 | tail -3

BEST_ONNX="${BEST_PT%.pt}.onnx"

# ── Step 5: Download and create submission ───────────────────────────────────
echo "=== Step 5: Create submission ==="
scp -o StrictHostKeyChecking=no -P $VAST_SCP_PORT $VAST_SCP_HOST:$BEST_ONNX submission/best.onnx
cd submission && zip -r ../submission.zip . -x ".*" "__MACOSX/*" && cd ..
ls -lh submission.zip

# ── Step 6: Test on L4 ──────────────────────────────────────────────────────
echo "=== Step 6: Test on L4 ==="
gcloud compute instances start test-l4 --zone=us-central1-a 2>/dev/null || true
sleep 5
gcloud compute scp submission.zip test-l4:~/submission.zip --zone=us-central1-a
gcloud compute ssh test-l4 --zone=us-central1-a --command="
rm -rf /tmp/test_sub /tmp/test_out && mkdir -p /tmp/test_sub /tmp/test_out
cd /tmp/test_sub && unzip -o ~/submission.zip
time python3 run.py --input ~/data/train/images --output /tmp/test_out/predictions.json
python3 -c '
import json
with open(\"/tmp/test_out/predictions.json\") as f:
    p = json.load(f)
ids = set(x[\"image_id\"] for x in p)
scores = [x[\"score\"] for x in p]
print(f\"{len(p)} preds, {len(ids)} images, score range {min(scores):.4f}-{max(scores):.4f}\")
'
"

echo ""
echo "=== Done! submission.zip is ready to upload ==="
