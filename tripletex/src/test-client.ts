import "dotenv/config";
import type { SolveRequest } from "./types.js";

const AGENT_URL = process.env.AGENT_URL || "http://localhost:3000";
const AGENT_API_KEY = process.env.API_KEY || "";

const SANDBOX_CREDENTIALS = {
  base_url: process.env.TRIPLETEX_BASE_URL || "https://kkpqfuj-amager.tripletex.dev/v2",
  session_token: process.env.TRIPLETEX_SESSION_TOKEN || "eyJ0b2tlbklkIjoyMTQ3NjMwNDAyLCJ0b2tlbiI6IjI2MWFhNjk4LTUzZDctNGMxMS04ZjEzLTBlYjNkYmNmZjBhNiJ9",
};

const TS = Date.now().toString().slice(-6);

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
  // ===== TIER 1: Simple single-entity tasks =====
  {
    name: "Create Employee (nb)",
    tier: 1,
    prompt: `Opprett en ansatt med fornavn Test${TS}, etternavn Ansen, og e-post test${TS}@example.com`,
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/employee", {
        firstName: `Test${TS}`,
        fields: "id,firstName,lastName,email",
      })) as { values: { id: number; firstName: string; lastName: string; email: string }[] };
      const emp = data.values?.find((e) => e.firstName === `Test${TS}`);
      return {
        passed: !!emp,
        checks: [
          { name: "Employee found", passed: !!emp, detail: emp ? `id=${emp.id}` : "not found" },
          { name: "Correct firstName", passed: emp?.firstName === `Test${TS}` },
          { name: "Correct lastName", passed: emp?.lastName === "Ansen" },
          { name: "Correct email", passed: emp?.email === `test${TS}@example.com`, detail: emp?.email },
        ],
      };
    },
  },
  {
    name: "Create Employee (en)",
    tier: 1,
    prompt: `Create an employee with first name Worker${TS}, last name Smith, and email worker${TS}@company.com`,
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/employee", {
        firstName: `Worker${TS}`,
        fields: "id,firstName,lastName,email",
      })) as { values: { id: number; firstName: string; lastName: string; email: string }[] };
      const emp = data.values?.find((e) => e.firstName === `Worker${TS}`);
      return {
        passed: !!emp,
        checks: [
          { name: "Employee found", passed: !!emp, detail: emp ? `id=${emp.id}` : "not found" },
          { name: "Correct firstName", passed: emp?.firstName === `Worker${TS}` },
          { name: "Correct lastName", passed: emp?.lastName === "Smith" },
          { name: "Correct email", passed: emp?.email === `worker${TS}@company.com`, detail: emp?.email },
        ],
      };
    },
  },
  {
    name: "Create Employee with Admin Role (nb)",
    tier: 1,
    prompt: `Opprett en ansatt med navn Admin${TS} Nordmann, admin${TS}@example.org. Vedkommende skal være kontoadministrator.`,
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/employee", {
        firstName: `Admin${TS}`,
        fields: "id,firstName,lastName,email",
      })) as { values: { id: number; firstName: string; lastName: string; email: string }[] };
      const emp = data.values?.find((e) => e.firstName === `Admin${TS}`);
      return {
        passed: !!emp,
        checks: [
          { name: "Employee found", passed: !!emp, detail: emp ? `id=${emp.id}` : "not found" },
          { name: "Correct email", passed: emp?.email === `admin${TS}@example.org` },
        ],
      };
    },
  },
  {
    name: "Create Customer (nb)",
    tier: 1,
    prompt: `Opprett en kunde med navn 'Bedrift${TS} AS' og e-post post${TS}@bedrift.no`,
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/customer", {
        name: `Bedrift${TS} AS`,
        fields: "id,name,email,isCustomer",
      })) as { values: { id: number; name: string; email: string; isCustomer: boolean }[] };
      const cust = data.values?.find((c) => c.name === `Bedrift${TS} AS`);
      return {
        passed: !!cust,
        checks: [
          { name: "Customer found", passed: !!cust, detail: cust ? `id=${cust.id}` : "not found" },
          { name: "Correct name", passed: cust?.name === `Bedrift${TS} AS` },
          { name: "Correct email", passed: cust?.email === `post${TS}@bedrift.no`, detail: cust?.email },
          { name: "isCustomer flag", passed: cust?.isCustomer === true },
        ],
      };
    },
  },
  {
    name: "Create Customer (de)",
    tier: 1,
    prompt: `Erstellen Sie einen Kunden mit dem Namen 'Firma${TS} GmbH' und der E-Mail kontakt${TS}@firma.de`,
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/customer", {
        name: `Firma${TS} GmbH`,
        fields: "id,name,email,isCustomer",
      })) as { values: { id: number; name: string; email: string; isCustomer: boolean }[] };
      const cust = data.values?.find((c) => c.name === `Firma${TS} GmbH`);
      return {
        passed: !!cust,
        checks: [
          { name: "Customer found", passed: !!cust, detail: cust ? `id=${cust.id}` : "not found" },
          { name: "Correct name", passed: cust?.name === `Firma${TS} GmbH` },
          { name: "Correct email", passed: cust?.email === `kontakt${TS}@firma.de`, detail: cust?.email },
          { name: "isCustomer flag", passed: cust?.isCustomer === true },
        ],
      };
    },
  },
  {
    name: "Create Department (nb)",
    tier: 1,
    prompt: `Opprett en avdeling med navn 'Avdeling${TS}' og avdelingsnummer ${parseInt(TS)}`,
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/department", {
        name: `Avdeling${TS}`,
        fields: "id,name,departmentNumber",
      })) as { values: { id: number; name: string; departmentNumber: number }[] };
      const dept = data.values?.find((d) => d.name === `Avdeling${TS}`);
      return {
        passed: !!dept,
        checks: [
          { name: "Department found", passed: !!dept, detail: dept ? `id=${dept.id}` : "not found" },
          { name: "Correct name", passed: dept?.name === `Avdeling${TS}` },
          { name: "Correct number", passed: dept?.departmentNumber === parseInt(TS), detail: String(dept?.departmentNumber) },
        ],
      };
    },
  },
  {
    name: "Create Product (nb)",
    tier: 1,
    prompt: `Opprett et produkt med navn 'Produkt${TS}', produktnummer ${TS}, og pris 1500 kr eks. mva.`,
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/product", {
        number: TS,
        fields: "id,name,number,priceExcludingVatCurrency",
      })) as { values: { id: number; name: string; number: string; priceExcludingVatCurrency: number }[] };
      const prod = data.values?.find((p) => p.number === TS);
      return {
        passed: !!prod,
        checks: [
          { name: "Product found", passed: !!prod, detail: prod ? `id=${prod.id}` : "not found" },
          { name: "Correct name", passed: prod?.name === `Produkt${TS}` },
          { name: "Correct number", passed: prod?.number === TS },
          { name: "Correct price", passed: prod?.priceExcludingVatCurrency === 1500, detail: String(prod?.priceExcludingVatCurrency) },
        ],
      };
    },
  },

  // ===== TIER 2: Multi-step workflows =====
  {
    name: "Create Customer + Order + Invoice (pt)",
    tier: 2,
    prompt: `Crie e envie uma fatura ao cliente Cliente${TS} Lda (org. nº 987${TS}) por 25800 NOK sem IVA. A fatura refere-se a Consultoria em nuvem.`,
    verify: async (baseUrl, auth) => {
      const custData = (await tripletexGet(baseUrl, auth, "/customer", {
        name: `Cliente${TS} Lda`,
        fields: "id,name,organizationNumber",
      })) as { values: { id: number; name: string; organizationNumber: string }[] };
      const cust = custData.values?.find((c) => c.name === `Cliente${TS} Lda`);

      const invoiceData = (await tripletexGet(baseUrl, auth, "/invoice", {
        invoiceDateFrom: "2024-01-01",
        invoiceDateTo: "2027-12-31",
        fields: "id,customer(id,name),amount",
        count: "100",
      })) as { values: { id: number; customer: { id: number; name: string }; amount: number }[] };
      const invoice = invoiceData.values?.find((i) => i.customer?.name === `Cliente${TS} Lda`);

      return {
        passed: !!cust && !!invoice,
        checks: [
          { name: "Customer created", passed: !!cust, detail: cust ? `id=${cust.id}` : "not found" },
          { name: "Invoice created", passed: !!invoice, detail: invoice ? `id=${invoice.id}` : "not found" },
          { name: "Invoice linked to customer", passed: invoice?.customer?.id === cust?.id },
        ],
      };
    },
  },
  {
    name: "Create Project with Manager (nb)",
    tier: 2,
    prompt: `Opprett et prosjekt med navn 'Prosjekt${TS}', prosjektnummer ${TS}. Bruk den første ansatte som prosjektleder.`,
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/project", {
        number: TS,
        fields: "id,name,number,projectManager(id,firstName,lastName)",
      })) as {
        values: {
          id: number;
          name: string;
          number: string;
          projectManager: { id: number; firstName: string; lastName: string };
        }[];
      };
      const proj = data.values?.find((p) => p.number === TS);
      return {
        passed: !!proj,
        checks: [
          { name: "Project found", passed: !!proj, detail: proj ? `id=${proj.id}` : "not found" },
          { name: "Correct name", passed: proj?.name === `Prosjekt${TS}` },
          { name: "Has project manager", passed: !!proj?.projectManager?.id },
        ],
      };
    },
  },
  {
    name: "Create Customer + Product + Order (fr)",
    tier: 2,
    prompt: `Créez un client 'Société${TS} SARL' avec l'email contact${TS}@societe.fr. Créez un produit 'Service${TS}' avec le numéro ${TS} au prix de 3000 NOK HT. Créez ensuite une commande pour ce client avec ce produit.`,
    verify: async (baseUrl, auth) => {
      const custData = (await tripletexGet(baseUrl, auth, "/customer", {
        name: `Société${TS} SARL`,
        fields: "id,name,email",
      })) as { values: { id: number; name: string; email: string }[] };
      const cust = custData.values?.find((c) => c.name === `Société${TS} SARL`);

      const prodData = (await tripletexGet(baseUrl, auth, "/product", {
        number: TS,
        fields: "id,name,number",
      })) as { values: { id: number; name: string; number: string }[] };
      const prod = prodData.values?.find((p) => p.number === TS);

      const orderData = (await tripletexGet(baseUrl, auth, "/order", {
        fields: "id,customer(id,name),orderLines(product(id,name))",
        count: "100",
      })) as { values: { id: number; customer: { id: number; name: string } }[] };
      const order = orderData.values?.find((o) => o.customer?.name === `Société${TS} SARL`);

      return {
        passed: !!cust && !!prod && !!order,
        checks: [
          { name: "Customer created", passed: !!cust, detail: cust ? `id=${cust.id}` : "not found" },
          { name: "Product created", passed: !!prod, detail: prod ? `id=${prod.id}` : "not found" },
          { name: "Order created", passed: !!order, detail: order ? `id=${order.id}` : "not found" },
          { name: "Order linked to customer", passed: order?.customer?.id === cust?.id },
        ],
      };
    },
  },
  {
    name: "Create Employee + Update Contact (es)",
    tier: 2,
    prompt: `Cree un empleado con nombre Empleado${TS} García, email empleado${TS}@empresa.es y número de teléfono +47${TS}00.`,
    verify: async (baseUrl, auth) => {
      const data = (await tripletexGet(baseUrl, auth, "/employee", {
        firstName: `Empleado${TS}`,
        fields: "id,firstName,lastName,email,phoneNumberMobile",
      })) as { values: { id: number; firstName: string; lastName: string; email: string; phoneNumberMobile: string }[] };
      const emp = data.values?.find((e) => e.firstName === `Empleado${TS}`);
      return {
        passed: !!emp,
        checks: [
          { name: "Employee found", passed: !!emp, detail: emp ? `id=${emp.id}` : "not found" },
          { name: "Correct lastName", passed: emp?.lastName === "García" },
          { name: "Correct email", passed: emp?.email === `empleado${TS}@empresa.es` },
          { name: "Has phone number", passed: !!emp?.phoneNumberMobile, detail: emp?.phoneNumberMobile },
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
  console.log(`Unique suffix: ${TS}`);
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
  console.log(`\nResult: ${passedCount}/${result.checks.length} checks passed`);
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
  console.log(`Unique suffix: ${TS}`);

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
