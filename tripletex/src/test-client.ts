import "dotenv/config";
import type { SolveRequest } from "./types.js";

const AGENT_URL = process.env.AGENT_URL || "http://localhost:3000";
const AGENT_API_KEY = process.env.API_KEY || "";

const SANDBOX_CREDENTIALS = {
  base_url: "https://kkpqfuj-amager.tripletex.dev/v2",
  session_token:
    "eyJ0b2tlbklkIjoyMTQ3NjMwNDAyLCJ0b2tlbiI6IjI2MWFhNjk4LTUzZDctNGMxMS04ZjEzLTBlYjNkYmNmZjBhNiJ9",
};

interface TestCase {
  name: string;
  tier: number;
  prompt: string;
  files?: SolveRequest["files"];
  verify: (baseUrl: string, auth: [string, string]) => Promise<VerifyResult>;
}

interface VerifyResult {
  passed: boolean;
  checks: { name: string; passed: boolean; detail?: string }[];
}

async function tripletexGet(
  baseUrl: string,
  auth: [string, string],
  path: string,
  params?: Record<string, string>
): Promise<unknown> {
  const url = new URL(`${baseUrl}${path}`);
  if (params) {
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  }
  const res = await fetch(url.toString(), {
    headers: {
      Authorization: "Basic " + Buffer.from(auth.join(":")).toString("base64"),
      Accept: "application/json",
    },
  });
  return res.json();
}

const TEST_CASES: TestCase[] = [
  {
    name: "Create Employee (Tier 1)",
    tier: 1,
    prompt:
      "Opprett en ansatt med fornavn Erik, etternavn Testesen, og e-post erik.testesen@example.com",
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/employee", {
        firstName: "Erik",
        lastName: "Testesen",
        fields: "id,firstName,lastName,email",
      })) as { values: { id: number; firstName: string; lastName: string; email: string }[] };
      const emp = data.values?.find(
        (e) => e.firstName === "Erik" && e.lastName === "Testesen"
      );
      return {
        passed: !!emp,
        checks: [
          { name: "Employee found", passed: !!emp, detail: emp ? `id=${emp.id}` : "not found" },
          { name: "Correct firstName", passed: emp?.firstName === "Erik" },
          { name: "Correct lastName", passed: emp?.lastName === "Testesen" },
          {
            name: "Correct email",
            passed: emp?.email === "erik.testesen@example.com",
            detail: emp?.email,
          },
        ],
      };
    },
  },
  {
    name: "Create Customer (Tier 1)",
    tier: 1,
    prompt:
      "Opprett en kunde med navn 'Testbedrift AS' og e-post kontakt@testbedrift.no",
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/customer", {
        name: "Testbedrift AS",
        fields: "id,name,email,isCustomer",
      })) as { values: { id: number; name: string; email: string; isCustomer: boolean }[] };
      const cust = data.values?.find((c) => c.name === "Testbedrift AS");
      return {
        passed: !!cust,
        checks: [
          { name: "Customer found", passed: !!cust, detail: cust ? `id=${cust.id}` : "not found" },
          { name: "Correct name", passed: cust?.name === "Testbedrift AS" },
          {
            name: "Correct email",
            passed: cust?.email === "kontakt@testbedrift.no",
            detail: cust?.email,
          },
          { name: "isCustomer flag", passed: cust?.isCustomer === true },
        ],
      };
    },
  },
  {
    name: "Create Department (Tier 1)",
    tier: 1,
    prompt: "Opprett en avdeling med navn 'Salgsavdelingen' og avdelingsnummer 3",
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/department", {
        name: "Salgsavdelingen",
        fields: "id,name,departmentNumber",
      })) as { values: { id: number; name: string; departmentNumber: number }[] };
      const dept = data.values?.find((d) => d.name === "Salgsavdelingen");
      return {
        passed: !!dept,
        checks: [
          { name: "Department found", passed: !!dept, detail: dept ? `id=${dept.id}` : "not found" },
          { name: "Correct name", passed: dept?.name === "Salgsavdelingen" },
          {
            name: "Correct number",
            passed: dept?.departmentNumber === 3,
            detail: String(dept?.departmentNumber),
          },
        ],
      };
    },
  },
  {
    name: "Create Product (Tier 1)",
    tier: 1,
    prompt:
      "Opprett et produkt med navn 'Konsulenttime', produktnummer 1001, og pris 1200 kr eks. mva.",
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/product", {
        number: "1001",
        fields: "id,name,number,priceExcludingVat",
      })) as { values: { id: number; name: string; number: string; priceExcludingVat: number }[] };
      const prod = data.values?.find((p) => p.number === "1001");
      return {
        passed: !!prod,
        checks: [
          { name: "Product found", passed: !!prod, detail: prod ? `id=${prod.id}` : "not found" },
          { name: "Correct name", passed: prod?.name === "Konsulenttime" },
          { name: "Correct number", passed: prod?.number === "1001" },
          {
            name: "Correct price",
            passed: prod?.priceExcludingVat === 1200,
            detail: String(prod?.priceExcludingVat),
          },
        ],
      };
    },
  },
  {
    name: "Create Employee with Admin Role (Tier 1)",
    tier: 1,
    prompt:
      "Opprett en ansatt med navn Ola Nordmann, ola@example.org. Han skal være kontoadministrator.",
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/employee", {
        firstName: "Ola",
        lastName: "Nordmann",
        fields: "id,firstName,lastName,email",
      })) as { values: { id: number; firstName: string; lastName: string; email: string }[] };
      const emp = data.values?.find(
        (e) => e.firstName === "Ola" && e.lastName === "Nordmann"
      );
      return {
        passed: !!emp,
        checks: [
          { name: "Employee found", passed: !!emp, detail: emp ? `id=${emp.id}` : "not found" },
          { name: "Correct email", passed: emp?.email === "ola@example.org" },
        ],
      };
    },
  },
  {
    name: "Create Customer and Invoice (Tier 2)",
    tier: 2,
    prompt:
      "Opprett en kunde 'Faktura Test AS' med e-post faktura@test.no. Opprett deretter en ordre med en ordrelinje for 'Rådgivning' til 5000 kr eks. mva, og lag en faktura basert på ordren.",
    verify: async (baseUrl, auth) => {
      const custData = (await tripletexGet(baseUrl, auth, "/customer", {
        name: "Faktura Test AS",
        fields: "id,name,email",
      })) as { values: { id: number; name: string; email: string }[] };
      const cust = custData.values?.find((c) => c.name === "Faktura Test AS");

      const invoiceData = (await tripletexGet(baseUrl, auth, "/invoice", {
        fields: "id,customer(id,name),amount",
        count: "100",
      })) as { values: { id: number; customer: { id: number; name: string }; amount: number }[] };
      const invoice = invoiceData.values?.find(
        (i) => i.customer?.name === "Faktura Test AS"
      );

      return {
        passed: !!cust && !!invoice,
        checks: [
          { name: "Customer created", passed: !!cust },
          { name: "Invoice created", passed: !!invoice, detail: invoice ? `id=${invoice.id}` : "not found" },
          {
            name: "Invoice linked to customer",
            passed: invoice?.customer?.id === cust?.id,
          },
        ],
      };
    },
  },
  {
    name: "Create Project (Tier 2)",
    tier: 2,
    prompt:
      "Opprett et prosjekt med navn 'Nettside Redesign', prosjektnummer 100. Bruk den første ansatte som prosjektleder.",
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/project", {
        number: "100",
        fields: "id,name,number,projectManager(id,firstName,lastName)",
      })) as {
        values: {
          id: number;
          name: string;
          number: string;
          projectManager: { id: number; firstName: string; lastName: string };
        }[];
      };
      const proj = data.values?.find((p) => p.number === "100");
      return {
        passed: !!proj,
        checks: [
          { name: "Project found", passed: !!proj, detail: proj ? `id=${proj.id}` : "not found" },
          { name: "Correct name", passed: proj?.name === "Nettside Redesign" },
          { name: "Has project manager", passed: !!proj?.projectManager?.id },
        ],
      };
    },
  },
];

