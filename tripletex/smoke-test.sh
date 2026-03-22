#!/bin/bash
# Smoke test: run 1 test against the Tripletex agent server
AGENT_URL="${1:-https://carapaced-overdelicate-joey.ngrok-free.dev}"
API_KEY="${2:-YOUR_API_KEY_HERE}"

cd "$(dirname "$0")"
AGENT_URL="$AGENT_URL" API_KEY="$API_KEY" npx tsx src/test-client.ts --count=1
