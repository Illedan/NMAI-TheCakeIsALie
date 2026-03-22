/**
 * Replay a competition log against our sandbox.
 * Tests the exact prompt, then verifies via API what was created.
 *
 * Usage:
 *   npx tsx src/replay-log.ts                    # replay latest log
 *   npx tsx src/replay-log.ts --last=3           # replay 3rd from last
 *   npx tsx src/replay-log.ts --prompt="Create..." # custom prompt
 *   npx tsx src/replay-log.ts --analyze          # just analyze recent logs, don't replay
 */
import "dotenv/config";
import { readFileSync, readdirSync } from "fs";
import { resolve } from "path";

const AGENT_URL = process.env.AGENT_URL || "http://localhost:3000";
const API_KEY = process.env.API_KEY || "";
const SANDBOX = {
  base_url: process.env.TRIPLETEX_BASE_URL || "https://kkpqfuj-amager.tripletex.dev/v2",
  session_token: process.env.TRIPLETEX_SESSION_TOKEN || "REDACTED",
};

const LOGS_DIR = resolve(import.meta.dirname || ".", "../logs");

interface LogEntry {
  timestamp: string;
  request: { prompt: string; base_url?: string; files?: unknown[] };
  agent?: { callCount?: number; errorCount?: number; messages?: unknown[] };
  apiCalls?: Array<{
    method: string;
    path: string;
    status: number;
    durationMs: number;
    params?: Record<string, unknown>;
    body?: unknown;
    response?: unknown;
    error?: Record<string, unknown>;
  }>;
  error?: string;
}

function loadLog(index: number): LogEntry {
  const files = readdirSync(LOGS_DIR).sort();
  const file = files[files.length - 1 - index];
  return JSON.parse(readFileSync(resolve(LOGS_DIR, file), "utf-8"));
}

function analyzeLog(log: LogEntry) {
  const calls = log.apiCalls || [];
  const errors = calls.filter(c => c.error);
  const totalTime = calls.reduce((s, c) => s + (c.durationMs || 0), 0);

  // Find wasted calls
  const wasted: string[] = [];
  for (let i = 0; i < calls.length; i++) {
    const c = calls[i];
    if (c.error) {
      wasted.push(`ERR: [${c.method}] ${c.path} -> ${c.status}`);
    }
    // Unnecessary GET after POST
    if (c.method === "GET" && i > 0 && calls[i-1].method === "POST" && calls[i-1].status === 201) {
      const prev = calls[i-1].path.split("/")[1];
      const curr = c.path.split("/")[1];
      if (prev === curr) {
        wasted.push(`VERIFY: [GET] ${c.path} (unnecessary after POST)`);
      }
    }
    // Multiple GET to same endpoint
    if (c.method === "GET") {
      const dupes = calls.filter((c2, j) => j < i && c2.method === "GET" && c2.path === c.path && !c2.error);
      if (dupes.length > 0) {
        wasted.push(`DUPE: [GET] ${c.path} (already called)`);
      }
    }
  }

  return { calls: calls.length, errors: errors.length, totalTime, wasted };
}

async function replay(prompt: string): Promise<LogEntry> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) headers["Authorization"] = `Bearer ${API_KEY}`;

  const start = Date.now();
  await fetch(`${AGENT_URL}/solve`, {
    method: "POST",
    headers,
    body: JSON.stringify({ prompt, files: [], tripletex_credentials: SANDBOX }),
  });

  // Read the new log
  const files = readdirSync(LOGS_DIR).sort();
  return JSON.parse(readFileSync(resolve(LOGS_DIR, files[files.length - 1]), "utf-8"));
}

