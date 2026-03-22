import "dotenv/config";
import express from "express";
import { execSync } from "child_process";
import { mkdirSync, writeFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { TripletexClient } from "./tripletex-client.js";
import { runAgent } from "./agent.js";
import type { SolveRequest } from "./types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");
const LOGS_DIR = resolve(__dirname, "../logs");
const TEST_LOGS_DIR = resolve(__dirname, "../test-logs");
mkdirSync(LOGS_DIR, { recursive: true });
mkdirSync(TEST_LOGS_DIR, { recursive: true });

const app = express();
app.use(express.json({ limit: "50mb" }));

const API_KEY = process.env.API_KEY;

function gitPush() {
  try {
    execSync("git add logs/", { cwd: resolve(__dirname, "..") });
    const timestamp = new Date().toISOString();
    execSync(`git commit -m "Add solve log ${timestamp}"`, {
      cwd: resolve(__dirname, ".."),
    });
    execSync("git push origin main", { cwd: REPO_ROOT });
    console.log("Pushed logs to git");
  } catch (e) {
    console.error("Git push failed:", e);
  }
}

app.post("/solve", async (req, res) => {
  if (API_KEY) {
    const auth = req.headers.authorization;
    if (auth !== `Bearer ${API_KEY}`) {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }
  }

  const body = req.body as SolveRequest;

  if (!body.prompt || !body.tripletex_credentials) {
    res.status(400).json({ error: "Missing prompt or credentials" });
    return;
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const isCompetition = body.tripletex_credentials?.base_url?.includes("tx-proxy");
  const logDir = isCompetition ? LOGS_DIR : TEST_LOGS_DIR;
  const logFile = resolve(logDir, `${timestamp}.json`);

  const startTime = new Date();
  const logData: Record<string, unknown> = {
    timestamp: startTime.toISOString(),
    startTime: startTime.toISOString(),
    request: {
      prompt: body.prompt,
      base_url: body.tripletex_credentials?.base_url || "NOT_SET",
      has_token: !!body.tripletex_credentials?.session_token,
      files: (body.files || []).map((f) => ({
        filename: f.filename,
        mime_type: f.mime_type,
        size: f.content_base64.length,
        content_base64: f.content_base64,
      })),
    },
  };

  const client = new TripletexClient(body.tripletex_credentials);
  try {
    const result = await runAgent(client, body.prompt, body.files || []);
    console.log(
      `Completed: ${result.callCount} API calls, ${result.errorCount} errors`
    );

    logData.endTime = new Date().toISOString();
    logData.durationMs = Date.now() - startTime.getTime();
    logData.response = { status: "completed" };
    logData.agent = {
      callCount: result.callCount,
      errorCount: result.errorCount,
      messages: result.messages,
    };
    logData.apiCalls = client.apiCalls;

    writeFileSync(logFile, JSON.stringify(logData, null, 2));
    if (isCompetition) gitPush();

    res.json({ status: "completed" });
  } catch (e) {
    console.error("Agent error:", e);

    logData.endTime = new Date().toISOString();
    logData.durationMs = Date.now() - startTime.getTime();
    logData.response = { status: "completed" };
    logData.error = String(e);
    logData.apiCalls = client.apiCalls;

    writeFileSync(logFile, JSON.stringify(logData, null, 2));
    if (isCompetition) gitPush();

    res.json({ status: "completed" });
  }
});

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

const PORT = parseInt(process.env.PORT || "3000");
app.listen(PORT, () => {
  console.log(`Tripletex agent running on port ${PORT}`);
});
