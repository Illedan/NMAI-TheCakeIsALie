#!/bin/bash
# Auto-submit 3 in parallel, wait, analyze all. Run with: bash submit-and-analyze.sh
set -e

COOKIE='access_token=YOUR_ACCESS_TOKEN_HERE'
TASK_ID="cccccccc-cccc-cccc-cccc-cccccccccccc"
TEAM_ID="YOUR_TEAM_ID_HERE"
ENDPOINT_URL="https://YOUR_NGROK_URL_HERE/solve"
ENDPOINT_KEY="YOUR_API_KEY_HERE"
DIR="$(dirname "$0")/submit-results"
mkdir -p "$DIR"

# === Pre-flight checks ===
echo "Pre-flight checks..."
LOCAL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:80/solve 2>/dev/null || echo "000")
if [[ "$LOCAL_STATUS" == "000" ]]; then
    echo "ABORT: Local server is NOT running on port 80"
    exit 1
fi
echo "  ✓ Local server is up (HTTP $LOCAL_STATUS)"

NGROK_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "ngrok-skip-browser-warning: true" -H "Content-Type: application/json" -X POST "$ENDPOINT_URL" -d '{"prompt":"healthcheck"}' 2>/dev/null || echo "000")
if [[ "$NGROK_STATUS" == "000" ]] || [[ "$NGROK_STATUS" == "502" ]] || [[ "$NGROK_STATUS" == "504" ]]; then
    echo "ABORT: ngrok tunnel is NOT reachable (HTTP $NGROK_STATUS)"
    exit 1
fi
echo "  ✓ ngrok tunnel is up (HTTP $NGROK_STATUS)"
echo ""

api() {
    curl -s "$1" -b "$COOKIE" -H 'accept: */*' -H 'origin: https://app.ainm.no' -H 'referer: https://app.ainm.no/' "${@:2}"
}

submit_one() {
    api "https://api.ainm.no/tasks/$TASK_ID/submissions" \
        -H 'content-type: application/json' \
        --data-raw "{\"endpoint_url\":\"$ENDPOINT_URL\",\"endpoint_api_key\":\"$ENDPOINT_KEY\"}"
}

echo ""
echo "=========================================="
echo "  3x PARALLEL SUBMISSION  ($(date +%H:%M:%S))"
echo "=========================================="

api "https://api.ainm.no/tripletex/leaderboard/$TEAM_ID" > "$DIR/tasks_before.json"

# Submit 3
RESP1=$(submit_one); sleep 1
RESP2=$(submit_one); sleep 1
RESP3=$(submit_one)

SUB_ID1=$(echo "$RESP1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','?'))" 2>/dev/null)
SUB_ID2=$(echo "$RESP2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','?'))" 2>/dev/null)
SUB_ID3=$(echo "$RESP3" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','?'))" 2>/dev/null)
USED=$(echo "$RESP3" | python3 -c "import sys,json; print(json.load(sys.stdin).get('daily_submissions_used','?'))" 2>/dev/null)
echo "Submitted #1: $SUB_ID1"
echo "Submitted #2: $SUB_ID2"
echo "Submitted #3: $SUB_ID3"
echo "Daily usage: $USED/300"

parse_result() {
    local FILE="$1"
    local SID="$2"
    python3 -c "
import json
subs = json.load(open('$FILE'))
items = subs if isinstance(subs, list) else subs.get('submissions', subs.get('items', []))
for s in (items if isinstance(items, list) else [items]):
    if s.get('id') == '$SID':
        status = s.get('status', '?')
        score = s.get('score_raw', '?')
        maxs = s.get('score_max', '?')
        norm = s.get('normalized_score', '?')
        dur = s.get('duration_ms', 0)
        fb = s.get('feedback', {})
        comment = fb.get('comment', '')
        checks = fb.get('checks', [])
        print(f'{status}|{score}/{maxs}|{norm}|{dur}|{comment}|{chr(59).join(checks)}')
        break
else:
    print('NOT_FOUND|||0||')
" 2>/dev/null || echo "PARSE_ERR|||0||"
}

print_result() {
    local LABEL="$1"
    local RESULT="$2"
    local STATUS=$(echo "$RESULT" | cut -d'|' -f1)
    local SCORE=$(echo "$RESULT" | cut -d'|' -f2)
    local NORM=$(echo "$RESULT" | cut -d'|' -f3)
    local DUR=$(echo "$RESULT" | cut -d'|' -f4)
    local COMMENT=$(echo "$RESULT" | cut -d'|' -f5)
    local CHECKS=$(echo "$RESULT" | cut -d'|' -f6)
    local DUR_S=$((DUR / 1000))
    echo ""
    echo "  $LABEL RESULT: $SCORE (normalized: $NORM) in ${DUR_S}s"
    echo "  $COMMENT"
    echo "$CHECKS" | tr ';' '\n' | while read -r check; do
        [[ -n "$check" ]] && echo "    $check"
    done
}

sleep 20
DONE1=false; DONE2=false; DONE3=false

for i in $(seq 1 80); do
    api "https://api.ainm.no/tripletex/my/submissions" > "$DIR/subs_poll.json"

    for N in 1 2 3; do
        eval "DONE_VAR=\$DONE${N}; SID=\$SUB_ID${N}"
        if [[ "$DONE_VAR" == "false" ]] && [[ "$SID" != "?" ]]; then
            R=$(parse_result "$DIR/subs_poll.json" "$SID")
            S=$(echo "$R" | cut -d'|' -f1)
            if [[ "$S" == "completed" ]] || [[ "$S" == "done" ]] || [[ "$S" == "finished" ]]; then
                print_result "#$N" "$R"
                eval "DONE${N}=true"
            fi
            eval "S${N}=$S"
        fi
    done

    # All done?
    ALL_DONE=true
    for N in 1 2 3; do
        eval "DONE_VAR=\$DONE${N}; SID=\$SUB_ID${N}"
        if [[ "$DONE_VAR" == "false" ]] && [[ "$SID" != "?" ]]; then
            ALL_DONE=false
        fi
    done
    [[ "$ALL_DONE" == "true" ]] && break

    PENDING=""
    for N in 1 2 3; do
        eval "DONE_VAR=\$DONE${N}; SID=\$SUB_ID${N}; SS=\$S${N}"
        [[ "$DONE_VAR" == "false" && "$SID" != "?" ]] && PENDING="$PENDING #$N:$SS"
    done
    printf "  Poll %d: waiting for%s\r" "$i" "$PENDING"
    sleep 8
done

api "https://api.ainm.no/tripletex/leaderboard/$TEAM_ID" > "$DIR/tasks_after.json"

python3 -c "
import json
before = json.load(open('$DIR/tasks_before.json'))
after = json.load(open('$DIR/tasks_after.json'))
b_tasks = before if isinstance(before, list) else before.get('task_scores', before.get('tasks', []))
a_tasks = after if isinstance(after, list) else after.get('task_scores', after.get('tasks', []))
b_map = {t.get('tx_task_id'): t for t in b_tasks}
a_map = {t.get('tx_task_id'): t for t in a_tasks}
for tid, at in a_map.items():
    bt = b_map.get(tid, {})
    if at.get('total_attempts', 0) != bt.get('total_attempts', 0):
        old_best = bt.get('best_score', 0)
        new_best = at.get('best_score', 0)
        delta = 'NEW BEST!' if new_best > old_best else 'no improvement'
        print(f'  Task {tid}: best {old_best} -> {new_best} ({delta})')
" 2>/dev/null

echo ""
echo "=== All submissions complete ==="