async function main() {
  const args = process.argv.slice(2);
  const analyzeOnly = args.includes("--analyze");
  const lastN = parseInt(args.find(a => a.startsWith("--last="))?.split("=")[1] || "0");
  const customPrompt = args.find(a => a.startsWith("--prompt="))?.split("=").slice(1).join("=");
  const count = parseInt(args.find(a => a.startsWith("--count="))?.split("=")[1] || "10");

  if (analyzeOnly) {
    console.log("=== ANALYZING RECENT COMPETITION LOGS ===\n");
    const files = readdirSync(LOGS_DIR).sort();
    let analyzed = 0;

    for (let i = files.length - 1; i >= 0 && analyzed < count; i--) {
      const log: LogEntry = JSON.parse(readFileSync(resolve(LOGS_DIR, files[i]), "utf-8"));
      if (!log.request?.base_url?.includes("tx-proxy")) continue;

      const analysis = analyzeLog(log);
      const prompt = log.request.prompt.slice(0, 70);
      const hasErr = log.error ? "CRASH" : "";

      console.log(`${log.timestamp?.slice(0, 19)} | ${String(analysis.calls).padStart(2)} calls ${String(analysis.errors).padStart(1)} err ${String(analysis.wasted.length).padStart(1)} waste | ${hasErr || prompt}`);

      if (analysis.wasted.length > 0) {
        for (const w of analysis.wasted.slice(0, 3)) {
          console.log(`  ${w}`);
        }
      }
      analyzed++;
    }

    console.log(`\nAnalyzed ${analyzed} competition submissions`);
    return;
  }

  // Load or create the prompt
  let prompt: string;
  let originalLog: LogEntry | null = null;

  if (customPrompt) {
    prompt = customPrompt;
  } else {
    originalLog = loadLog(lastN);
    prompt = originalLog.request.prompt;
    const origAnalysis = analyzeLog(originalLog);

    console.log("=== ORIGINAL LOG ===");
    console.log(`Prompt: ${prompt.slice(0, 150)}`);
    console.log(`Calls: ${origAnalysis.calls}, Errors: ${origAnalysis.errors}, Wasted: ${origAnalysis.wasted.length}`);
    if (origAnalysis.wasted.length > 0) {
      for (const w of origAnalysis.wasted) console.log(`  ${w}`);
    }
    console.log();
  }

  console.log("=== REPLAYING ===");
  console.log(`Prompt: ${prompt.slice(0, 150)}...`);
  console.log();

  const newLog = await replay(prompt);
  const newAnalysis = analyzeLog(newLog);

  console.log("=== REPLAY RESULT ===");
  console.log(`Calls: ${newAnalysis.calls}, Errors: ${newAnalysis.errors}, Wasted: ${newAnalysis.wasted.length}`);
  if (newLog.error) console.log(`CRASH: ${newLog.error.slice(0, 200)}`);

  // Show all API calls
  for (const ac of (newLog.apiCalls || [])) {
    const body = ac.body ? JSON.stringify(ac.body).slice(0, 120) : "";
    console.log(`  [${ac.method}] ${ac.path} -> ${ac.status} ${ac.error ? "ERR" : "OK"} (${ac.durationMs}ms)`);
    if (body && (ac.method === "POST" || ac.method === "PUT" || ac.error)) console.log(`    ${body}`);
    if (ac.error) {
      const vm = (ac.error as any).validationMessages || (ac.error as any).message || "";
      console.log(`    err: ${JSON.stringify(vm).slice(0, 150)}`);
    }
  }

  if (newAnalysis.wasted.length > 0) {
    console.log("\n  WASTED CALLS:");
    for (const w of newAnalysis.wasted) console.log(`    ${w}`);
  }

  if (originalLog) {
    const origAnalysis = analyzeLog(originalLog);
    console.log(`\n=== COMPARISON ===`);
    console.log(`  Original: ${origAnalysis.calls} calls, ${origAnalysis.errors} errors`);
    console.log(`  Replay:   ${newAnalysis.calls} calls, ${newAnalysis.errors} errors`);
    const improved = newAnalysis.calls < origAnalysis.calls || newAnalysis.errors < origAnalysis.errors;
    const regressed = newAnalysis.calls > origAnalysis.calls + 2 || newAnalysis.errors > origAnalysis.errors;
    console.log(`  ${improved ? "IMPROVED" : regressed ? "REGRESSED" : "SIMILAR"}`);
  }
}

main().catch(console.error);
