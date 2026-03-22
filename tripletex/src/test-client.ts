import "dotenv/config";
import type { SolveRequest } from "./types.js";

const AGENT_URL = process.env.AGENT_URL || "http://localhost:3000";
const AGENT_API_KEY = process.env.API_KEY || "";

const SANDBOX_CREDENTIALS = {
  base_url: process.env.TRIPLETEX_BASE_URL || "https://kkpqfuj-amager.tripletex.dev/v2",
  session_token: process.env.TRIPLETEX_SESSION_TOKEN || "REDACTED",
};

const TS = Date.now().toString().slice(-6);
const today = new Date().toISOString().split("T")[0];

// ============================================================
// Types
// ============================================================

interface TestCase {
  name: string;
  tier: number;
  prompt: string;
  files?: SolveRequest["files"];
  verify: (baseUrl: string, auth: [string, string]) => Promise<VerifyResult>;
}

interface VerifyResult {
  passed: boolean;
  checks: Check[];
}

interface Check {
  name: string;
  passed: boolean;
  detail?: string;
}

// ============================================================
// API helper
// ============================================================

async function api(
  baseUrl: string,
  auth: [string, string],
  path: string,
  params?: Record<string, string>
): Promise<{ status: number; data: any }> {
  const url = new URL(`${baseUrl}${path}`);
  if (params) for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const res = await fetch(url.toString(), {
    headers: {
      Authorization: "Basic " + Buffer.from(auth.join(":")).toString("base64"),
      Accept: "application/json",
    },
  });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  return { status: res.status, data };
}

// ============================================================
// Verify helpers — reduce boilerplate
// ============================================================

function findEmployee(baseUrl: string, auth: [string, string], firstName: string, fields = "id,firstName,lastName,email,phoneNumberMobile,dateOfBirth,userType") {
  return api(baseUrl, auth, "/employee", { firstName, fields, from: "0", count: "1000" });
}

function findCustomer(baseUrl: string, auth: [string, string], name: string, fields = "id,name,email,organizationNumber,isCustomer,isSupplier,isPrivateIndividual,phoneNumber,invoiceEmail,language,invoicesDueIn,invoicesDueInType") {
  return api(baseUrl, auth, "/customer", { name, fields, from: "0", count: "1000" });
}

function findProduct(baseUrl: string, auth: [string, string], nameOrNumber: string, fields = "id,name,number,priceExcludingVatCurrency,priceIncludingVatCurrency,vatType(id,percentage)") {
  // Product API 'number' filter only accepts integer IDs, not product number strings.
  // Use 'name' filter when it looks like a name, otherwise list all and filter client-side.
  return api(baseUrl, auth, "/product", { fields, from: "0", count: "1000" });
}

function findDepartment(baseUrl: string, auth: [string, string], name: string, fields = "id,name,departmentNumber") {
  return api(baseUrl, auth, "/department", { name, fields, from: "0", count: "1000" });
}

function findProject(baseUrl: string, auth: [string, string], number: string, fields = "id,name,number,projectManager(id),startDate,endDate,isInternal,isFixedPrice,isClosed,description") {
  return api(baseUrl, auth, "/project", { number, fields, from: "0", count: "1000" });
}

function findSupplier(baseUrl: string, auth: [string, string], name: string, fields = "id,name,email,phoneNumber,organizationNumber") {
  return api(baseUrl, auth, "/supplier", { from: "0", count: "100", fields });
}

function findInvoice(baseUrl: string, auth: [string, string], customerId: string, fields = "id,customer(id,name),amount,amountOutstanding,invoiceNumber") {
  return api(baseUrl, auth, "/invoice", { customerId, invoiceDateFrom: "2024-01-01", invoiceDateTo: "2027-12-31", fields, from: "0", count: "100" });
}

function findOrder(baseUrl: string, auth: [string, string], customerId: string, fields = "id,customer(id,name),orderLines(id,product(id,name),count,unitPriceExcludingVatCurrency,description)") {
  return api(baseUrl, auth, "/order", { customerId, orderDateFrom: "2024-01-01", orderDateTo: "2027-12-31", fields, from: "0", count: "100" });
}

function findContact(baseUrl: string, auth: [string, string], customerId: string, fields = "id,firstName,lastName,email,phoneNumberMobile,customer(id)") {
  return api(baseUrl, auth, "/contact", { customerId, fields, from: "0", count: "1000" });
}

function chk(name: string, passed: boolean, detail?: string): Check {
  return { name, passed, detail };
}

function result(checks: Check[]): VerifyResult {
  return { passed: checks.every(c => c.passed), checks };
}

// ============================================================
// 100 TEST CASES
// ============================================================