async function callSolveEndpoint(testCase: TestCase): Promise<{ status: string; durationMs: number }> {
  const payload: SolveRequest = {
    prompt: testCase.prompt,
    files: testCase.files || [],
    tripletex_credentials: SANDBOX_CREDENTIALS,
  };

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (AGENT_API_KEY) headers["Authorization"] = `Bearer ${AGENT_API_KEY}`;

  const start = Date.now();
  const res = await fetch(`${AGENT_URL}/solve`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  const durationMs = Date.now() - start;
  const body = await res.json() as { status: string };
  return { status: body.status, durationMs };
}

async function runTest(testCase: TestCase) {
  const auth: [string, string] = ["0", SANDBOX_CREDENTIALS.session_token];
  const baseUrl = SANDBOX_CREDENTIALS.base_url;

  console.log(`\n${"=".repeat(60)}`);
  console.log(`TEST: ${testCase.name} (Tier ${testCase.tier})`);
  console.log(`Prompt: ${testCase.prompt}`);
  console.log("=".repeat(60));

  console.log("\nCalling /solve...");
  const { status, durationMs } = await callSolveEndpoint(testCase);
  console.log(`Response: ${status} (${(durationMs / 1000).toFixed(1)}s)`);

  console.log("\nVerifying...");
  const result = await testCase.verify(baseUrl, auth);

  for (const check of result.checks) {
    const icon = check.passed ? "PASS" : "FAIL";
    const detail = check.detail ? ` (${check.detail})` : "";
    console.log(`  [${icon}] ${check.name}${detail}`);
  }

  const passedCount = result.checks.filter((c) => c.passed).length;
  console.log(
    `\nResult: ${passedCount}/${result.checks.length} checks passed`
  );
  return result.passed;
}

async function main() {
  const args = process.argv.slice(2);
  const filterTier = args.find((a) => a.startsWith("--tier="));
  const filterName = args.find((a) => a.startsWith("--name="));
  const listOnly = args.includes("--list");

  let tests = TEST_CASES;
  if (filterTier) {
    const tier = parseInt(filterTier.split("=")[1]);
    tests = tests.filter((t) => t.tier === tier);
  }
  if (filterName) {
    const name = filterName.split("=")[1].toLowerCase();
    tests = tests.filter((t) => t.name.toLowerCase().includes(name));
  }

  if (listOnly) {
    console.log("Available test cases:");
    for (const t of TEST_CASES) {
      console.log(`  [Tier ${t.tier}] ${t.name}`);
    }
    return;
  }

  console.log(`Running ${tests.length} test(s) against ${AGENT_URL}`);
  console.log(`Sandbox: ${SANDBOX_CREDENTIALS.base_url}`);

  const results: { name: string; passed: boolean }[] = [];
  for (const test of tests) {
    const passed = await runTest(test);
    results.push({ name: test.name, passed });
  }

  console.log(`\n${"=".repeat(60)}`);
  console.log("SUMMARY");
  console.log("=".repeat(60));
  for (const r of results) {
    console.log(`  [${r.passed ? "PASS" : "FAIL"}] ${r.name}`);
  }
  const total = results.filter((r) => r.passed).length;
  console.log(`\n${total}/${results.length} tests passed`);
}

main().catch(console.error);
