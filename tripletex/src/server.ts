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
mkdirSync(LOGS_DIR, { recursive: true });

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
  const logFile = resolve(LOGS_DIR, `${timestamp}.json`);

  const logData: Record<string, unknown> = {
    timestamp: new Date().toISOString(),
    request: {
      prompt: body.prompt,
      files: (body.files || []).map((f) => ({
        filename: f.filename,
        mime_type: f.mime_type,
        size: f.content_base64.length,
        content_base64: f.content_base64,
      })),
    },
  };

  try {
    const client = new TripletexClient(body.tripletex_credentials);
    const result = await runAgent(client, body.prompt, body.files || []);
    console.log(
      `Completed: ${result.callCount} API calls, ${result.errorCount} errors`
    );

    logData.response = { status: "completed" };
    logData.agent = {
      callCount: result.callCount,
      errorCount: result.errorCount,
      messages: result.messages,
    };

    writeFileSync(logFile, JSON.stringify(logData, null, 2));
    gitPush();

    res.json({ status: "completed" });
  } catch (e) {
    console.error("Agent error:", e);

    logData.response = { status: "completed" };
    logData.error = String(e);

    writeFileSync(logFile, JSON.stringify(logData, null, 2));
    gitPush();

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