const TEST_CASES: TestCase[] = [

  // ===================================================================
  // TIER 1: Simple single-entity creation (1-35)
  // ===================================================================

  // --- Employees ---
  {
    name: "T1-01 Create Employee (nb)",
    tier: 1,
    prompt: `Opprett en ansatt med fornavn Emp01${TS}, etternavn Hansen, e-post emp01${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp01${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp01${TS}`);
      return result([
        chk("Employee exists", !!e, e ? `id=${e.id}` : "not found"),
        chk("lastName=Hansen", e?.lastName === "Hansen"),
        chk("Correct email", e?.email === `emp01${TS}@example.com`),
      ]);
    },
  },
  {
    name: "T1-02 Create Employee (en)",
    tier: 1,
    prompt: `Create an employee named Emp02${TS} Johnson with email emp02${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp02${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp02${TS}`);
      return result([
        chk("Employee exists", !!e),
        chk("lastName=Johnson", e?.lastName === "Johnson"),
        chk("Correct email", e?.email === `emp02${TS}@example.com`),
      ]);
    },
  },
  {
    name: "T1-03 Create Employee (de)",
    tier: 1,
    prompt: `Erstellen Sie einen Mitarbeiter: Vorname Emp03${TS}, Nachname Müller, E-Mail emp03${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp03${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp03${TS}`);
      return result([
        chk("Employee exists", !!e),
        chk("lastName=Müller", e?.lastName === "Müller"),
      ]);
    },
  },
  {
    name: "T1-04 Create Employee (fr)",
    tier: 1,
    prompt: `Créez un employé avec le prénom Emp04${TS}, le nom Dupont et l'email emp04${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp04${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp04${TS}`);
      return result([
        chk("Employee exists", !!e),
        chk("lastName=Dupont", e?.lastName === "Dupont"),
      ]);
    },
  },
  {
    name: "T1-05 Create Employee (es)",
    tier: 1,
    prompt: `Cree un empleado: nombre Emp05${TS}, apellido García, correo emp05${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp05${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp05${TS}`);
      return result([
        chk("Employee exists", !!e),
        chk("lastName=García", e?.lastName === "García"),
      ]);
    },
  },
  {
    name: "T1-06 Create Employee with admin role (nb)",
    tier: 1,
    prompt: `Opprett en ansatt Emp06${TS} Nordmann, emp06${TS}@example.com. Vedkommende skal være kontoadministrator.`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp06${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp06${TS}`);
      return result([
        chk("Employee exists", !!e),
        chk("Correct email", e?.email === `emp06${TS}@example.com`),
      ]);
    },
  },
  {
    name: "T1-07 Create Employee with phone (en)",
    tier: 1,
    prompt: `Create employee Emp07${TS} Berg, email emp07${TS}@example.com, mobile phone number +4798765432`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp07${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp07${TS}`);
      return result([
        chk("Employee exists", !!e),
        chk("Has phone", !!e?.phoneNumberMobile, e?.phoneNumberMobile),
      ]);
    },
  },
  {
    name: "T1-08 Create Employee with NO_ACCESS (nb)",
    tier: 1,
    prompt: `Opprett en ansatt Emp08${TS} Olsen med e-post emp08${TS}@example.com. Denne ansatte skal ikke ha systemtilgang.`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp08${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp08${TS}`);
      return result([
        chk("Employee exists", !!e),
        chk("Correct email", e?.email === `emp08${TS}@example.com`),
      ]);
    },
  },

  // --- Customers ---
  {
    name: "T1-09 Create Customer (nb)",
    tier: 1,
    prompt: `Opprett en kunde med navn 'Kunde09${TS} AS' og e-post kunde09${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Kunde09${TS} AS`);
      const c = data?.values?.find((x: any) => x.name === `Kunde09${TS} AS`);
      return result([
        chk("Customer exists", !!c, c ? `id=${c.id}` : "not found"),
        chk("Correct email", c?.email === `kunde09${TS}@example.com`),
        chk("isCustomer=true", c?.isCustomer === true),
      ]);
    },
  },
  {
    name: "T1-10 Create Customer (en)",
    tier: 1,
    prompt: `Create a customer called 'Client10${TS} Ltd' with email client10${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Client10${TS} Ltd`);
      const c = data?.values?.find((x: any) => x.name === `Client10${TS} Ltd`);
      return result([
        chk("Customer exists", !!c),
        chk("Correct email", c?.email === `client10${TS}@example.com`),
      ]);
    },
  },
  {
    name: "T1-11 Create Customer (pt)",
    tier: 1,
    prompt: `Crie um cliente chamado 'Cliente11${TS} Lda' com email cliente11${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Cliente11${TS} Lda`);
      const c = data?.values?.find((x: any) => x.name === `Cliente11${TS} Lda`);
      return result([
        chk("Customer exists", !!c),
        chk("Correct email", c?.email === `cliente11${TS}@example.com`),
      ]);
    },
  },
  {
    name: "T1-12 Create Customer (nynorsk)",
    tier: 1,
    prompt: `Opprett ein kunde med namnet 'Kunde12${TS} AS' og e-post kunde12${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Kunde12${TS} AS`);
      const c = data?.values?.find((x: any) => x.name === `Kunde12${TS} AS`);
      return result([
        chk("Customer exists", !!c),
        chk("Correct email", c?.email === `kunde12${TS}@example.com`),
      ]);
    },
  },
  {
    name: "T1-13 Create Customer with org number (nb)",
    tier: 1,
    prompt: `Opprett en kunde 'Firma13${TS} AS' med organisasjonsnummer 9${TS}13 og e-post firma13${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Firma13${TS} AS`);
      const c = data?.values?.find((x: any) => x.name === `Firma13${TS} AS`);
      return result([
        chk("Customer exists", !!c),
        chk("Has org number", !!c?.organizationNumber, c?.organizationNumber),
      ]);
    },
  },
  {
    name: "T1-14 Create Customer with address (en)",
    tier: 1,
    prompt: `Create customer 'Addr14${TS} AS' with email addr14${TS}@example.com. Address: Storgata 1, 0250 Oslo`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Addr14${TS} AS`);
      const c = data?.values?.find((x: any) => x.name === `Addr14${TS} AS`);
      return result([
        chk("Customer exists", !!c),
        chk("Correct email", c?.email === `addr14${TS}@example.com`),
      ]);
    },
  },
  {
    name: "T1-15 Create Customer as both customer and supplier (nb)",
    tier: 1,
    prompt: `Opprett 'DualRole15${TS} AS' med e-post dual15${TS}@example.com som er både kunde og leverandør`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `DualRole15${TS} AS`);
      const c = data?.values?.find((x: any) => x.name === `DualRole15${TS} AS`);
      return result([
        chk("Customer exists", !!c),
        chk("isCustomer=true", c?.isCustomer === true),
        chk("isSupplier=true", c?.isSupplier === true),
      ]);
    },
  },
  {
    name: "T1-16 Create Private Customer (nb)",
    tier: 1,
    prompt: `Opprett en privatkunde med navn 'Privat16${TS}' og e-post privat16${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Privat16${TS}`);
      const c = data?.values?.find((x: any) => x.name === `Privat16${TS}`);
      return result([
        chk("Customer exists", !!c),
        chk("isPrivateIndividual=true", c?.isPrivateIndividual === true),
      ]);
    },
  },
  {
    name: "T1-17 Create Customer with English language (en)",
    tier: 1,
    prompt: `Create customer 'English17${TS} Ltd' with email en17${TS}@example.com. Set the customer language to English.`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `English17${TS} Ltd`);
      const c = data?.values?.find((x: any) => x.name === `English17${TS} Ltd`);
      return result([
        chk("Customer exists", !!c),
        chk("Language=EN", c?.language === "EN"),
      ]);
    },
  },

  // --- Products ---
  {
    name: "T1-18 Create Product (nb)",
    tier: 1,
    prompt: `Opprett et produkt med navn 'Prod18${TS}', produktnummer P18${TS}, og pris 2500 kr eks. mva.`,
    verify: async (b, a) => {
      const { data } = await findProduct(b, a, `P18${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P18${TS}`);
      return result([
        chk("Product exists", !!p, p ? `id=${p.id}` : "not found"),
        chk("Name correct", p?.name === `Prod18${TS}`),
        chk("Price=2500", p?.priceExcludingVatCurrency === 2500, String(p?.priceExcludingVatCurrency)),
      ]);
    },
  },
  {
    name: "T1-19 Create Product (en)",
    tier: 1,
    prompt: `Create a product named 'Prod19${TS}' with product number P19${TS} and price 3000 NOK excluding VAT`,
    verify: async (b, a) => {
      const { data } = await findProduct(b, a, `P19${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P19${TS}`);
      return result([
        chk("Product exists", !!p),
        chk("Price=3000", p?.priceExcludingVatCurrency === 3000, String(p?.priceExcludingVatCurrency)),
      ]);
    },
  },
  {
    name: "T1-20 Create Product (fr)",
    tier: 1,
    prompt: `Créez un produit 'Prod20${TS}' avec le numéro P20${TS} et un prix de 1800 NOK HT`,
    verify: async (b, a) => {
      const { data } = await findProduct(b, a, `P20${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P20${TS}`);
      return result([
        chk("Product exists", !!p),
        chk("Price=1800", p?.priceExcludingVatCurrency === 1800, String(p?.priceExcludingVatCurrency)),
      ]);
    },
  },
  {
    name: "T1-21 Create Product with VAT (nb)",
    tier: 1,
    prompt: `Opprett et produkt 'MVAProd21${TS}' med nummer P21${TS}, pris 1000 kr eks. mva. Sett MVA-type til den utgående MVA-typen som er tilgjengelig.`,
    verify: async (b, a) => {
      const { data } = await findProduct(b, a, `P21${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P21${TS}`);
      return result([
        chk("Product exists", !!p),
        chk("Price=1000", p?.priceExcludingVatCurrency === 1000, String(p?.priceExcludingVatCurrency)),
        chk("Has VAT type", !!p?.vatType?.id),
      ]);
    },
  },

  // --- Departments ---
  {
    name: "T1-22 Create Department (nb)",
    tier: 1,
    prompt: `Opprett en avdeling med navn 'Avd22${TS}' og avdelingsnummer ${parseInt(TS) + 22}`,
    verify: async (b, a) => {
      const { data } = await findDepartment(b, a, `Avd22${TS}`);
      const d = data?.values?.find((x: any) => x.name === `Avd22${TS}`);
      return result([
        chk("Department exists", !!d, d ? `id=${d.id}` : "not found"),
        chk("Correct number", String(d?.departmentNumber) === String(parseInt(TS) + 22), String(d?.departmentNumber)),
      ]);
    },
  },
  {
    name: "T1-23 Create Department (en)",
    tier: 1,
    prompt: `Create a department named 'Dept23${TS}' with department number ${parseInt(TS) + 23}`,
    verify: async (b, a) => {
      const { data } = await findDepartment(b, a, `Dept23${TS}`);
      const d = data?.values?.find((x: any) => x.name === `Dept23${TS}`);
      return result([
        chk("Department exists", !!d),
        chk("Correct number", String(d?.departmentNumber) === String(parseInt(TS) + 23), String(d?.departmentNumber)),
      ]);
    },
  },
  {
    name: "T1-24 Create Department (de)",
    tier: 1,
    prompt: `Erstellen Sie eine Abteilung namens 'Abt24${TS}' mit der Abteilungsnummer ${parseInt(TS) + 24}`,
    verify: async (b, a) => {
      const { data } = await findDepartment(b, a, `Abt24${TS}`);
      const d = data?.values?.find((x: any) => x.name === `Abt24${TS}`);
      return result([
        chk("Department exists", !!d),
      ]);
    },
  },

  // --- Projects ---
  {
    name: "T1-25 Create Project (nb)",
    tier: 1,
    prompt: `Opprett et prosjekt med navn 'Prosj25${TS}' og prosjektnummer P25${TS}`,
    verify: async (b, a) => {
      const { data } = await findProject(b, a, `P25${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P25${TS}`);
      return result([
        chk("Project exists", !!p, p ? `id=${p.id}` : "not found"),
        chk("Name correct", p?.name === `Prosj25${TS}`),
        chk("Has project manager", !!p?.projectManager?.id),
      ]);
    },
  },
  {
    name: "T1-26 Create Project (en)",
    tier: 1,
    prompt: `Create a project named 'Proj26${TS}' with project number P26${TS}`,
    verify: async (b, a) => {
      const { data } = await findProject(b, a, `P26${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P26${TS}`);
      return result([
        chk("Project exists", !!p),
        chk("Has project manager", !!p?.projectManager?.id),
      ]);
    },
  },
  {
    name: "T1-27 Create Internal Project (nb)",
    tier: 1,
    prompt: `Opprett et internt prosjekt med navn 'Intern27${TS}' og prosjektnummer P27${TS}`,
    verify: async (b, a) => {
      const { data } = await findProject(b, a, `P27${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P27${TS}`);
      return result([
        chk("Project exists", !!p),
        chk("isInternal=true", p?.isInternal === true),
      ]);
    },
  },

  // --- Suppliers ---
  {
    name: "T1-28 Create Supplier (nb)",
    tier: 1,
    prompt: `Opprett en leverandør med navn 'Lev28${TS} AS' og e-post lev28${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findSupplier(b, a, `Lev28${TS} AS`);
      const s = data?.values?.find((x: any) => x.name === `Lev28${TS} AS`);
      return result([
        chk("Supplier exists", !!s, s ? `id=${s.id}` : "not found"),
        chk("Correct email", s?.email === `lev28${TS}@example.com`),
      ]);
    },
  },
  {
    name: "T1-29 Create Supplier (en)",
    tier: 1,
    prompt: `Create a supplier named 'Supp29${TS} Inc' with email supp29${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findSupplier(b, a, `Supp29${TS} Inc`);
      const s = data?.values?.find((x: any) => x.name === `Supp29${TS} Inc`);
      return result([
        chk("Supplier exists", !!s),
        chk("Correct email", s?.email === `supp29${TS}@example.com`),
      ]);
    },
  },

  // --- Mixed simple ---
  {
    name: "T1-30 Create Customer with payment terms (nb)",
    tier: 1,
    prompt: `Opprett en kunde 'Betaling30${TS} AS' med e-post bet30${TS}@example.com og betalingsfrist 30 dager`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Betaling30${TS} AS`);
      const c = data?.values?.find((x: any) => x.name === `Betaling30${TS} AS`);
      return result([
        chk("Customer exists", !!c),
        chk("invoicesDueIn=30", c?.invoicesDueIn === 30, String(c?.invoicesDueIn)),
      ]);
    },
  },
  {
    name: "T1-31 Create Product expensive (en)",
    tier: 1,
    prompt: `Create product 'Premium31${TS}' with number P31${TS}, price 99999 NOK excluding VAT`,
    verify: async (b, a) => {
      const { data } = await findProduct(b, a, `P31${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P31${TS}`);
      return result([
        chk("Product exists", !!p),
        chk("Price=99999", p?.priceExcludingVatCurrency === 99999, String(p?.priceExcludingVatCurrency)),
      ]);
    },
  },
  {
    name: "T1-32 Create Customer with invoice email (nb)",
    tier: 1,
    prompt: `Opprett kunde 'Faktura32${TS} AS' med e-post info32${TS}@example.com og faktura-epost faktura32${TS}@example.com`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Faktura32${TS} AS`);
      const c = data?.values?.find((x: any) => x.name === `Faktura32${TS} AS`);
      return result([
        chk("Customer exists", !!c),
        chk("Correct email", c?.email === `info32${TS}@example.com`),
      ]);
    },
  },
  {
    name: "T1-33 Create Fixed Price Project (en)",
    tier: 1,
    prompt: `Create a fixed price project 'Fixed33${TS}' with number P33${TS} and fixed price 150000 NOK`,
    verify: async (b, a) => {
      const { data } = await findProject(b, a, `P33${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P33${TS}`);
      return result([
        chk("Project exists", !!p),
        chk("isFixedPrice=true", p?.isFixedPrice === true),
      ]);
    },
  },
  {
    name: "T1-34 Create Product with decimal price (nb)",
    tier: 1,
    prompt: `Opprett et produkt 'Desimal34${TS}' med nummer P34${TS} og pris 1499.50 kr eks. mva.`,
    verify: async (b, a) => {
      const { data } = await findProduct(b, a, `P34${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P34${TS}`);
      return result([
        chk("Product exists", !!p),
        chk("Price~1499.50", Math.abs((p?.priceExcludingVatCurrency || 0) - 1499.5) < 1, String(p?.priceExcludingVatCurrency)),
      ]);
    },
  },
  {
    name: "T1-35 Create Customer (nb, long name)",
    tier: 1,
    prompt: `Opprett en kunde med navn 'Nordiske Konsulenttjenester og Rådgivning 35${TS} AS' og e-post kontor35${TS}@example.com`,
    verify: async (b, a) => {
      const name = `Nordiske Konsulenttjenester og Rådgivning 35${TS} AS`;
      const { data } = await findCustomer(b, a, name);
      const c = data?.values?.find((x: any) => x.name === name);
      return result([
        chk("Customer exists", !!c),
        chk("Correct email", c?.email === `kontor35${TS}@example.com`),
      ]);
    },
  },

  // ===================================================================
  // TIER 2: Two-step workflows (36-65)
  // ===================================================================

  {
    name: "T2-36 Create Employee in department (nb)",
    tier: 2,
    prompt: `Opprett en avdeling 'IT36${TS}' og deretter en ansatt Emp36${TS} Berg i den avdelingen med e-post emp36${TS}@example.com`,
    verify: async (b, a) => {
      const { data: dd } = await findDepartment(b, a, `IT36${TS}`);
      const dept = dd?.values?.find((x: any) => x.name === `IT36${TS}`);
      const { data: ed } = await findEmployee(b, a, `Emp36${TS}`);
      const emp = ed?.values?.find((x: any) => x.firstName === `Emp36${TS}`);
      return result([
        chk("Department exists", !!dept),
        chk("Employee exists", !!emp),
        chk("Correct email", emp?.email === `emp36${TS}@example.com`),
      ]);
    },
  },
  {
    name: "T2-37 Create Employee with start date (nb)",
    tier: 2,
    prompt: `Opprett en ansatt Emp37${TS} Larsen med e-post emp37${TS}@example.com og startdato ${today}`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp37${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp37${TS}`);
      if (!e) return result([chk("Employee exists", false)]);
      const { data: empls } = await api(b, a, "/employee/employment", { employeeId: String(e.id), from: "0", count: "5" });
      return result([
        chk("Employee exists", !!e),
        chk("Has employment", empls?.values?.length >= 1),
      ]);
    },
  },
  {
    name: "T2-38 Create Employee with start date (en)",
    tier: 2,
    prompt: `Create employee Emp38${TS} Smith, email emp38${TS}@example.com, start date ${today}`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp38${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp38${TS}`);
      if (!e) return result([chk("Employee exists", false)]);
      const { data: empls } = await api(b, a, "/employee/employment", { employeeId: String(e.id), from: "0", count: "5" });
      return result([
        chk("Employee exists", !!e),
        chk("Has employment", empls?.values?.length >= 1),
      ]);
    },
  },
  {
    name: "T2-39 Create Customer + Contact (nb)",
    tier: 2,
    prompt: `Opprett en kunde 'Kontakt39${TS} AS' med e-post kontakt39${TS}@example.com. Legg til en kontaktperson: Ola Nordmann, ola39${TS}@example.com`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Kontakt39${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Kontakt39${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: contacts } = await findContact(b, a, String(c.id));
      const contact = contacts?.values?.find((x: any) => x.email === `ola39${TS}@example.com`);
      return result([
        chk("Customer exists", !!c),
        chk("Contact exists", !!contact),
        chk("Contact name=Ola", contact?.firstName === "Ola"),
      ]);
    },
  },
  {
    name: "T2-40 Create Customer + Product (nb)",
    tier: 2,
    prompt: `Opprett en kunde 'KP40${TS} AS' med e-post kp40${TS}@example.com og et produkt 'Tjeneste40${TS}' med nummer P40${TS} til 5000 kr eks. mva.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `KP40${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `KP40${TS} AS`);
      const { data: pd } = await findProduct(b, a, `P40${TS}`);
      const p = pd?.values?.find((x: any) => x.number === `P40${TS}`);
      return result([
        chk("Customer exists", !!c),
        chk("Product exists", !!p),
        chk("Product price=5000", p?.priceExcludingVatCurrency === 5000),
      ]);
    },
  },
  {
    name: "T2-41 Create Customer + Order (en)",
    tier: 2,
    prompt: `Create customer 'Order41${TS} Ltd' with email order41${TS}@example.com. Then create an order for this customer with a line item: 'Consulting services', quantity 10, unit price 2000 NOK excluding VAT.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Order41${TS} Ltd`);
      const c = cd?.values?.find((x: any) => x.name === `Order41${TS} Ltd`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: od } = await findOrder(b, a, String(c.id));
      const o = od?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Order exists", !!o, o ? `id=${o.id}` : "not found"),
      ]);
    },
  },
  {
    name: "T2-42 Create Project with description (nb)",
    tier: 2,
    prompt: `Opprett et prosjekt 'Besk42${TS}' med nummer P42${TS} og beskrivelse 'Utvikling av ny nettside for kunden'`,
    verify: async (b, a) => {
      const { data } = await findProject(b, a, `P42${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P42${TS}`);
      return result([
        chk("Project exists", !!p),
        chk("Has description", !!p?.description && p.description.length > 0),
      ]);
    },
  },
  {
    name: "T2-43 Create Supplier with phone (nb)",
    tier: 2,
    prompt: `Opprett en leverandør 'LevTlf43${TS} AS' med e-post lev43${TS}@example.com og telefon +4722334455`,
    verify: async (b, a) => {
      const { data } = await findSupplier(b, a, `LevTlf43${TS} AS`);
      const s = data?.values?.find((x: any) => x.name === `LevTlf43${TS} AS`);
      return result([
        chk("Supplier exists", !!s),
        chk("Has phone", !!s?.phoneNumber, s?.phoneNumber),
      ]);
    },
  },
  {
    name: "T2-44 Create Two Employees (en)",
    tier: 2,
    prompt: `Create two employees: 1) Emp44A${TS} Alpha, email emp44a${TS}@example.com. 2) Emp44B${TS} Beta, email emp44b${TS}@example.com`,
    verify: async (b, a) => {
      const { data: d1 } = await findEmployee(b, a, `Emp44A${TS}`);
      const e1 = d1?.values?.find((x: any) => x.firstName === `Emp44A${TS}`);
      const { data: d2 } = await findEmployee(b, a, `Emp44B${TS}`);
      const e2 = d2?.values?.find((x: any) => x.firstName === `Emp44B${TS}`);
      return result([
        chk("Employee A exists", !!e1),
        chk("Employee B exists", !!e2),
      ]);
    },
  },
  {
    name: "T2-45 Create Three Customers (nb)",
    tier: 2,
    prompt: `Opprett tre kunder: 'Kunde45A${TS} AS' (kunde45a${TS}@example.com), 'Kunde45B${TS} AS' (kunde45b${TS}@example.com), og 'Kunde45C${TS} AS' (kunde45c${TS}@example.com)`,
    verify: async (b, a) => {
      const names = ["A", "B", "C"];
      const checks: Check[] = [];
      for (const n of names) {
        const { data } = await findCustomer(b, a, `Kunde45${n}${TS} AS`);
        const c = data?.values?.find((x: any) => x.name === `Kunde45${n}${TS} AS`);
        checks.push(chk(`Customer ${n} exists`, !!c));
      }
      return result(checks);
    },
  },
  {
    name: "T2-46 Create Product + Order (nb)",
    tier: 2,
    prompt: `Opprett et produkt 'Vare46${TS}' med nummer P46${TS} og pris 750 kr eks. mva. Bruk den første kunden i systemet og opprett en bestilling med 5 stk av dette produktet.`,
    verify: async (b, a) => {
      const { data: pd } = await findProduct(b, a, `P46${TS}`);
      const p = pd?.values?.find((x: any) => x.number === `P46${TS}`);
      return result([
        chk("Product exists", !!p),
        chk("Price=750", p?.priceExcludingVatCurrency === 750),
      ]);
    },
  },
  {
    name: "T2-47 Create Department + Project (en)",
    tier: 2,
    prompt: `Create department 'Dev47${TS}' and a project 'Proj47${TS}' (number P47${TS}) assigned to that department`,
    verify: async (b, a) => {
      const { data: dd } = await findDepartment(b, a, `Dev47${TS}`);
      const dept = dd?.values?.find((x: any) => x.name === `Dev47${TS}`);
      const { data: pd } = await findProject(b, a, `P47${TS}`);
      const proj = pd?.values?.find((x: any) => x.number === `P47${TS}`);
      return result([
        chk("Department exists", !!dept),
        chk("Project exists", !!proj),
      ]);
    },
  },
  {
    name: "T2-48 Create Two Products (nb)",
    tier: 2,
    prompt: `Opprett to produkter: 'Prod48A${TS}' (nummer P48A${TS}, pris 1000) og 'Prod48B${TS}' (nummer P48B${TS}, pris 2000) begge eks. mva.`,
    verify: async (b, a) => {
      const { data: d1 } = await findProduct(b, a, `P48A${TS}`);
      const p1 = d1?.values?.find((x: any) => x.number === `P48A${TS}`);
      const { data: d2 } = await findProduct(b, a, `P48B${TS}`);
      const p2 = d2?.values?.find((x: any) => x.number === `P48B${TS}`);
      return result([
        chk("Product A exists", !!p1),
        chk("Product A price=1000", p1?.priceExcludingVatCurrency === 1000),
        chk("Product B exists", !!p2),
        chk("Product B price=2000", p2?.priceExcludingVatCurrency === 2000),
      ]);
    },
  },
  {
    name: "T2-49 Create Customer + Order with two lines (nb)",
    tier: 2,
    prompt: `Opprett kunde 'TwoLine49${TS} AS' med e-post tl49${TS}@example.com. Lag en bestilling med to linjer: 'Konsulenttimer' 10 stk à 1500 kr og 'Reisekostnader' 1 stk à 5000 kr (begge eks. mva.)`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `TwoLine49${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `TwoLine49${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: od } = await findOrder(b, a, String(c.id));
      const o = od?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Order exists", !!o),
        chk("Order has 2+ lines", o?.orderLines?.length >= 2, String(o?.orderLines?.length)),
      ]);
    },
  },
  {
    name: "T2-50 Create Supplier + Customer (dual entity, nb)",
    tier: 2,
    prompt: `Opprett en leverandør 'Partner50${TS} AS' (partner50${TS}@example.com) og en kunde 'Klient50${TS} AS' (klient50${TS}@example.com)`,
    verify: async (b, a) => {
      const { data: sd } = await findSupplier(b, a, `Partner50${TS} AS`);
      const s = sd?.values?.find((x: any) => x.name === `Partner50${TS} AS`);
      const { data: cd } = await findCustomer(b, a, `Klient50${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Klient50${TS} AS`);
      return result([
        chk("Supplier exists", !!s),
        chk("Customer exists", !!c),
      ]);
    },
  },

  // ===================================================================
  // TIER 3: Multi-step complex workflows (51-80)
  // ===================================================================

  {
    name: "T3-51 Full Invoice workflow (nb)",
    tier: 3,
    prompt: `Opprett en kunde 'Faktura51${TS} AS' med e-post fak51${TS}@example.com. Lag en bestilling med 'IT-tjenester' 20 timer à 1200 kr eks. mva. Opprett og send en faktura for denne bestillingen.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Faktura51${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Faktura51${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv, inv ? `id=${inv.id}, amount=${inv.amount}` : "not found"),
      ]);
    },
  },
  {
    name: "T3-52 Full Invoice workflow (en)",
    tier: 3,
    prompt: `Create customer 'Invoice52${TS} Ltd' (inv52${TS}@example.com). Create an order with line: 'Cloud hosting' 12 months at 3500 NOK each excl. VAT. Create and send an invoice.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Invoice52${TS} Ltd`);
      const c = cd?.values?.find((x: any) => x.name === `Invoice52${TS} Ltd`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv),
        chk("Invoice amount > 0", inv?.amount > 0, String(inv?.amount)),
      ]);
    },
  },
  {
    name: "T3-53 Invoice + Payment (nb)",
    tier: 3,
    prompt: `Opprett kunde 'Betalt53${TS} AS' (bet53${TS}@example.com). Bestill 'Programvare' 1 stk à 50000 kr eks. mva. Fakturer og registrer full betaling.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Betalt53${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Betalt53${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv),
        chk("Fully paid (outstanding=0)", inv?.amountOutstanding === 0, `outstanding=${inv?.amountOutstanding}`),
      ]);
    },
  },
  {
    name: "T3-54 Invoice + Payment (en)",
    tier: 3,
    prompt: `Create customer 'Paid54${TS} Ltd' (paid54${TS}@example.com). Order: 'Annual license' 1x 75000 NOK excl VAT. Create invoice and register full payment.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Paid54${TS} Ltd`);
      const c = cd?.values?.find((x: any) => x.name === `Paid54${TS} Ltd`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv),
        chk("Fully paid", inv?.amountOutstanding === 0, `outstanding=${inv?.amountOutstanding}`),
      ]);
    },
  },
  {
    name: "T3-55 Invoice (pt)",
    tier: 3,
    prompt: `Crie e envie uma fatura ao cliente 'Fatura55${TS} Lda' (fat55${TS}@example.com) por 30000 NOK sem IVA para 'Serviços de consultoria'.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Fatura55${TS} Lda`);
      const c = cd?.values?.find((x: any) => x.name === `Fatura55${TS} Lda`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv),
      ]);
    },
  },
  {
    name: "T3-56 Invoice (fr)",
    tier: 3,
    prompt: `Créez un client 'Facture56${TS} SARL' (fac56${TS}@example.com). Commande: 'Développement web' 40h à 1500 NOK HT. Créez et envoyez la facture.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Facture56${TS} SARL`);
      const c = cd?.values?.find((x: any) => x.name === `Facture56${TS} SARL`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv),
      ]);
    },
  },
  {
    name: "T3-57 Invoice (de)",
    tier: 3,
    prompt: `Erstellen Sie den Kunden 'Rechnung57${TS} GmbH' (rech57${TS}@example.com). Bestellung: 'IT-Beratung' 15 Stunden à 2000 NOK exkl. MwSt. Rechnung erstellen und senden.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Rechnung57${TS} GmbH`);
      const c = cd?.values?.find((x: any) => x.name === `Rechnung57${TS} GmbH`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv),
      ]);
    },
  },
  {
    name: "T3-58 Employee onboarding full (nb)",
    tier: 3,
    prompt: `Opprett avdeling 'Utvikling58${TS}'. Opprett en ansatt Emp58${TS} Johansen, emp58${TS}@example.com, i denne avdelingen med startdato ${today}. Vedkommende er født 15. januar 1990.`,
    verify: async (b, a) => {
      const { data: dd } = await findDepartment(b, a, `Utvikling58${TS}`);
      const dept = dd?.values?.find((x: any) => x.name === `Utvikling58${TS}`);
      const { data: ed } = await findEmployee(b, a, `Emp58${TS}`);
      const emp = ed?.values?.find((x: any) => x.firstName === `Emp58${TS}`);
      let hasEmployment = false;
      if (emp) {
        const { data: empls } = await api(b, a, "/employee/employment", { employeeId: String(emp.id), from: "0", count: "5" });
        hasEmployment = empls?.values?.length >= 1;
      }
      return result([
        chk("Department exists", !!dept),
        chk("Employee exists", !!emp),
        chk("Has employment", hasEmployment),
      ]);
    },
  },
  {
    name: "T3-59 Employee onboarding (en)",
    tier: 3,
    prompt: `Create department 'Engineering59${TS}'. Create employee Emp59${TS} Williams (emp59${TS}@example.com), born 1985-06-20, in this department with start date ${today}.`,
    verify: async (b, a) => {
      const { data: ed } = await findEmployee(b, a, `Emp59${TS}`);
      const emp = ed?.values?.find((x: any) => x.firstName === `Emp59${TS}`);
      let hasEmployment = false;
      if (emp) {
        const { data: empls } = await api(b, a, "/employee/employment", { employeeId: String(emp.id), from: "0", count: "5" });
        hasEmployment = empls?.values?.length >= 1;
      }
      return result([
        chk("Employee exists", !!emp),
        chk("Has employment", hasEmployment),
      ]);
    },
  },
  {
    name: "T3-60 Customer + Product + Order + Invoice (nb)",
    tier: 3,
    prompt: `Gjør følgende: 1) Opprett kunde 'Full60${TS} AS' (full60${TS}@example.com). 2) Opprett produkt 'Analyse60${TS}' (P60${TS}, 8000 kr eks. mva). 3) Lag bestilling med 3 stk. 4) Fakturer og send.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Full60${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Full60${TS} AS`);
      const { data: pd } = await findProduct(b, a, `P60${TS}`);
      const p = pd?.values?.find((x: any) => x.number === `P60${TS}`);
      let hasInvoice = false;
      if (c) {
        const { data: id } = await findInvoice(b, a, String(c.id));
        hasInvoice = id?.values?.length >= 1;
      }
      return result([
        chk("Customer exists", !!c),
        chk("Product exists", !!p),
        chk("Invoice exists", hasInvoice),
      ]);
    },
  },
  {
    name: "T3-61 Three departments (en)",
    tier: 3,
    prompt: `Create three departments: 'Sales61${TS}', 'Marketing61${TS}', and 'Support61${TS}'`,
    verify: async (b, a) => {
      const checks: Check[] = [];
      for (const name of [`Sales61${TS}`, `Marketing61${TS}`, `Support61${TS}`]) {
        const { data } = await findDepartment(b, a, name);
        const d = data?.values?.find((x: any) => x.name === name);
        checks.push(chk(`${name} exists`, !!d));
      }
      return result(checks);
    },
  },
  {
    name: "T3-62 Five customers batch (nb)",
    tier: 3,
    prompt: `Opprett fem kunder: 'Batch62A${TS} AS', 'Batch62B${TS} AS', 'Batch62C${TS} AS', 'Batch62D${TS} AS', 'Batch62E${TS} AS'. Alle med e-poster batch62X${TS}@example.com (bytt X med a-e).`,
    verify: async (b, a) => {
      const checks: Check[] = [];
      for (const letter of ["A", "B", "C", "D", "E"]) {
        const name = `Batch62${letter}${TS} AS`;
        const { data } = await findCustomer(b, a, name);
        const c = data?.values?.find((x: any) => x.name === name);
        checks.push(chk(`${letter} exists`, !!c));
      }
      return result(checks);
    },
  },
  {
    name: "T3-63 Invoice with specific amount (nb)",
    tier: 3,
    prompt: `Opprett kunde 'Beløp63${TS} AS' (bel63${TS}@example.com). Bestill 'Rådgivning' 8 timer à 1875 kr eks. mva. Fakturer og send.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Beløp63${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Beløp63${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv),
        chk("Amount > 0", inv?.amount > 0, String(inv?.amount)),
      ]);
    },
  },
  {
    name: "T3-64 Credit note (nb)",
    tier: 3,
    prompt: `Opprett kunde 'Kredit64${TS} AS' (kred64${TS}@example.com). Lag bestilling med 'Lisens' 1 stk à 25000 kr eks. mva. Fakturer. Deretter lag en kreditnota for fakturaen.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Kredit64${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Kredit64${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      return result([
        chk("Customer exists", !!c),
        chk("Has invoices (incl credit note)", id?.values?.length >= 1),
      ]);
    },
  },
  {
    name: "T3-65 Employee + Project assignment (nb)",
    tier: 3,
    prompt: `Opprett ansatt Emp65${TS} Knutsen (emp65${TS}@example.com). Opprett prosjekt 'Prosjekt65${TS}' (P65${TS}) med denne ansatte som prosjektleder.`,
    verify: async (b, a) => {
      const { data: ed } = await findEmployee(b, a, `Emp65${TS}`);
      const emp = ed?.values?.find((x: any) => x.firstName === `Emp65${TS}`);
      const { data: pd } = await findProject(b, a, `P65${TS}`);
      const proj = pd?.values?.find((x: any) => x.number === `P65${TS}`);
      return result([
        chk("Employee exists", !!emp),
        chk("Project exists", !!proj),
        chk("Employee is PM", proj?.projectManager?.id === emp?.id),
      ]);
    },
  },

  // ===================================================================
  // TIER 3 continued: More complex workflows (66-80)
  // ===================================================================

  {
    name: "T3-66 Invoice (es)",
    tier: 3,
    prompt: `Cree el cliente 'Factura66${TS} SL' (fac66${TS}@example.com). Pida 'Servicios IT' 25 horas a 1600 NOK cada una sin IVA. Cree y envíe la factura.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Factura66${TS} SL`);
      const c = cd?.values?.find((x: any) => x.name === `Factura66${TS} SL`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", id?.values?.length >= 1),
      ]);
    },
  },
  {
    name: "T3-67 Two invoices same customer (nb)",
    tier: 3,
    prompt: `Opprett kunde 'ToFakt67${TS} AS' (tf67${TS}@example.com). Lag to separate bestillinger: 'Tjeneste A' 5 stk à 3000 kr og 'Tjeneste B' 10 stk à 1500 kr (begge eks. mva). Fakturer begge.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `ToFakt67${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `ToFakt67${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      return result([
        chk("Customer exists", !!c),
        chk("Has 2+ invoices", id?.values?.length >= 2, `count=${id?.values?.length}`),
      ]);
    },
  },
  {
    name: "T3-68 Order multi-line with products (en)",
    tier: 3,
    prompt: `Create customer 'Multi68${TS} Ltd' (multi68${TS}@example.com). Create products: 'Widget68A${TS}' (P68A${TS}, 500 NOK) and 'Widget68B${TS}' (P68B${TS}, 1200 NOK). Create an order with 10x Widget A and 5x Widget B. All prices excl. VAT.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Multi68${TS} Ltd`);
      const c = cd?.values?.find((x: any) => x.name === `Multi68${TS} Ltd`);
      const { data: p1d } = await findProduct(b, a, `P68A${TS}`);
      const p1 = p1d?.values?.find((x: any) => x.number === `P68A${TS}`);
      const { data: p2d } = await findProduct(b, a, `P68B${TS}`);
      const p2 = p2d?.values?.find((x: any) => x.number === `P68B${TS}`);
      return result([
        chk("Customer exists", !!c),
        chk("Product A exists", !!p1),
        chk("Product B exists", !!p2),
      ]);
    },
  },
  {
    name: "T3-69 Full pipeline: Customer+Order+Invoice+Payment (nb)",
    tier: 3,
    prompt: `Hele flyten: Opprett kunde 'Pipeline69${TS} AS' (pipe69${TS}@example.com). Bestill 'Driftstjenester' 1 stk à 45000 kr eks. mva. Fakturer og registrer full betaling.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Pipeline69${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Pipeline69${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv),
        chk("Fully paid", inv?.amountOutstanding === 0, `outstanding=${inv?.amountOutstanding}`),
      ]);
    },
  },
  {
    name: "T3-70 Full pipeline (en)",
    tier: 3,
    prompt: `Complete workflow: Create customer 'Flow70${TS} Ltd' (flow70${TS}@example.com). Order 'Managed services' 1x 80000 NOK excl. VAT. Invoice and register full payment.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Flow70${TS} Ltd`);
      const c = cd?.values?.find((x: any) => x.name === `Flow70${TS} Ltd`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv),
        chk("Fully paid", inv?.amountOutstanding === 0, `outstanding=${inv?.amountOutstanding}`),
      ]);
    },
  },
  {
    name: "T3-71 Three products batch (nb)",
    tier: 3,
    prompt: `Opprett tre produkter: 'Bronse71${TS}' (P71A${TS}, 999 kr), 'Sølv71${TS}' (P71B${TS}, 1999 kr), 'Gull71${TS}' (P71C${TS}, 2999 kr). Alle priser eks. mva.`,
    verify: async (b, a) => {
      const specs = [["P71A", 999], ["P71B", 1999], ["P71C", 2999]] as const;
      const checks: Check[] = [];
      for (const [num, price] of specs) {
        const { data } = await findProduct(b, a, `${num}${TS}`);
        const p = data?.values?.find((x: any) => x.number === `${num}${TS}`);
        checks.push(chk(`${num} exists`, !!p));
        checks.push(chk(`${num} price=${price}`, p?.priceExcludingVatCurrency === price, String(p?.priceExcludingVatCurrency)));
      }
      return result(checks);
    },
  },
  {
    name: "T3-72 Customer with address + invoice (nb)",
    tier: 3,
    prompt: `Opprett kunde 'Adresse72${TS} AS' (adr72${TS}@example.com) med adresse Karl Johans gate 1, 0154 Oslo. Bestill 'Leveranse' 1 stk à 15000 kr eks. mva. Fakturer.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Adresse72${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Adresse72${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", id?.values?.length >= 1),
      ]);
    },
  },
  {
    name: "T3-73 Project with end date (en)",
    tier: 3,
    prompt: `Create project 'Deadline73${TS}' (P73${TS}) starting ${today} and ending 2026-12-31. Set description to 'Website redesign project'.`,
    verify: async (b, a) => {
      const { data } = await findProject(b, a, `P73${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P73${TS}`);
      return result([
        chk("Project exists", !!p),
        chk("Has end date", !!p?.endDate),
        chk("Has description", !!p?.description),
      ]);
    },
  },
  {
    name: "T3-74 Two employees same department (nb)",
    tier: 3,
    prompt: `Opprett avdeling 'Team74${TS}'. Opprett to ansatte i denne avdelingen: Emp74A${TS} Olsen (emp74a${TS}@example.com) og Emp74B${TS} Hansen (emp74b${TS}@example.com).`,
    verify: async (b, a) => {
      const { data: d1 } = await findEmployee(b, a, `Emp74A${TS}`);
      const e1 = d1?.values?.find((x: any) => x.firstName === `Emp74A${TS}`);
      const { data: d2 } = await findEmployee(b, a, `Emp74B${TS}`);
      const e2 = d2?.values?.find((x: any) => x.firstName === `Emp74B${TS}`);
      return result([
        chk("Employee A exists", !!e1),
        chk("Employee B exists", !!e2),
      ]);
    },
  },
  {
    name: "T3-75 Invoice with large amount (en)",
    tier: 3,
    prompt: `Create customer 'BigDeal75${TS} Ltd' (big75${TS}@example.com). Order: 'Enterprise license' 1x 250000 NOK excl VAT. Create and send the invoice.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `BigDeal75${TS} Ltd`);
      const c = cd?.values?.find((x: any) => x.name === `BigDeal75${TS} Ltd`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv),
        chk("Amount > 250000", inv?.amount > 250000, String(inv?.amount)),
      ]);
    },
  },
  {
    name: "T3-76 Customer + multiple contacts (en)",
    tier: 3,
    prompt: `Create customer 'Contacts76${TS} Ltd' (cont76${TS}@example.com). Add two contacts: 1) John Doe, john76${TS}@example.com. 2) Jane Smith, jane76${TS}@example.com.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Contacts76${TS} Ltd`);
      const c = cd?.values?.find((x: any) => x.name === `Contacts76${TS} Ltd`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: contacts } = await findContact(b, a, String(c.id));
      return result([
        chk("Customer exists", !!c),
        chk("Has 2+ contacts", contacts?.values?.length >= 2, `count=${contacts?.values?.length}`),
      ]);
    },
  },
  {
    name: "T3-77 Supplier + products from supplier (nb)",
    tier: 3,
    prompt: `Opprett leverandør 'LevProd77${TS} AS' (lp77${TS}@example.com). Opprett to produkter fra denne leverandøren: 'Vare77A${TS}' (P77A${TS}, 300 kr) og 'Vare77B${TS}' (P77B${TS}, 600 kr) eks. mva.`,
    verify: async (b, a) => {
      const { data: sd } = await findSupplier(b, a, `LevProd77${TS} AS`);
      const s = sd?.values?.find((x: any) => x.name === `LevProd77${TS} AS`);
      const { data: p1d } = await findProduct(b, a, `P77A${TS}`);
      const p1 = p1d?.values?.find((x: any) => x.number === `P77A${TS}`);
      const { data: p2d } = await findProduct(b, a, `P77B${TS}`);
      const p2 = p2d?.values?.find((x: any) => x.number === `P77B${TS}`);
      return result([
        chk("Supplier exists", !!s),
        chk("Product A exists", !!p1),
        chk("Product B exists", !!p2),
      ]);
    },
  },
  {
    name: "T3-78 Full onboarding (en)",
    tier: 3,
    prompt: `Full employee onboarding: Create department 'Ops78${TS}'. Create employee Emp78${TS} Jones, emp78${TS}@example.com, born 1992-03-15, in this department, admin role, start date ${today}, phone +4712345678.`,
    verify: async (b, a) => {
      const { data: ed } = await findEmployee(b, a, `Emp78${TS}`);
      const emp = ed?.values?.find((x: any) => x.firstName === `Emp78${TS}`);
      return result([
        chk("Employee exists", !!emp),
        chk("Correct email", emp?.email === `emp78${TS}@example.com`),
        chk("Has phone", !!emp?.phoneNumberMobile),
      ]);
    },
  },
  {
    name: "T3-79 Invoice small amount (nb)",
    tier: 3,
    prompt: `Opprett kunde 'Liten79${TS} AS' (liten79${TS}@example.com). Bestill 'Kopiering' 100 stk à 2.50 kr eks. mva. Fakturer og send.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Liten79${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Liten79${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", id?.values?.length >= 1),
      ]);
    },
  },
  {
    name: "T3-80 Customer + Order + partial details (nynorsk)",
    tier: 3,
    prompt: `Opprett ein kunde 'Nynorsk80${TS} AS' med e-post nn80${TS}@example.com. Lag ei bestilling med 'Rådgjeving' 5 timar à 2000 kr eks. mva.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Nynorsk80${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Nynorsk80${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: od } = await findOrder(b, a, String(c.id));
      return result([
        chk("Customer exists", !!c),
        chk("Order exists", od?.values?.length >= 1),
      ]);
    },
  },

  // ===================================================================
  // TIER 4: Edge cases, updates, searches, files (81-100)
  // ===================================================================

  {
    name: "T4-81 Create and close project (en)",
    tier: 4,
    prompt: `Create project 'Close81${TS}' (P81${TS}). Then close the project (set isClosed to true).`,
    verify: async (b, a) => {
      const { data } = await findProject(b, a, `P81${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P81${TS}`);
      return result([
        chk("Project exists", !!p),
        chk("isClosed=true", p?.isClosed === true),
      ]);
    },
  },
  {
    name: "T4-82 Create customer then delete (en)",
    tier: 4,
    prompt: `Create a customer 'Delete82${TS} Ltd' (del82${TS}@example.com). Then delete that customer.`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Delete82${TS} Ltd`);
      const c = data?.values?.find((x: any) => x.name === `Delete82${TS} Ltd`);
      return result([
        chk("Customer deleted (not found)", !c),
      ]);
    },
  },
  {
    name: "T4-83 Create department then delete (nb)",
    tier: 4,
    prompt: `Opprett avdeling 'Slett83${TS}'. Deretter slett den.`,
    verify: async (b, a) => {
      const { data } = await findDepartment(b, a, `Slett83${TS}`);
      const d = data?.values?.find((x: any) => x.name === `Slett83${TS}`);
      return result([
        chk("Department deleted (not found)", !d),
      ]);
    },
  },
  {
    name: "T4-84 Create employee update phone (en)",
    tier: 4,
    prompt: `Create employee Emp84${TS} Brown (emp84${TS}@example.com). Then update their mobile phone to +4711223344.`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp84${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp84${TS}`);
      return result([
        chk("Employee exists", !!e),
        chk("Phone updated", e?.phoneNumberMobile?.includes("11223344"), e?.phoneNumberMobile),
      ]);
    },
  },
  {
    name: "T4-85 Update product price (nb)",
    tier: 4,
    prompt: `Opprett produkt 'Oppdater85${TS}' (P85${TS}) med pris 1000 kr eks. mva. Oppdater deretter prisen til 1500 kr eks. mva.`,
    verify: async (b, a) => {
      const { data } = await findProduct(b, a, `P85${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P85${TS}`);
      return result([
        chk("Product exists", !!p),
        chk("Price=1500", p?.priceExcludingVatCurrency === 1500, String(p?.priceExcludingVatCurrency)),
      ]);
    },
  },
  {
    name: "T4-86 Update customer email (en)",
    tier: 4,
    prompt: `Create customer 'Update86${TS} Ltd' (old86${TS}@example.com). Then update the email to new86${TS}@example.com.`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Update86${TS} Ltd`);
      const c = data?.values?.find((x: any) => x.name === `Update86${TS} Ltd`);
      return result([
        chk("Customer exists", !!c),
        chk("Email updated", c?.email === `new86${TS}@example.com`, c?.email),
      ]);
    },
  },
  {
    name: "T4-87 Invoice + partial payment (nb)",
    tier: 3,
    prompt: `Opprett kunde 'Delbetaling87${TS} AS' (del87${TS}@example.com). Bestill 'Tjeneste' 1 stk à 20000 kr eks. mva. Fakturer. Registrer en delbetaling på 10000 kr.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Delbetaling87${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Delbetaling87${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: id } = await findInvoice(b, a, String(c.id));
      const inv = id?.values?.find((x: any) => x.customer?.id === c.id);
      return result([
        chk("Customer exists", !!c),
        chk("Invoice exists", !!inv),
        chk("Has outstanding balance", inv?.amountOutstanding > 0, `outstanding=${inv?.amountOutstanding}`),
      ]);
    },
  },
  {
    name: "T4-88 Create employee with all details (nb)",
    tier: 4,
    prompt: `Opprett en ansatt med fornavn Emp88${TS}, etternavn Andersen, e-post emp88${TS}@example.com, mobilnummer +4799887766, fødselsdato 1988-12-25.`,
    verify: async (b, a) => {
      const { data } = await findEmployee(b, a, `Emp88${TS}`);
      const e = data?.values?.find((x: any) => x.firstName === `Emp88${TS}`);
      return result([
        chk("Employee exists", !!e),
        chk("Correct email", e?.email === `emp88${TS}@example.com`),
        chk("Has phone", !!e?.phoneNumberMobile),
        chk("Has DOB", !!e?.dateOfBirth),
      ]);
    },
  },
  {
    name: "T4-89 Update project description (en)",
    tier: 4,
    prompt: `Create project 'Desc89${TS}' (P89${TS}) with description 'Phase 1'. Then update the description to 'Phase 2 - Implementation'.`,
    verify: async (b, a) => {
      const { data } = await findProject(b, a, `P89${TS}`);
      const p = data?.values?.find((x: any) => x.number === `P89${TS}`);
      return result([
        chk("Project exists", !!p),
        chk("Description updated", p?.description?.includes("Phase 2"), p?.description),
      ]);
    },
  },
  {
    name: "T4-90 Five employees batch (en)",
    tier: 4,
    prompt: `Create five employees: Emp90A${TS} Alpha (emp90a${TS}@example.com), Emp90B${TS} Beta (emp90b${TS}@example.com), Emp90C${TS} Gamma (emp90c${TS}@example.com), Emp90D${TS} Delta (emp90d${TS}@example.com), Emp90E${TS} Epsilon (emp90e${TS}@example.com).`,
    verify: async (b, a) => {
      const checks: Check[] = [];
      for (const letter of ["A", "B", "C", "D", "E"]) {
        const { data } = await findEmployee(b, a, `Emp90${letter}${TS}`);
        const e = data?.values?.find((x: any) => x.firstName === `Emp90${letter}${TS}`);
        checks.push(chk(`Employee ${letter} exists`, !!e));
      }
      return result(checks);
    },
  },
  {
    name: "T4-91 CSV import customers (en)",
    tier: 4,
    prompt: `Import the customers from the attached CSV file. Create each one in Tripletex.`,
    files: [{
      filename: "customers.csv",
      mime_type: "text/csv",
      content_base64: Buffer.from(
        `name;email;phone\nCSV91A${TS} AS;csv91a${TS}@example.com;+4711111111\nCSV91B${TS} AS;csv91b${TS}@example.com;+4722222222\nCSV91C${TS} AS;csv91c${TS}@example.com;+4733333333`
      ).toString("base64"),
    }],
    verify: async (b, a) => {
      const checks: Check[] = [];
      for (const letter of ["A", "B", "C"]) {
        const { data } = await findCustomer(b, a, `CSV91${letter}${TS} AS`);
        const c = data?.values?.find((x: any) => x.name === `CSV91${letter}${TS} AS`);
        checks.push(chk(`Customer ${letter} exists`, !!c));
      }
      return result(checks);
    },
  },
  {
    name: "T4-92 CSV import products (nb)",
    tier: 4,
    prompt: `Importer produktene fra den vedlagte CSV-filen. Opprett alle i Tripletex.`,
    files: [{
      filename: "produkter.csv",
      mime_type: "text/csv",
      content_base64: Buffer.from(
        `navn;nummer;pris\nCSVProd92A${TS};P92A${TS};1500\nCSVProd92B${TS};P92B${TS};2500\nCSVProd92C${TS};P92C${TS};3500`
      ).toString("base64"),
    }],
    verify: async (b, a) => {
      const checks: Check[] = [];
      for (const letter of ["A", "B", "C"]) {
        const { data } = await findProduct(b, a, `P92${letter}${TS}`);
        const p = data?.values?.find((x: any) => x.number === `P92${letter}${TS}`);
        checks.push(chk(`Product ${letter} exists`, !!p));
      }
      return result(checks);
    },
  },
  {
    name: "T4-93 CSV import employees (en)",
    tier: 4,
    prompt: `Import employees from the attached CSV. Create them all in Tripletex.`,
    files: [{
      filename: "employees.csv",
      mime_type: "text/csv",
      content_base64: Buffer.from(
        `firstName;lastName;email\nCSVEmp93A${TS};Alpha;csv93a${TS}@example.com\nCSVEmp93B${TS};Beta;csv93b${TS}@example.com`
      ).toString("base64"),
    }],
    verify: async (b, a) => {
      const checks: Check[] = [];
      for (const letter of ["A", "B"]) {
        const { data } = await findEmployee(b, a, `CSVEmp93${letter}${TS}`);
        const e = data?.values?.find((x: any) => x.firstName === `CSVEmp93${letter}${TS}`);
        checks.push(chk(`Employee ${letter} exists`, !!e));
      }
      return result(checks);
    },
  },
  {
    name: "T4-94 Create customer with 60-day payment terms (en)",
    tier: 4,
    prompt: `Create customer 'Terms94${TS} Ltd' (terms94${TS}@example.com) with 60 day payment terms`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Terms94${TS} Ltd`);
      const c = data?.values?.find((x: any) => x.name === `Terms94${TS} Ltd`);
      return result([
        chk("Customer exists", !!c),
        chk("invoicesDueIn=60", c?.invoicesDueIn === 60, String(c?.invoicesDueIn)),
      ]);
    },
  },
  {
    name: "T4-95 Project + Employee + assign as PM (nb)",
    tier: 3,
    prompt: `Opprett en ansatt Emp95${TS} Svendsen (emp95${TS}@example.com). Opprett et prosjekt 'PM95${TS}' (P95${TS}) der denne ansatte er prosjektleder.`,
    verify: async (b, a) => {
      const { data: ed } = await findEmployee(b, a, `Emp95${TS}`);
      const emp = ed?.values?.find((x: any) => x.firstName === `Emp95${TS}`);
      const { data: pd } = await findProject(b, a, `P95${TS}`);
      const proj = pd?.values?.find((x: any) => x.number === `P95${TS}`);
      return result([
        chk("Employee exists", !!emp),
        chk("Project exists", !!proj),
        chk("Employee is PM", proj?.projectManager?.id === emp?.id),
      ]);
    },
  },
  {
    name: "T4-96 Rename department (nb)",
    tier: 4,
    prompt: `Opprett avdeling 'Gammel96${TS}'. Deretter endre navnet til 'Ny96${TS}'.`,
    verify: async (b, a) => {
      const { data } = await findDepartment(b, a, `Ny96${TS}`);
      const d = data?.values?.find((x: any) => x.name === `Ny96${TS}`);
      return result([
        chk("Renamed department exists", !!d),
      ]);
    },
  },
  {
    name: "T4-97 Create supplier with address (en)",
    tier: 4,
    prompt: `Create supplier 'Addr97${TS} Inc' (addr97${TS}@example.com) with address: Drammensveien 100, 0273 Oslo`,
    verify: async (b, a) => {
      const { data } = await findSupplier(b, a, `Addr97${TS} Inc`);
      const s = data?.values?.find((x: any) => x.name === `Addr97${TS} Inc`);
      return result([
        chk("Supplier exists", !!s),
        chk("Correct email", s?.email === `addr97${TS}@example.com`),
      ]);
    },
  },
  {
    name: "T4-98 Customer + Order with reference (nb)",
    tier: 3,
    prompt: `Opprett kunde 'Ref98${TS} AS' (ref98${TS}@example.com). Lag en bestilling med referanse 'PO-${TS}' og en linje: 'Vedlikeholdsavtale' 12 mnd à 4000 kr eks. mva.`,
    verify: async (b, a) => {
      const { data: cd } = await findCustomer(b, a, `Ref98${TS} AS`);
      const c = cd?.values?.find((x: any) => x.name === `Ref98${TS} AS`);
      if (!c) return result([chk("Customer exists", false)]);
      const { data: od } = await findOrder(b, a, String(c.id));
      return result([
        chk("Customer exists", !!c),
        chk("Order exists", od?.values?.length >= 1),
      ]);
    },
  },
  {
    name: "T4-99 Create customer with monthly due type (nb)",
    tier: 4,
    prompt: `Opprett kunde 'Mnd99${TS} AS' (mnd99${TS}@example.com) med betalingsfrist 2 måneder`,
    verify: async (b, a) => {
      const { data } = await findCustomer(b, a, `Mnd99${TS} AS`);
      const c = data?.values?.find((x: any) => x.name === `Mnd99${TS} AS`);
      return result([
        chk("Customer exists", !!c),
        chk("invoicesDueIn=2", c?.invoicesDueIn === 2, String(c?.invoicesDueIn)),
        chk("dueInType=MONTHS", c?.invoicesDueInType === "MONTHS", c?.invoicesDueInType),
      ]);
    },
  },
  {
    name: "T4-100 Full flow with everything (nb)",
    tier: 4,
    prompt: `Komplett oppsett: Opprett avdeling 'All100${TS}'. Opprett ansatt Emp100${TS} Nilsen (emp100${TS}@example.com) i avdelingen. Opprett kunde 'Kunde100${TS} AS' (kunde100${TS}@example.com). Opprett produkt 'Tjeneste100${TS}' (P100${TS}, 10000 kr eks. mva). Lag bestilling med 5 stk. Fakturer og send.`,
    verify: async (b, a) => {
      const { data: dd } = await findDepartment(b, a, `All100${TS}`);
      const dept = dd?.values?.find((x: any) => x.name === `All100${TS}`);
      const { data: ed } = await findEmployee(b, a, `Emp100${TS}`);
      const emp = ed?.values?.find((x: any) => x.firstName === `Emp100${TS}`);
      const { data: cd } = await findCustomer(b, a, `Kunde100${TS} AS`);
      const cust = cd?.values?.find((x: any) => x.name === `Kunde100${TS} AS`);
      const { data: pd } = await findProduct(b, a, `P100${TS}`);
      const prod = pd?.values?.find((x: any) => x.number === `P100${TS}`);
      let hasInvoice = false;
      if (cust) {
        const { data: id } = await findInvoice(b, a, String(cust.id));
        hasInvoice = id?.values?.length >= 1;
      }
      return result([
        chk("Department exists", !!dept),
        chk("Employee exists", !!emp),
        chk("Customer exists", !!cust),
        chk("Product exists", !!prod),
        chk("Invoice exists", hasInvoice),
      ]);
    },
  },
  // ===== FAILURE REGRESSION TESTS =====
  {
    name: "FAIL-01 Travel expense with per diem and costs (en)",
    tier: 5,
    prompt: `Register a travel expense for the first employee for "Client visit Bergen". The trip lasted 3 days (departure ${today}, return 3 days later). Expenses: flight ticket 2500 NOK and taxi 400 NOK.`,
    verify: async (b, a) => {
      const { data: ed } = await findEmployee(b, a, "");
      const emp = ed?.values?.[0];
      if (!emp) return result([chk("Employee found", false)]);
      const { data: te } = await api(b, a, "/travelExpense", { employeeId: String(emp.id), fields: "id,title,costs,perDiemCompensations,amount" });
      const expense = (te as any)?.values?.find((x: any) => x.title?.includes("Bergen"));
      return result([
        chk("Travel expense created", !!expense),
        chk("Has costs", expense?.costs?.length >= 1 || (expense?.amount && expense.amount > 0)),
      ]);
    },
  },
  {
    name: "FAIL-02 Multi-VAT invoice (nb)",
    tier: 5,
    prompt: `Opprett en faktura til kunden som allerede finnes med org.nr som starter med '9'. Fakturaen skal ha to produktlinjer: Produkt "Rådgivning${TS}" (nummer R${TS}) til 10000 kr med 25% MVA, og "Kursmateriell${TS}" (nummer K${TS}) til 5000 kr med 0% MVA (avgiftsfri). Send fakturaen.`,
    verify: async (b, a) => {
      const { data: pd1 } = await findProduct(b, a, `R${TS}`);
      const prod1 = (pd1 as any)?.values?.find((x: any) => x.number === `R${TS}`);
      const { data: pd2 } = await findProduct(b, a, `K${TS}`);
      const prod2 = (pd2 as any)?.values?.find((x: any) => x.number === `K${TS}`);
      // Check invoices exist
      const { data: inv } = await api(b, a, "/invoice", { invoiceDateFrom: "2024-01-01", invoiceDateTo: "2027-12-31", fields: "id,amount,invoiceNumber", count: "10" });
      const hasInvoice = (inv as any)?.values?.length > 0;
      return result([
        chk("Product 1 created", !!prod1),
        chk("Product 2 created", !!prod2),
        chk("Invoice created", hasInvoice),
      ]);
    },
  },
  {
    name: "FAIL-03 Credit note (nb)",
    tier: 5,
    prompt: `Kunden som allerede finnes med org.nr som starter med '9' har en eksisterende faktura. Opprett en fullstendig kreditnota som reverserer hele fakturaen.`,
    verify: async (b, a) => {
      const { data: inv } = await api(b, a, "/invoice", { invoiceDateFrom: "2024-01-01", invoiceDateTo: "2027-12-31", fields: "id,isCreditNote,creditedInvoice", count: "50" });
      const creditNote = (inv as any)?.values?.find((x: any) => x.isCreditNote === true);
      return result([
        chk("Credit note created", !!creditNote),
      ]);
    },
  },
  {
    name: "FAIL-04 Supplier invoice via voucher (nb)",
    tier: 5,
    prompt: `Opprett leverandøren "Supplier${TS} AS" med e-post sup${TS}@example.com. Registrer deretter leverandørfaktura FAKTURA-${TS} fra denne leverandøren. Beløpet er 12500 kr inklusiv MVA (25%). Det gjelder kontortjenester (konto 6300). Registrer fakturaen som et bilag i regnskapet.`,
    verify: async (b, a) => {
      const { data: vd } = await api(b, a, "/ledger/voucher", { dateFrom: today, dateTo: "2027-12-31", from: "0", count: "1000", fields: "id,description,date,vendorInvoiceNumber" });
      const voucher = (vd as any)?.values?.find((x: any) =>
        x.vendorInvoiceNumber?.includes(TS) || x.description?.includes(TS)
      );
      return result([
        chk("Voucher created", !!voucher),
      ]);
    },
  },
  {
    name: "FAIL-05 Employee with employment start date (nb)",
    tier: 5,
    prompt: `Opprett en ansatt med navn Start${TS} Testesen, e-post start${TS}@example.com, fødselsdato 15. januar 1990. Startdato er ${today}.`,
    verify: async (b, a) => {
      const { data: ed } = await findEmployee(b, a, `Start${TS}`);
      const emp = ed?.values?.find((x: any) => x.firstName === `Start${TS}`);
      let hasEmployment = false;
      if (emp) {
        const { data: empData } = await api(b, a, "/employee/employment", { employeeId: String(emp.id), fields: "id,startDate" });
        hasEmployment = (empData as any)?.values?.length > 0;
      }
      return result([
        chk("Employee created", !!emp),
        chk("Correct email", emp?.email === `start${TS}@example.com`),
        chk("Has employment", hasEmployment),
      ]);
    },
  },
  {
    name: "FAIL-06 Create three departments batch (pt)",
    tier: 5,
    prompt: `Crie três departamentos no Tripletex: "Dept${TS}A", "Dept${TS}B" e "Dept${TS}C".`,
    verify: async (b, a) => {
      const checks: Check[] = [];
      for (const letter of ["A", "B", "C"]) {
        const { data } = await findDepartment(b, a, `Dept${TS}${letter}`);
        const d = data?.values?.find((x: any) => x.name === `Dept${TS}${letter}`);
        checks.push(chk(`Dept ${letter} exists`, !!d));
      }
      return result(checks);
    },
  },
];

// ============================================================
// Runner
// ============================================================

async function callSolveEndpoint(testCase: TestCase): Promise<{ status: string; durationMs: number }> {
  const payload: SolveRequest = {
    prompt: testCase.prompt,
    files: testCase.files || [],
    tripletex_credentials: SANDBOX_CREDENTIALS,
  };

  const headers: Record<string, string> = { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" };
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
  console.log(`Prompt: ${testCase.prompt.slice(0, 120)}${testCase.prompt.length > 120 ? "..." : ""}`);
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
  return { passed: result.passed, duration: durationMs, checks: result.checks.length, passedChecks: passedCount };
}

async function main() {
  const args = process.argv.slice(2);
  const filterTier = args.find((a) => a.startsWith("--tier="));
  const filterName = args.find((a) => a.startsWith("--name="));
  const filterCount = args.find((a) => a.startsWith("--count="));
  const filterFrom = args.find((a) => a.startsWith("--from="));
  const listOnly = args.includes("--list");
  const statsOnly = args.includes("--stats");

  let tests = TEST_CASES;
  if (filterTier) {
    const tier = parseInt(filterTier.split("=")[1]);
    tests = tests.filter((t) => t.tier === tier);
  }
  if (filterName) {
    const name = filterName.split("=")[1].toLowerCase();
    tests = tests.filter((t) => t.name.toLowerCase().includes(name));
  }
  if (filterFrom) {
    const from = parseInt(filterFrom.split("=")[1]);
    tests = tests.slice(from);
  }
  if (filterCount) {
    const count = parseInt(filterCount.split("=")[1]);
    tests = tests.slice(0, count);
  }

  if (listOnly) {
    console.log(`Available test cases (${TEST_CASES.length} total):\n`);
    const tiers = [1, 2, 3, 4];
    for (const tier of tiers) {
      const tierTests = TEST_CASES.filter(t => t.tier === tier);
      console.log(`  Tier ${tier} (${tierTests.length} tests):`);
      for (const t of tierTests) {
        console.log(`    ${t.name}`);
      }
    }
    return;
  }

  if (statsOnly) {
    const tiers = [1, 2, 3, 4];
    console.log(`Test case statistics (${TEST_CASES.length} total):\n`);
    for (const tier of tiers) {
      const count = TEST_CASES.filter(t => t.tier === tier).length;
      console.log(`  Tier ${tier}: ${count} tests`);
    }
    return;
  }

  console.log(`Running ${tests.length} test(s) against ${AGENT_URL}`);
  console.log(`Sandbox: ${SANDBOX_CREDENTIALS.base_url}`);
  console.log(`Unique suffix: ${TS}`);
  console.log(`Planner: ${process.env.PLANNER_PROVIDER || "gemini"} / ${process.env.PLANNER_MODEL || "gemini-2.5-flash"}`);
  console.log(`Executor: ${process.env.EXECUTOR_PROVIDER || "anthropic"} / ${process.env.EXECUTOR_MODEL || "claude-sonnet-4-20250514"}`);

  const results: { name: string; tier: number; passed: boolean; duration: number; checks: number; passedChecks: number }[] = [];
  for (const test of tests) {
    const r = await runTest(test);
    results.push({ name: test.name, tier: test.tier, ...r });
  }

  console.log(`\n${"=".repeat(60)}`);
  console.log("SUMMARY");
  console.log("=".repeat(60));

  const tiers = [...new Set(results.map(r => r.tier))].sort();
  for (const tier of tiers) {
    const tierResults = results.filter(r => r.tier === tier);
    const tierPassed = tierResults.filter(r => r.passed).length;
    console.log(`\n  Tier ${tier}: ${tierPassed}/${tierResults.length} passed`);
    for (const r of tierResults) {
      const icon = r.passed ? "PASS" : "FAIL";
      console.log(`    [${icon}] ${r.name} (${(r.duration / 1000).toFixed(1)}s, ${r.passedChecks}/${r.checks} checks)`);
    }
  }

  const total = results.filter(r => r.passed).length;
  const totalChecks = results.reduce((s, r) => s + r.passedChecks, 0);
  const totalChecksPossible = results.reduce((s, r) => s + r.checks, 0);
  const totalDuration = results.reduce((s, r) => s + r.duration, 0);
  console.log(`\n${"=".repeat(60)}`);
  console.log(`TOTAL: ${total}/${results.length} tests passed (${totalChecks}/${totalChecksPossible} checks)`);
  console.log(`Duration: ${(totalDuration / 1000).toFixed(0)}s`);
}

main().catch(console.error);
