/**
 * Comprehensive validation test suite.
 * Tests every competition task type against our sandbox.
 * Uses the actual prompts from competition logs.
 *
 * Usage: npx tsx src/validate-all.ts [--type=INVOICE] [--quick]
 */
import "dotenv/config";
import type { SolveRequest } from "./types.js";

const AGENT_URL = process.env.AGENT_URL || "http://localhost:3000";
const API_KEY = process.env.API_KEY || "";
const SANDBOX = {
  base_url: process.env.TRIPLETEX_BASE_URL || "https://kkpqfuj-amager.tripletex.dev/v2",
  session_token: process.env.TRIPLETEX_SESSION_TOKEN || "REDACTED",
};

const TS = Date.now().toString().slice(-6);
const today = new Date().toISOString().split("T")[0];

interface TestResult {
  name: string;
  calls: number;
  errors: number;
  duration: number;
  status: "pass" | "fail" | "error";
  detail: string;
}

async function solve(prompt: string): Promise<{ calls: number; errors: number; duration: number; topError: string }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) headers["Authorization"] = `Bearer ${API_KEY}`;

  const start = Date.now();
  const res = await fetch(`${AGENT_URL}/solve`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      prompt,
      files: [],
      tripletex_credentials: SANDBOX,
    }),
  });
  const duration = Date.now() - start;
  await res.json();

  // Read latest log
  const { readFileSync, readdirSync } = await import("fs");
  const { resolve } = await import("path");
  const logsDir = resolve(import.meta.dirname || ".", "../logs");
  const logFiles = readdirSync(logsDir).sort();
  const latest = JSON.parse(readFileSync(resolve(logsDir, logFiles[logFiles.length - 1]), "utf-8"));

  return {
    calls: latest.agent?.callCount || 0,
    errors: latest.agent?.errorCount || 0,
    duration,
    topError: latest.error || "",
  };
}

// Target: calls, max_errors
const TESTS: Array<{ name: string; type: string; prompt: string; targetCalls: number; maxErrors: number }> = [
  // TIER 1 - Simple creation
  {
    name: "Employee (simple)",
    type: "EMPLOYEE",
    prompt: `Opprett en ansatt med fornavn Val${TS}, etternavn Testesen, e-post val${TS}@example.com`,
    targetCalls: 2,
    maxErrors: 0,
  },
  {
    name: "Customer (simple)",
    type: "CUSTOMER",
    prompt: `Create a customer called 'ValCust${TS} Ltd' with email valcust${TS}@example.com`,
    targetCalls: 1,
    maxErrors: 0,
  },
  {
    name: "Customer (with address)",
    type: "CUSTOMER",
    prompt: `Opprett kunden ValAddr${TS} AS med org.nr 999${TS}. Adressen er Storgata 1, 0250 Oslo. E-post: valaddr${TS}@example.com`,
    targetCalls: 1,
    maxErrors: 0,
  },
  {
    name: "Product (with VAT)",
    type: "PRODUCT",
    prompt: `Opprett produktet "ValProd${TS}" med produktnummer V${TS}. Prisen er 15000 kr eksklusiv MVA med 25% MVA.`,
    targetCalls: 2,
    maxErrors: 0,
  },
  {
    name: "Department (batch 3)",
    type: "DEPARTMENT",
    prompt: `Crie três departamentos: "ValDept${TS}A", "ValDept${TS}B" e "ValDept${TS}C".`,
    targetCalls: 1,
    maxErrors: 0,
  },
  {
    name: "Project (simple)",
    type: "PROJECT",
    prompt: `Erstellen Sie das Projekt "ValProj${TS}" verknüpft mit dem ersten Kunden. Projektleiter ist der erste Mitarbeiter.`,
    targetCalls: 3,
    maxErrors: 0,
  },
  {
    name: "Supplier",
    type: "SUPPLIER",
    prompt: `Registrer leverandøren ValSup${TS} AS med e-post valsup${TS}@example.com`,
    targetCalls: 1,
    maxErrors: 0,
  },

  // TIER 2 - Multi-step
  {
    name: "Invoice (simple)",
    type: "INVOICE",
    prompt: `Créez et envoyez une facture au client qui existe déjà (org commençant par '9') de 25000 NOK HT pour "Service Val${TS}".`,
    targetCalls: 5,
    maxErrors: 0,
  },
  {
    name: "Invoice (multi-product)",
    type: "INVOICE",
    prompt: `Create an invoice for an existing customer with two products: "ValProdA${TS}" at 10000 NOK with 25% VAT and "ValProdB${TS}" at 5000 NOK with 0% VAT (exempt). Send the invoice.`,
    targetCalls: 6,
    maxErrors: 0,
  },
  {
    name: "Payment registration",
    type: "PAYMENT",
    prompt: `The existing customer's outstanding invoice needs full payment registration. Register the payment.`,
    targetCalls: 4,
    maxErrors: 0,
  },
  {
    name: "Credit note",
    type: "CREDIT_NOTE",
    prompt: `The existing customer has an invoice. Create a full credit note reversing it.`,
    targetCalls: 3,
    maxErrors: 0,
  },
  {
    name: "Employee with start date",
    type: "EMPLOYEE",
    prompt: `Opprett en ansatt ValEmp${TS} Hansen, e-post valemp${TS}@example.com, fødselsdato 15. januar 1990. Startdato er ${today}.`,
    targetCalls: 3,
    maxErrors: 0,
  },
  {
    name: "Project fixed price + invoice",
    type: "PROJECT_FIXED_PRICE",
    prompt: `Sett fastpris 100000 kr på et eksisterende prosjekt. Fakturer kunden for 50% av fastprisen.`,
    targetCalls: 6,
    maxErrors: 0,
  },
  {
    name: "Supplier invoice (voucher)",
    type: "SUPPLIER_INVOICE",
    prompt: `Vi har mottatt faktura VALFAKT-${TS} fra en eksisterende leverandør på 12500 kr inklusiv MVA (25%). Det gjelder kontortjenester (konto 6300). Registrer leverandørfakturaen som et bilag.`,
    targetCalls: 5,
    maxErrors: 0,
  },
  {
    name: "Accounting dimension + voucher",
    type: "ACCOUNTING_DIM",
    prompt: `Opprett en fri regnskapsdimensjon "ValDim${TS}" med verdien "TestVerdi". Bokfør et bilag på konto 6300 for 5000 kr, knyttet til dimensjonsverdien.`,
    targetCalls: 6,
    maxErrors: 0,
  },
  {
    name: "Travel expense",
    type: "TRAVEL_EXPENSE",
    prompt: `Register a travel expense for the first employee for "Client visit Bergen". The trip lasted 3 days from ${today}. Expenses: flight ticket 3000 NOK and taxi 500 NOK. Per diem daily rate 800 NOK.`,
    targetCalls: 8,
    maxErrors: 0,
  },
];

