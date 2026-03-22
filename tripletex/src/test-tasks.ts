/**
 * Test suite for Tripletex agent.
 * Tests key task types against sandbox.
 *
 * Usage: npx tsx src/test-tasks.ts [--type=CURRENCY|LEDGER|ALL]
 */
import "dotenv/config";

const AGENT_URL = process.env.AGENT_URL || "http://localhost:3000";
const API_KEY = process.env.API_KEY || "";
const SANDBOX = {
  base_url: process.env.TRIPLETEX_BASE_URL || "https://kkpqfuj-amager.tripletex.dev/v2",
  session_token: process.env.TRIPLETEX_SESSION_TOKEN || "REDACTED",
};

interface TestCase {
  name: string;
  type: string;
  prompt: string;
  checks: (log: any) => string[];
}

const TESTS: TestCase[] = [
  {
    name: "Currency Exchange (should NOT create invoice)",
    type: "CURRENCY",
    prompt: "We sent an invoice for 5000 EUR to TestCorp Ltd (org no. 972362980) when the exchange rate was 11.00 NOK/EUR. The customer has now paid, but the rate is 11.50 NOK/EUR. Register the payment and post the exchange rate difference (agio) to the correct account.",
    checks: (log) => {
      const errors: string[] = [];
      const calls = log.apiCalls || [];
      for (const c of calls) {
        if (c.method === "POST" && ["/product", "/order", "/invoice"].includes(c.path)) {
          errors.push(`Should NOT POST ${c.path} — invoice already exists`);
        }
        if (c.status >= 400 && c.status !== 403) {
          errors.push(`API error ${c.status} on ${c.method} ${c.path}: ${JSON.stringify(c.error || c.response).slice(0, 100)}`);
        }
      }
      const hasPayment = calls.some((c: any) => c.method === "PUT" && c.path?.includes("/:payment") && c.status < 400);
      if (!hasPayment) errors.push("No successful payment registered");
      const hasVoucher = calls.some((c: any) => c.method === "POST" && c.path === "/ledger/voucher" && c.status < 400);
      if (!hasVoucher) errors.push("No agio/disagio voucher created");
      return errors;
    }
  },
  {
    name: "Ledger Corrections (no VAT splitting)",
    type: "LEDGER",
    prompt: "We have discovered errors in the general ledger for January and February 2026. Review all vouchers and find the 4 errors: a posting to the wrong account (account 6540 used instead of 6860, amount 3150 NOK), a duplicate voucher (account 6500, amount 1500 NOK), a missing VAT line (account 6300, amount excluding VAT 22350 NOK, missing VAT on account 2710), and a wrong amount (account 6540, 20500 NOK posted instead of 17650 NOK). Correct all errors with appropriate correction vouchers.",
    checks: (log) => {
      const errors: string[] = [];
      const calls = log.apiCalls || [];
      const vouchers = calls.filter((c: any) => c.method === "POST" && c.path === "/ledger/voucher" && c.status < 400);
      if (vouchers.length < 4) errors.push(`Only ${vouchers.length} correction vouchers created (need 4)`);

      // Check each voucher has exactly 2 postings
      for (const v of vouchers) {
        const resp = v.response?.value;
        if (resp?.postings?.length !== 2) {
          // Allow 3 for auto-generated VAT posting
          if (resp?.postings?.length === 3) {
            // OK — Tripletex may auto-add VAT posting
          } else {
            errors.push(`Voucher "${resp?.description}" has ${resp?.postings?.length} postings (should be 2)`);
          }
        }
      }

      for (const c of calls) {
        if (c.status >= 400) {
          errors.push(`API error ${c.status} on ${c.method} ${c.path}`);
        }
      }
      return errors;
    }
  },
  {
    name: "Simple Employee Creation",
    type: "EMPLOYEE",
    prompt: "Opprett en ansatt med fornavn TestValidation, etternavn Check, e-post testval@example.com",
    checks: (log) => {
      const errors: string[] = [];
      const calls = log.apiCalls || [];
      const empCreate = calls.find((c: any) => c.method === "POST" && c.path === "/employee" && c.status < 400);
      if (!empCreate) errors.push("Employee not created");
      for (const c of calls) {
        if (c.status >= 400) errors.push(`API error ${c.status} on ${c.method} ${c.path}`);
      }
      if (log.agent?.errorCount > 0) errors.push(`${log.agent.errorCount} errors`);
      return errors;
    }
  },
  {
    name: "Create Invoice (sendToCustomer enforced)",
    type: "INVOICE",
    prompt: "Create and send an invoice to the customer Brightstone Ltd (org no. 836973569) for 10000 NOK excluding VAT. The invoice is for Consulting Services.",
    checks: (log) => {
      const errors: string[] = [];
      const calls = log.apiCalls || [];
      const invCreate = calls.find((c: any) => c.method === "POST" && c.path === "/invoice" && c.status < 400);
      if (!invCreate) errors.push("Invoice not created");
      if (invCreate && !invCreate.params?.sendToCustomer) errors.push("sendToCustomer not set!");
      for (const c of calls) {
        if (c.status >= 400) errors.push(`API error ${c.status} on ${c.method} ${c.path}`);
      }
      return errors;
    }
  },
];

async function runTest(test: TestCase): Promise<{ pass: boolean; errors: string[]; duration: number; calls: number }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) headers["Authorization"] = `Bearer ${API_KEY}`;

  const start = Date.now();
  try {
    const res = await fetch(`${AGENT_URL}/solve`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        prompt: test.prompt,
        tripletex_credentials: SANDBOX,
        files: [],
      }),
      signal: AbortSignal.timeout(180000),
    });
    const duration = Date.now() - start;

    if (!res.ok) {
      return { pass: false, errors: [`HTTP ${res.status}`], duration, calls: 0 };
    }

    // Find the latest test log
    const fs = await import("fs");
    const path = await import("path");
    const logsDir = path.resolve(import.meta.dirname || ".", "../test-logs");
    const logs = fs.readdirSync(logsDir).sort();
    const latestLog = JSON.parse(fs.readFileSync(path.join(logsDir, logs[logs.length - 1]), "utf-8"));

    const errors = test.checks(latestLog);
    return {
      pass: errors.length === 0,
      errors,
      duration,
      calls: latestLog.agent?.callCount || 0
    };
  } catch (e) {
    return { pass: false, errors: [String(e)], duration: Date.now() - start, calls: 0 };
  }
}

async function main() {
  const typeFilter = process.argv.find(a => a.startsWith("--type="))?.split("=")[1]?.toUpperCase();
  const tests = typeFilter && typeFilter !== "ALL"
    ? TESTS.filter(t => t.type === typeFilter)
    : TESTS;

  console.log(`Running ${tests.length} tests...\n`);

  let passed = 0;
  let failed = 0;

  for (const test of tests) {
    process.stdout.write(`  ${test.name}... `);
    const result = await runTest(test);

    if (result.pass) {
      console.log(`✓ PASS (${result.duration}ms, ${result.calls} calls)`);
      passed++;
    } else {
      console.log(`✗ FAIL (${result.duration}ms, ${result.calls} calls)`);
      for (const err of result.errors) {
        console.log(`    - ${err}`);
      }
      failed++;
    }
  }

  console.log(`\n${passed}/${passed + failed} tests passed`);
  process.exit(failed > 0 ? 1 : 0);
}

main();
