import express from "express";
import { TripletexClient } from "./tripletex-client.js";
import { runAgent } from "./agent.js";
import type { SolveRequest } from "./types.js";

const app = express();
app.use(express.json({ limit: "50mb" }));

const API_KEY = process.env.API_KEY;

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

  try {
    const client = new TripletexClient(body.tripletex_credentials);
    const result = await runAgent(client, body.prompt, body.files || []);
    console.log(
      `Completed: ${result.callCount} API calls, ${result.errorCount} errors`
    );
    res.json({ status: "completed" });
  } catch (e) {
    console.error("Agent error:", e);
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
