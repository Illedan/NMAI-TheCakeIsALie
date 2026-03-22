#!/bin/bash
# Auto-submit script for Astar Island
# Checks if there's an active round with budget, then submits

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
cd /Users/erikkvanli/Repos/NMAI-TheCakeIsALie/astar-erik

LOG="/Users/erikkvanli/Repos/NMAI-TheCakeIsALie/astar-erik/auto_submit_$(date +%Y%m%d_%H%M%S).log"

echo "=== Auto-submit started at $(date) ===" >> "$LOG"

# Check if there's an active round with budget
python3 -c "
import online
token = online.load_token()
try:
    budget = online.api_get('/budget', token)
    if budget.get('active') and budget['queries_used'] == 0:
        print('READY')
    else:
        print(f'SKIP: used={budget.get(\"queries_used\",\"?\")}/{budget.get(\"queries_max\",\"?\")} active={budget.get(\"active\",\"?\")}')
except Exception as e:
    print(f'ERROR: {e}')
" 2>&1 | tee -a "$LOG" | grep -q "READY"

if [ $? -eq 0 ]; then
    echo "Active round with full budget — submitting..." >> "$LOG"
    python3 online.py submit >> "$LOG" 2>&1
    echo "=== Submit complete at $(date) ===" >> "$LOG"
else
    echo "No active round or budget already used — skipping" >> "$LOG"
fi