async function main() {
  const args = process.argv.slice(2);
  const filterType = args.find(a => a.startsWith("--type="))?.split("=")[1];
  const quick = args.includes("--quick");

  let tests = TESTS;
  if (filterType) {
    tests = tests.filter(t => t.type.toLowerCase().includes(filterType.toLowerCase()));
  }
  if (quick) {
    // Just run tier 1
    tests = tests.slice(0, 7);
  }

  console.log(`Running ${tests.length} validation tests against ${AGENT_URL}`);
  console.log(`Unique suffix: ${TS}\n`);

  const results: TestResult[] = [];

  for (const test of tests) {
    console.log(`\n${"=".repeat(50)}`);
    console.log(`TEST: ${test.name} (${test.type})`);
    console.log(`Target: ${test.targetCalls} calls, ${test.maxErrors} errors`);
    console.log(`${"=".repeat(50)}`);

    try {
      const { calls, errors, duration, topError } = await solve(test.prompt);

      const callOk = calls <= test.targetCalls + 2; // allow 2 extra
      const errOk = errors <= test.maxErrors;
      const status = topError ? "error" : (callOk && errOk ? "pass" : "fail");

      const detail = topError
        ? `CRASH: ${topError.slice(0, 80)}`
        : `${calls} calls (target ${test.targetCalls}), ${errors} errors`;

      console.log(`  Result: ${status.toUpperCase()} — ${detail} (${(duration/1000).toFixed(1)}s)`);

      results.push({ name: test.name, calls, errors, duration, status, detail });
    } catch (e) {
      console.log(`  EXCEPTION: ${e}`);
      results.push({ name: test.name, calls: 0, errors: 0, duration: 0, status: "error", detail: String(e).slice(0, 80) });
    }
  }

  console.log(`\n${"=".repeat(50)}`);
  console.log("VALIDATION SUMMARY");
  console.log(`${"=".repeat(50)}`);
  console.log(`\nName                                Status   Calls    Errs   Time`);
  console.log("-".repeat(70));
  for (const r of results) {
    const icon = r.status === "pass" ? "OK" : r.status === "fail" ? "!!" : "XX";
    console.log(`${icon} ${r.name.padEnd(33)} ${r.status.padEnd(8)} ${String(r.calls).padEnd(8)} ${String(r.errors).padEnd(6)} ${(r.duration/1000).toFixed(0)}s`);
  }

  const passed = results.filter(r => r.status === "pass").length;
  const failed = results.filter(r => r.status === "fail").length;
  const errored = results.filter(r => r.status === "error").length;
  console.log(`\n${passed} passed, ${failed} inefficient, ${errored} errors out of ${results.length}`);
}

main().catch(console.error);
