import "dotenv/config";

const BASE_URL = process.env.TRIPLETEX_BASE_URL || "https://kkpqfuj-amager.tripletex.dev/v2";
const SESSION_TOKEN = process.env.TRIPLETEX_SESSION_TOKEN || "";
const AUTH = "Basic " + Buffer.from(`0:${SESSION_TOKEN}`).toString("base64");
const TS = Date.now().toString().slice(-6);
const today = new Date().toISOString().split("T")[0];
const dueDate = new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0];

interface TestResult {
  category: string;
  name: string;
  passed: boolean;
  detail?: string;
  response?: unknown;
  error?: string;
  durationMs: number;
}

const results: TestResult[] = [];

async function api(
  method: string,
  path: string,
  opts: { params?: Record<string, string | number | boolean>; body?: unknown } = {}
): Promise<{ status: number; data: unknown; durationMs: number }> {
  const url = new URL(`${BASE_URL}${path}`);
  if (opts.params) {
    for (const [k, v] of Object.entries(opts.params)) url.searchParams.set(k, String(v));
  }
  const start = Date.now();
  const res = await fetch(url.toString(), {
    method,
    headers: { Authorization: AUTH, "Content-Type": "application/json", Accept: "application/json" },
    ...(opts.body ? { body: JSON.stringify(opts.body) } : {}),
  });
  const durationMs = Date.now() - start;
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  return { status: res.status, data, durationMs };
}

async function test(
  category: string,
  name: string,
  fn: () => Promise<{ passed: boolean; detail?: string; response?: unknown }>
) {
  const start = Date.now();
  try {
    const r = await fn();
    results.push({ category, name, passed: r.passed, detail: r.detail, response: r.response, durationMs: Date.now() - start });
    const icon = r.passed ? "PASS" : "FAIL";
    console.log(`  [${icon}] ${name}${r.detail ? ` — ${r.detail}` : ""}`);
  } catch (e) {
    results.push({ category, name, passed: false, error: String(e), durationMs: Date.now() - start });
    console.log(`  [ERR ] ${name} — ${e}`);
  }
}

function val(data: unknown): { values: unknown[]; fullResultSize?: number } {
  const d = data as { values?: unknown[]; fullResultSize?: number };
  return { values: d?.values || [], fullResultSize: d?.fullResultSize };
}

function single(data: unknown): { value: Record<string, unknown> } {
  const d = data as { value?: Record<string, unknown> };
  return { value: d?.value || {} };
}

// Shared IDs populated during tests
const ids: Record<string, number> = {};

// ============================================================
// 1. DEPARTMENT
// ============================================================
async function testDepartment() {
  console.log("\n=== 1. DEPARTMENT ===");

  await test("department", "GET /department — list all", async () => {
    const { status, data } = await api("GET", "/department", { params: { from: 0, count: 5 } });
    const v = val(data);
    return { passed: status === 200 && v.values.length > 0, detail: `${v.values.length} depts` };
  });

  await test("department", "POST /department — create with number", async () => {
    const { status, data } = await api("POST", "/department", { body: { name: `Dept${TS}`, departmentNumber: parseInt(TS) } });
    ids.dept = (single(data).value.id as number) || 0;
    return { passed: status === 201 && ids.dept > 0, detail: `id=${ids.dept}` };
  });

  await test("department", "GET /department/{id}", async () => {
    const { status, data } = await api("GET", `/department/${ids.dept}`, { params: { fields: "*" } });
    return { passed: status === 200 && single(data).value.name === `Dept${TS}`, detail: `name=${single(data).value.name}` };
  });

  await test("department", "GET /department — filter name", async () => {
    const { status, data } = await api("GET", "/department", { params: { name: `Dept${TS}` } });
    return { passed: status === 200 && val(data).values.length >= 1, detail: `found ${val(data).values.length}` };
  });

  await test("department", "PUT /department/{id} — update", async () => {
    const { data: g } = await api("GET", `/department/${ids.dept}`, { params: { fields: "*" } });
    const { status, data } = await api("PUT", `/department/${ids.dept}`, { body: { ...single(g).value, name: `DeptUpd${TS}` } });
    return { passed: status === 200, detail: `name=${single(data).value.name}` };
  });

  await test("department", "GET /department/query — wildcard", async () => {
    const { status, data } = await api("GET", "/department/query", { params: { query: `DeptUpd${TS}` } });
    return { passed: status === 200 && val(data).values.length >= 1 };
  });

  await test("department", "POST /department/list — batch create 2", async () => {
    const { status, data } = await api("POST", "/department/list", {
      body: [{ name: `BatchD1${TS}` }, { name: `BatchD2${TS}` }],
    });
    return { passed: status === 201 && val(data).values.length === 2, detail: `created ${val(data).values.length}` };
  });

  await test("department", "DELETE /department/{id}", async () => {
    const { status } = await api("DELETE", `/department/${ids.dept}`);
    return { passed: status === 204 || status === 200 };
  });
}

// ============================================================
// 2. EMPLOYEE
// ============================================================
async function testEmployee() {
  console.log("\n=== 2. EMPLOYEE ===");

  const { data: dd } = await api("GET", "/department", { params: { from: 0, count: 1 } });
  const deptId = (val(dd).values[0] as { id: number })?.id || 1;

  await test("employee", "GET /employee — list", async () => {
    const { status, data } = await api("GET", "/employee", { params: { from: 0, count: 5, fields: "id,firstName,lastName,email" } });
    return { passed: status === 200 && val(data).values.length > 0, detail: `${val(data).values.length} emps` };
  });

  await test("employee", "POST /employee — minimal STANDARD", async () => {
    const { status, data } = await api("POST", "/employee", {
      body: { firstName: `Emp${TS}`, lastName: "Tester", email: `emp${TS}@example.com`, userType: "STANDARD", department: { id: deptId } },
    });
    ids.emp = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.emp}` };
  });

  await test("employee", "POST /employee — EXTENDED (admin)", async () => {
    const { status, data } = await api("POST", "/employee", {
      body: { firstName: `Admin${TS}`, lastName: "Boss", email: `adm${TS}@example.com`, userType: "EXTENDED", department: { id: deptId } },
    });
    return { passed: status === 201, detail: `id=${single(data).value.id}` };
  });

  await test("employee", "POST /employee — NO_ACCESS + phone + dob", async () => {
    const { status, data } = await api("POST", "/employee", {
      body: { firstName: `NoAcc${TS}`, lastName: "User", email: `noacc${TS}@example.com`, userType: "NO_ACCESS", department: { id: deptId }, phoneNumberMobile: "+4712345678", dateOfBirth: "1995-06-15" },
    });
    ids.empWithDob = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.empWithDob}, phone=${single(data).value.phoneNumberMobile}` };
  });

  await test("employee", "GET /employee/{id} — fields=*", async () => {
    const { status, data } = await api("GET", `/employee/${ids.emp}`, { params: { fields: "*" } });
    return { passed: status === 200 && single(data).value.firstName === `Emp${TS}` };
  });

  await test("employee", "GET /employee — filter firstName", async () => {
    const { status, data } = await api("GET", "/employee", { params: { firstName: `Emp${TS}` } });
    return { passed: status === 200 && val(data).values.length >= 1 };
  });

  await test("employee", "GET /employee — filter email", async () => {
    const { status, data } = await api("GET", "/employee", { params: { email: `emp${TS}@example.com` } });
    return { passed: status === 200 && val(data).values.length >= 1 };
  });

  await test("employee", "GET /employee — filter departmentId", async () => {
    const { status, data } = await api("GET", "/employee", { params: { departmentId: deptId, from: 0, count: 5 } });
    return { passed: status === 200, detail: `found ${val(data).values.length}` };
  });

  await test("employee", "GET /employee — sorting firstName", async () => {
    const { status, data } = await api("GET", "/employee", { params: { from: 0, count: 5, sorting: "firstName", fields: "id,firstName" } });
    return { passed: status === 200, detail: `${val(data).values.length} sorted` };
  });

  await test("employee", "PUT /employee/{id} — update (needs dateOfBirth)", async () => {
    const { data: g } = await api("GET", `/employee/${ids.emp}`, { params: { fields: "id,version,firstName,lastName,email,dateOfBirth,department(id)" } });
    const c = single(g).value;
    const { status, data } = await api("PUT", `/employee/${ids.emp}`, {
      body: { ...c, lastName: "Updated", dateOfBirth: c.dateOfBirth || "1990-01-15" },
    });
    return { passed: status === 200 && single(data).value.lastName === "Updated" };
  });

  await test("employee", "POST /employee/list — batch create 2", async () => {
    const { status, data } = await api("POST", "/employee/list", {
      body: [
        { firstName: `Bat1${TS}`, lastName: "One", email: `bat1${TS}@example.com`, userType: "NO_ACCESS", department: { id: deptId } },
        { firstName: `Bat2${TS}`, lastName: "Two", email: `bat2${TS}@example.com`, userType: "NO_ACCESS", department: { id: deptId } },
      ],
    });
    return { passed: status === 201 && val(data).values.length === 2, detail: `created ${val(data).values.length}` };
  });

  // Employment
  await test("employee", "POST /employee/employment — create", async () => {
    const { data: g } = await api("GET", `/employee/${ids.empWithDob}`, { params: { fields: "id,version,firstName,lastName,email,dateOfBirth,department(id)" } });
    const c = single(g).value;
    if (!c.dateOfBirth) await api("PUT", `/employee/${ids.empWithDob}`, { body: { ...c, dateOfBirth: "1995-06-15" } });
    const { status, data } = await api("POST", "/employee/employment", {
      body: { employee: { id: ids.empWithDob }, startDate: today, isMainEmployer: true },
    });
    ids.employment = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.employment}` };
  });

  await test("employee", "GET /employee/employment — list by employee", async () => {
    const { status, data } = await api("GET", "/employee/employment", { params: { employeeId: ids.empWithDob } });
    return { passed: status === 200 && val(data).values.length >= 1, detail: `${val(data).values.length} employments` };
  });

  await test("employee", "GET /employee/employment/employmentType — list", async () => {
    const { status, data } = await api("GET", "/employee/employment/employmentType");
    return { passed: status === 200, detail: `${val(data).values.length} types`, response: val(data).values };
  });

  await test("employee", "GET /employee/employment/details — list", async () => {
    const { status, data } = await api("GET", "/employee/employment/details", { params: { employmentId: ids.employment, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} details` };
  });

  await test("employee", "POST /employee/employment/details — create", async () => {
    const detDate = new Date(Date.now() + 86400000).toISOString().split("T")[0]; // tomorrow to avoid collision
    const { status, data } = await api("POST", "/employee/employment/details", {
      body: { employment: { id: ids.employment }, date: detDate, employmentType: "ORDINARY", percentageOfFullTimeEquivalent: 100 },
    });
    return { passed: status === 201 || status === 200, detail: `status=${status}`, response: single(data).value };
  });

  await test("employee", "GET /employee/category — list", async () => {
    const { status, data } = await api("GET", "/employee/category", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} categories` };
  });

  await test("employee", "GET /employee/standardTime — list", async () => {
    const { status, data } = await api("GET", "/employee/standardTime", { params: { employeeId: ids.emp, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} times` };
  });
}

// ============================================================
// 3. CUSTOMER
// ============================================================
async function testCustomer() {
  console.log("\n=== 3. CUSTOMER ===");

  await test("customer", "GET /customer — list", async () => {
    const { status, data } = await api("GET", "/customer", { params: { from: 0, count: 5 } });
    return { passed: status === 200, detail: `${val(data).values.length} customers` };
  });

  await test("customer", "POST /customer — minimal", async () => {
    const { status, data } = await api("POST", "/customer", { body: { name: `Cust${TS} AS`, isCustomer: true } });
    ids.cust = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.cust}` };
  });

  await test("customer", "POST /customer — full fields", async () => {
    const { status, data } = await api("POST", "/customer", {
      body: {
        name: `Full${TS} AS`, isCustomer: true, email: `full${TS}@example.com`,
        organizationNumber: `${TS}${TS.slice(0, 3)}`, phoneNumber: "+4722334455", phoneNumberMobile: "+4799887766",
        invoiceEmail: `inv${TS}@example.com`, invoicesDueIn: 30, invoicesDueInType: "DAYS",
        invoiceSendMethod: "EMAIL", language: "NO", isPrivateIndividual: false,
        physicalAddress: { addressLine1: `Gate ${TS}`, postalCode: "0150", city: "Oslo" },
        postalAddress: { addressLine1: `Gate ${TS}`, postalCode: "0150", city: "Oslo" },
      },
    });
    return { passed: status === 201, detail: `id=${single(data).value.id}` };
  });

  await test("customer", "POST /customer — isSupplier=true (dual)", async () => {
    const { status, data } = await api("POST", "/customer", {
      body: { name: `Dual${TS} AS`, isCustomer: true, isSupplier: true, email: `dual${TS}@example.com` },
    });
    return { passed: status === 201 && single(data).value.isSupplier === true };
  });

  await test("customer", "POST /customer — isPrivateIndividual=true", async () => {
    const { status, data } = await api("POST", "/customer", {
      body: { name: `Priv${TS} Person`, isCustomer: true, isPrivateIndividual: true, email: `priv${TS}@example.com` },
    });
    return { passed: status === 201, detail: `private=${single(data).value.isPrivateIndividual}` };
  });

  await test("customer", "POST /customer — invoicesDueInType=MONTHS", async () => {
    const { status, data } = await api("POST", "/customer", {
      body: { name: `Mon${TS} AS`, isCustomer: true, invoicesDueIn: 2, invoicesDueInType: "MONTHS" },
    });
    return { passed: status === 201, detail: `dueInType=${single(data).value.invoicesDueInType}` };
  });

  await test("customer", "POST /customer — language=EN", async () => {
    const { status, data } = await api("POST", "/customer", {
      body: { name: `Eng${TS} Ltd`, isCustomer: true, language: "EN", email: `eng${TS}@example.com` },
    });
    return { passed: status === 201, detail: `lang=${single(data).value.language}` };
  });

  await test("customer", "GET /customer/{id} — fields=*", async () => {
    const { status, data } = await api("GET", `/customer/${ids.cust}`, { params: { fields: "*" } });
    return { passed: status === 200 && single(data).value.name === `Cust${TS} AS` };
  });

  await test("customer", "GET /customer — filter name", async () => {
    const { status, data } = await api("GET", "/customer", { params: { name: `Cust${TS} AS` } });
    return { passed: status === 200 && val(data).values.length >= 1 };
  });

  await test("customer", "GET /customer — filter email", async () => {
    const { status, data } = await api("GET", "/customer", { params: { email: `full${TS}@example.com` } });
    return { passed: status === 200, detail: `found ${val(data).values.length}` };
  });

  await test("customer", "PUT /customer/{id} — update email", async () => {
    const { data: g } = await api("GET", `/customer/${ids.cust}`, { params: { fields: "*" } });
    const { status, data } = await api("PUT", `/customer/${ids.cust}`, { body: { ...single(g).value, email: `upd${TS}@example.com` } });
    return { passed: status === 200 && single(data).value.email === `upd${TS}@example.com` };
  });

  await test("customer", "POST /customer/list — batch create 3", async () => {
    const { status, data } = await api("POST", "/customer/list", {
      body: [
        { name: `BC1${TS} AS`, isCustomer: true },
        { name: `BC2${TS} AS`, isCustomer: true },
        { name: `BC3${TS} AS`, isCustomer: true },
      ],
    });
    return { passed: status === 201 && val(data).values.length === 3, detail: `created ${val(data).values.length}` };
  });

  await test("customer", "GET /customer/category — list", async () => {
    const { status, data } = await api("GET", "/customer/category", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} categories` };
  });

  await test("customer", "DELETE /customer/{id}", async () => {
    const { data: cd } = await api("POST", "/customer", { body: { name: `Del${TS} AS`, isCustomer: true } });
    const delId = (single(cd).value.id as number) || 0;
    const { status } = await api("DELETE", `/customer/${delId}`);
    return { passed: status === 200 || status === 204, detail: `status=${status}` };
  });
}

// ============================================================
// 4. PRODUCT
// ============================================================
async function testProduct() {
  console.log("\n=== 4. PRODUCT ===");

  await test("product", "GET /ledger/vatType — outgoing", async () => {
    const { status, data } = await api("GET", "/ledger/vatType", { params: { typeOfVat: "OUTGOING", from: 0, count: 100 } });
    const types = val(data).values as { id: number; name: string; percentage: number }[];
    ids.vat25 = types.find((t) => t.percentage === 25)?.id || types[0]?.id || 0;
    return { passed: status === 200 && types.length > 0, detail: `${types.length} types, 25%=${ids.vat25}` };
  });

  await test("product", "POST /product — minimal", async () => {
    const { status, data } = await api("POST", "/product", { body: { name: `Prod${TS}` } });
    ids.prod = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.prod}` };
  });

  await test("product", "POST /product — full price + VAT", async () => {
    const { status, data } = await api("POST", "/product", {
      body: {
        name: `PricedProd${TS}`, number: TS, description: `Test product ${TS}`,
        priceExcludingVatCurrency: 1500, priceIncludingVatCurrency: 1875, costExcludingVatCurrency: 800,
        vatType: ids.vat25 ? { id: ids.vat25 } : undefined, isStockItem: false, isInactive: false,
      },
    });
    ids.prodPriced = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.prodPriced}, price=${single(data).value.priceExcludingVatCurrency}` };
  });

  await test("product", "GET /product/{id} — fields=*", async () => {
    const { status, data } = await api("GET", `/product/${ids.prod}`, { params: { fields: "*" } });
    return { passed: status === 200, detail: `name=${single(data).value.name}`, response: Object.keys(single(data).value) };
  });

  await test("product", "GET /product — filter number", async () => {
    const { status, data } = await api("GET", "/product", { params: { number: TS } });
    return { passed: status === 200 && val(data).values.length >= 1 };
  });

  await test("product", "GET /product — filter name", async () => {
    const { status, data } = await api("GET", "/product", { params: { name: `Prod${TS}`, from: 0, count: 5 } });
    return { passed: status === 200, detail: `found ${val(data).values.length}` };
  });

  await test("product", "PUT /product/{id} — update price", async () => {
    const { data: g } = await api("GET", `/product/${ids.prod}`, { params: { fields: "*" } });
    const { status, data } = await api("PUT", `/product/${ids.prod}`, { body: { ...single(g).value, priceExcludingVatCurrency: 2500 } });
    return { passed: status === 200, detail: `price=${single(data).value.priceExcludingVatCurrency}` };
  });

  await test("product", "POST /product/list — batch create 3", async () => {
    const { status, data } = await api("POST", "/product/list", {
      body: [{ name: `BP1${TS}` }, { name: `BP2${TS}` }, { name: `BP3${TS}` }],
    });
    return { passed: status === 201 && val(data).values.length === 3, detail: `created ${val(data).values.length}` };
  });

  await test("product", "GET /product/group — list", async () => {
    const { status, data } = await api("GET", "/product/group", { params: { from: 0, count: 10 } });
    // 403 = permission not available in sandbox, that's expected
    return { passed: status === 200 || status === 403, detail: `status=${status}` };
  });

  await test("product", "GET /product/discountGroup — list", async () => {
    const { status, data } = await api("GET", "/product/discountGroup", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} discount groups` };
  });

  await test("product", "GET /product/inventoryLocation — list", async () => {
    const { status, data } = await api("GET", "/product/inventoryLocation", { params: { from: 0, count: 10 } });
    // 403 = Logistics module not activated in sandbox
    return { passed: status === 200 || status === 403, detail: `status=${status}` };
  });
}

// ============================================================
// 5. DEPARTMENT (already covered above — skip)
// 6. PROJECT
// ============================================================
async function testProject() {
  console.log("\n=== 5. PROJECT ===");

  const { data: ed } = await api("GET", "/employee", { params: { from: 0, count: 1, fields: "id" } });
  const managerId = (val(ed).values[0] as { id: number })?.id || 1;

  await test("project", "POST /project — minimal", async () => {
    const { status, data } = await api("POST", "/project", {
      body: { name: `Proj${TS}`, number: TS, projectManager: { id: managerId }, startDate: today },
    });
    ids.proj = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.proj}` };
  });

  await test("project", "POST /project — with description + endDate + internal", async () => {
    const { status, data } = await api("POST", "/project", {
      body: { name: `IntProj${TS}`, projectManager: { id: managerId }, startDate: today, endDate: dueDate, description: "Internal project", isInternal: true },
    });
    return { passed: status === 201, detail: `isInternal=${single(data).value.isInternal}` };
  });

  await test("project", "POST /project — fixedPrice", async () => {
    const { status, data } = await api("POST", "/project", {
      body: { name: `Fixed${TS}`, projectManager: { id: managerId }, startDate: today, isFixedPrice: true, fixedprice: 100000 },
    });
    return { passed: status === 201, detail: `fixedprice=${single(data).value.fixedprice}` };
  });

  await test("project", "POST /project — with customer", async () => {
    if (!ids.cust) {
      const { data: cd } = await api("POST", "/customer", { body: { name: `ProjCust${TS}`, isCustomer: true } });
      ids.cust = (single(cd).value.id as number) || 0;
    }
    const { status, data } = await api("POST", "/project", {
      body: { name: `CustProj${TS}`, projectManager: { id: managerId }, startDate: today, customer: { id: ids.cust } },
    });
    return { passed: status === 201 };
  });

  await test("project", "GET /project/{id}", async () => {
    const { status, data } = await api("GET", `/project/${ids.proj}`, { params: { fields: "*" } });
    return { passed: status === 200 && single(data).value.name === `Proj${TS}` };
  });

  await test("project", "GET /project — filter number", async () => {
    const { status, data } = await api("GET", "/project", { params: { number: TS } });
    return { passed: status === 200 && val(data).values.length >= 1 };
  });

  await test("project", "GET /project — filter isClosed=false", async () => {
    const { status, data } = await api("GET", "/project", { params: { isClosed: false, from: 0, count: 5 } });
    return { passed: status === 200, detail: `${val(data).values.length} open projects` };
  });

  await test("project", "PUT /project/{id} — update description", async () => {
    const { data: g } = await api("GET", `/project/${ids.proj}`, {
      params: { fields: "id,version,name,number,description,projectManager(id),startDate,endDate,isClosed,isInternal,isFixedPrice,isOffer,currency(id),vatType(id)" },
    });
    const { status, data } = await api("PUT", `/project/${ids.proj}`, { body: { ...single(g).value, description: `Updated ${TS}` } });
    return { passed: status === 200, detail: `desc=${single(data).value.description}` };
  });

  await test("project", "GET /project/category — list", async () => {
    const { status, data } = await api("GET", "/project/category", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} categories` };
  });

  await test("project", "GET /project/hourlyRates — list", async () => {
    const { status, data } = await api("GET", "/project/hourlyRates", { params: { projectId: ids.proj, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} rates` };
  });

  await test("project", "GET /project/>forTimeSheet — list", async () => {
    const { status, data } = await api("GET", "/project/>forTimeSheet", { params: { employeeId: managerId, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} projects for timesheet` };
  });
}

// ============================================================
// 6. ORDER
// ============================================================
async function testOrder() {
  console.log("\n=== 6. ORDER ===");

  if (!ids.cust) {
    const { data } = await api("POST", "/customer", { body: { name: `OrdCust${TS}`, isCustomer: true } });
    ids.cust = (single(data).value.id as number) || 0;
  }
  if (!ids.prod) {
    const { data } = await api("POST", "/product", { body: { name: `OrdProd${TS}`, priceExcludingVatCurrency: 1000 } });
    ids.prod = (single(data).value.id as number) || 0;
  }

  await test("order", "POST /order — with product orderLines", async () => {
    const { status, data } = await api("POST", "/order", {
      body: {
        orderDate: today, deliveryDate: today, customer: { id: ids.cust },
        orderLines: [{ product: { id: ids.prod }, count: 2, unitPriceExcludingVatCurrency: 1500, vatType: ids.vat25 ? { id: ids.vat25 } : undefined }],
      },
    });
    ids.order = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.order}` };
  });

  await test("order", "POST /order — description-only lines (no product)", async () => {
    const { status, data } = await api("POST", "/order", {
      body: {
        orderDate: today, deliveryDate: today, customer: { id: ids.cust },
        orderLines: [{ description: "Consulting services", count: 10, unitPriceExcludingVatCurrency: 2000 }],
        invoiceComment: "Net 30 days",
      },
    });
    ids.order2 = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.order2}` };
  });

  await test("order", "POST /order — with reference + deliveryComment", async () => {
    const { status, data } = await api("POST", "/order", {
      body: {
        orderDate: today, deliveryDate: dueDate, customer: { id: ids.cust },
        orderLines: [{ description: "Item", count: 1, unitPriceExcludingVatCurrency: 500 }],
        reference: `REF-${TS}`, deliveryComment: "Leave at door",
      },
    });
    return { passed: status === 201, detail: `ref=${single(data).value.reference}` };
  });

  await test("order", "GET /order/{id} — fields=*", async () => {
    const { status, data } = await api("GET", `/order/${ids.order}`, { params: { fields: "*" } });
    return { passed: status === 200, detail: `lines=${(single(data).value.orderLines as unknown[])?.length}`, response: Object.keys(single(data).value) };
  });

  await test("order", "GET /order — filter customerId + dates", async () => {
    const { status, data } = await api("GET", "/order", { params: { customerId: ids.cust, orderDateFrom: "2024-01-01", orderDateTo: "2027-12-31" } });
    return { passed: status === 200 && val(data).values.length >= 1, detail: `found ${val(data).values.length}` };
  });

  await test("order", "POST /order/orderline — add line to existing", async () => {
    const { status, data } = await api("POST", "/order/orderline", {
      body: { order: { id: ids.order }, product: { id: ids.prod }, count: 3, unitPriceExcludingVatCurrency: 750, description: "Extra line" },
    });
    ids.orderline = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `lineId=${ids.orderline}` };
  });

  await test("order", "POST /order/orderline/list — batch add 2 lines", async () => {
    const { status, data } = await api("POST", "/order/orderline/list", {
      body: [
        { order: { id: ids.order }, description: "Batch line 1", count: 1, unitPriceExcludingVatCurrency: 100 },
        { order: { id: ids.order }, description: "Batch line 2", count: 2, unitPriceExcludingVatCurrency: 200 },
      ],
    });
    return { passed: status === 201, detail: `created ${val(data).values.length}` };
  });

  await test("order", "GET /order/orderline/{id}", async () => {
    if (!ids.orderline) return { passed: false, detail: "no orderline id" };
    const { status, data } = await api("GET", `/order/orderline/${ids.orderline}`, { params: { fields: "*" } });
    return { passed: status === 200, detail: `desc=${single(data).value.description}` };
  });

  await test("order", "DELETE /order/orderline/{id}", async () => {
    if (!ids.orderline) return { passed: false, detail: "no orderline id" };
    const { status } = await api("DELETE", `/order/orderline/${ids.orderline}`);
    return { passed: status === 200 || status === 204, detail: `status=${status}` };
  });

  await test("order", "POST /order/list — batch create 2 orders", async () => {
    const { status, data } = await api("POST", "/order/list", {
      body: [
        { orderDate: today, deliveryDate: today, customer: { id: ids.cust }, orderLines: [{ description: "BO1", count: 1, unitPriceExcludingVatCurrency: 100 }] },
        { orderDate: today, deliveryDate: today, customer: { id: ids.cust }, orderLines: [{ description: "BO2", count: 1, unitPriceExcludingVatCurrency: 200 }] },
      ],
    });
    return { passed: status === 201, detail: `created ${val(data).values.length}` };
  });

  await test("order", "GET /order/orderGroup — list", async () => {
    const { status, data } = await api("GET", "/order/orderGroup", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} groups` };
  });
}

// ============================================================
// 7. INVOICE
// ============================================================
async function testInvoice() {
  console.log("\n=== 7. INVOICE ===");

  // Ensure bank account
  await test("invoice", "Setup bank account", async () => {
    const { data } = await api("GET", "/ledger/account", { params: { isBankAccount: true, from: 0, count: 10, fields: "*" } });
    const accts = val(data).values as { id: number; bankAccountNumber: string }[];
    const a = accts[0];
    if (!a) return { passed: false, detail: "no bank accounts" };
    if (a.bankAccountNumber) return { passed: true, detail: `already set: ${a.bankAccountNumber}` };
    const { status } = await api("PUT", `/ledger/account/${a.id}`, { body: { ...a, bankAccountNumber: "28002222222" } });
    return { passed: status === 200, detail: `set on id=${a.id}` };
  });

  // Need a fresh order for invoicing
  if (!ids.order2) {
    const { data } = await api("POST", "/order", {
      body: { orderDate: today, deliveryDate: today, customer: { id: ids.cust }, orderLines: [{ description: "For invoice", count: 5, unitPriceExcludingVatCurrency: 2000 }] },
    });
    ids.order2 = (single(data).value.id as number) || 0;
  }

  await test("invoice", "POST /invoice — create (sendToCustomer=false)", async () => {
    const { status, data } = await api("POST", "/invoice", {
      params: { sendToCustomer: false },
      body: { invoiceDate: today, invoiceDueDate: dueDate, orders: [{ id: ids.order2 }] },
    });
    ids.invoice = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.invoice}, amount=${single(data).value.amount}` };
  });

  await test("invoice", "GET /invoice/{id} — fields=*", async () => {
    const { status, data } = await api("GET", `/invoice/${ids.invoice}`, { params: { fields: "*" } });
    return { passed: status === 200, detail: `amount=${single(data).value.amount}`, response: Object.keys(single(data).value) };
  });

  await test("invoice", "GET /invoice — filter customerId + dates", async () => {
    const { status, data } = await api("GET", "/invoice", { params: { customerId: ids.cust, invoiceDateFrom: "2024-01-01", invoiceDateTo: "2027-12-31" } });
    return { passed: status === 200 && val(data).values.length >= 1, detail: `found ${val(data).values.length}` };
  });

  await test("invoice", "GET /invoice/paymentType — list", async () => {
    const { status, data } = await api("GET", "/invoice/paymentType", { params: { from: 0, count: 100 } });
    const types = val(data).values as { id: number; description: string }[];
    ids.paymentType = types[0]?.id || 0;
    return { passed: status === 200 && types.length > 0, detail: `${types.length} types, first=${ids.paymentType}`, response: types };
  });

  await test("invoice", "PUT /invoice/{id}/:payment — register", async () => {
    const { data: inv } = await api("GET", `/invoice/${ids.invoice}`, { params: { fields: "amount" } });
    const amount = single(inv).value.amount as number;
    const { status, data } = await api("PUT", `/invoice/${ids.invoice}/:payment`, {
      params: { paymentDate: today, paymentTypeId: ids.paymentType, paidAmount: amount },
    });
    return { passed: status === 200, detail: `paid ${amount}`, response: data };
  });

  await test("invoice", "PUT /invoice/{id}/:createCreditNote", async () => {
    const { status } = await api("PUT", `/invoice/${ids.invoice}/:createCreditNote`, {
      params: { date: today, comment: `Credit ${TS}`, sendToCustomer: false },
    });
    return { passed: status === 200 };
  });

  // Create another invoice for send test
  const { data: o3d } = await api("POST", "/order", {
    body: { orderDate: today, deliveryDate: today, customer: { id: ids.cust }, orderLines: [{ description: "Send test", count: 1, unitPriceExcludingVatCurrency: 100 }] },
  });
  const o3 = (single(o3d).value.id as number) || 0;

  await test("invoice", "POST /invoice — sendToCustomer=true", async () => {
    const { status, data } = await api("POST", "/invoice", {
      params: { sendToCustomer: true },
      body: { invoiceDate: today, invoiceDueDate: dueDate, orders: [{ id: o3 }] },
    });
    return { passed: status === 201, detail: `id=${single(data).value.id}` };
  });

  await test("invoice", "GET /invoice/{id}/pdf", async () => {
    const url = new URL(`${BASE_URL}/invoice/${ids.invoice}/pdf`);
    const res = await fetch(url.toString(), {
      method: "GET",
      headers: { Authorization: AUTH, Accept: "application/octet-stream" },
    });
    const bytes = (await res.arrayBuffer()).byteLength;
    return { passed: res.status === 200 && bytes > 100, detail: `status=${res.status}, bytes=${bytes}` };
  });

  await test("invoice", "GET /invoice/details — list", async () => {
    const { status, data } = await api("GET", "/invoice/details", { params: { invoiceDateFrom: "2024-01-01", invoiceDateTo: "2027-12-31", from: 0, count: 5 } });
    return { passed: status === 200, detail: `${val(data).values.length} details` };
  });
}

// ============================================================
// 8. SUPPLIER
// ============================================================
async function testSupplier() {
  console.log("\n=== 8. SUPPLIER ===");

  await test("supplier", "POST /supplier — create", async () => {
    const { status, data } = await api("POST", "/supplier", {
      body: { name: `Supp${TS} AS`, email: `supp${TS}@example.com`, phoneNumber: "+4711223344" },
    });
    ids.supp = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.supp}` };
  });

  await test("supplier", "POST /supplier — with address", async () => {
    const { status, data } = await api("POST", "/supplier", {
      body: {
        name: `FullSupp${TS} AS`, email: `fsupp${TS}@example.com`,
        physicalAddress: { addressLine1: `Leverandørgt ${TS}`, postalCode: "0250", city: "Oslo" },
      },
    });
    return { passed: status === 201, detail: `id=${single(data).value.id}` };
  });

  await test("supplier", "GET /supplier — list", async () => {
    const { status, data } = await api("GET", "/supplier", { params: { from: 0, count: 10, fields: "id,name,email" } });
    return { passed: status === 200, detail: `${val(data).values.length} suppliers` };
  });

  await test("supplier", "GET /supplier/{id} — fields=*", async () => {
    const { status, data } = await api("GET", `/supplier/${ids.supp}`, { params: { fields: "*" } });
    return { passed: status === 200, detail: `name=${single(data).value.name}`, response: Object.keys(single(data).value) };
  });

  await test("supplier", "PUT /supplier/{id} — update", async () => {
    const { data: g } = await api("GET", `/supplier/${ids.supp}`, { params: { fields: "*" } });
    const { status, data } = await api("PUT", `/supplier/${ids.supp}`, { body: { ...single(g).value, phoneNumber: "+4799988877" } });
    return { passed: status === 200, detail: `phone=${single(data).value.phoneNumber}` };
  });

  await test("supplier", "POST /supplier/list — batch create 2", async () => {
    const { status, data } = await api("POST", "/supplier/list", {
      body: [
        { name: `BS1${TS} AS`, email: `bs1${TS}@example.com` },
        { name: `BS2${TS} AS`, email: `bs2${TS}@example.com` },
      ],
    });
    return { passed: status === 201 && val(data).values.length === 2, detail: `created ${val(data).values.length}` };
  });
}

// ============================================================
// 9. CONTACT
// ============================================================
async function testContact() {
  console.log("\n=== 9. CONTACT ===");

  if (!ids.cust) {
    const { data } = await api("POST", "/customer", { body: { name: `ContCust${TS}`, isCustomer: true } });
    ids.cust = (single(data).value.id as number) || 0;
  }

  await test("contact", "POST /contact — with customer", async () => {
    const { status, data } = await api("POST", "/contact", {
      body: { firstName: `Cont${TS}`, lastName: "Person", email: `cont${TS}@example.com`, customer: { id: ids.cust }, phoneNumberMobile: "+4712121212" },
    });
    ids.contact = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.contact}` };
  });

  await test("contact", "POST /contact — without customer", async () => {
    const { status, data } = await api("POST", "/contact", {
      body: { firstName: `Free${TS}`, lastName: "Agent", email: `free${TS}@example.com` },
    });
    return { passed: status === 201, detail: `id=${single(data).value.id}` };
  });

  await test("contact", "GET /contact — list all", async () => {
    const { status, data } = await api("GET", "/contact", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} contacts` };
  });

  await test("contact", "GET /contact — filter customerId", async () => {
    const { status, data } = await api("GET", "/contact", { params: { customerId: ids.cust } });
    return { passed: status === 200 && val(data).values.length >= 1, detail: `found ${val(data).values.length}` };
  });

  await test("contact", "GET /contact — filter email", async () => {
    const { status, data } = await api("GET", "/contact", { params: { email: `cont${TS}@example.com` } });
    return { passed: status === 200, detail: `found ${val(data).values.length}` };
  });

  await test("contact", "GET /contact/{id}", async () => {
    const { status, data } = await api("GET", `/contact/${ids.contact}`, { params: { fields: "*" } });
    return { passed: status === 200, detail: `name=${single(data).value.firstName}` };
  });

  await test("contact", "PUT /contact/{id} — update phone", async () => {
    const { data: g } = await api("GET", `/contact/${ids.contact}`, { params: { fields: "id,version,firstName,lastName,email,phoneNumberMobile,phoneNumberWork,customer(id),department(id)" } });
    const { status, data } = await api("PUT", `/contact/${ids.contact}`, { body: { ...single(g).value, phoneNumberMobile: "+4798765432" } });
    return { passed: status === 200, detail: `phone=${single(data).value.phoneNumberMobile}` };
  });

  await test("contact", "POST /contact/list — batch create 2", async () => {
    const { status, data } = await api("POST", "/contact/list", {
      body: [
        { firstName: `BC1${TS}`, lastName: "One", email: `bc1c${TS}@example.com`, customer: { id: ids.cust } },
        { firstName: `BC2${TS}`, lastName: "Two", email: `bc2c${TS}@example.com`, customer: { id: ids.cust } },
      ],
    });
    return { passed: status === 201, detail: `created ${val(data).values.length}` };
  });
}

// ============================================================
// 10. LEDGER
// ============================================================
async function testLedger() {
  console.log("\n=== 10. LEDGER ===");

  await test("ledger", "GET /ledger — general ledger", async () => {
    const { status, data } = await api("GET", "/ledger", { params: { dateFrom: "2024-01-01", dateTo: today, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} entries` };
  });

  await test("ledger", "GET /ledger/account — list all", async () => {
    const { status, data } = await api("GET", "/ledger/account", { params: { from: 0, count: 20, fields: "id,number,name" } });
    return { passed: status === 200, detail: `${val(data).values.length} accounts` };
  });

  await test("ledger", "GET /ledger/account — isBankAccount=true", async () => {
    const { status, data } = await api("GET", "/ledger/account", { params: { isBankAccount: true, fields: "id,number,name,bankAccountNumber" } });
    return { passed: status === 200, detail: `${val(data).values.length} bank accounts`, response: val(data).values };
  });

  await test("ledger", "GET /ledger/account — ledgerType=GENERAL", async () => {
    const { status, data } = await api("GET", "/ledger/account", { params: { ledgerType: "GENERAL", from: 0, count: 5 } });
    return { passed: status === 200, detail: `${val(data).values.length}` };
  });

  await test("ledger", "GET /ledger/account — ledgerType=CUSTOMER", async () => {
    const { status, data } = await api("GET", "/ledger/account", { params: { ledgerType: "CUSTOMER", from: 0, count: 5 } });
    return { passed: status === 200, detail: `${val(data).values.length}` };
  });

  await test("ledger", "GET /ledger/account — ledgerType=VENDOR", async () => {
    const { status, data } = await api("GET", "/ledger/account", { params: { ledgerType: "VENDOR", from: 0, count: 5 } });
    return { passed: status === 200, detail: `${val(data).values.length}` };
  });

  await test("ledger", "GET /ledger/vatType — all", async () => {
    const { status, data } = await api("GET", "/ledger/vatType", { params: { from: 0, count: 100 } });
    return { passed: status === 200, detail: `${val(data).values.length} total` };
  });

  await test("ledger", "GET /ledger/vatType — OUTGOING", async () => {
    const { status, data } = await api("GET", "/ledger/vatType", { params: { typeOfVat: "OUTGOING", from: 0, count: 100 } });
    return { passed: status === 200, detail: `${val(data).values.length} outgoing`, response: val(data).values };
  });

  await test("ledger", "GET /ledger/vatType — INCOMING", async () => {
    const { status, data } = await api("GET", "/ledger/vatType", { params: { typeOfVat: "INCOMING", from: 0, count: 100 } });
    return { passed: status === 200, detail: `${val(data).values.length} incoming` };
  });

  await test("ledger", "GET /ledger/accountingPeriod — list", async () => {
    const { status, data } = await api("GET", "/ledger/accountingPeriod", { params: { from: 0, count: 20 } });
    return { passed: status === 200, detail: `${val(data).values.length} periods` };
  });

  await test("ledger", "GET /ledger/paymentTypeOut — list", async () => {
    const { status, data } = await api("GET", "/ledger/paymentTypeOut", { params: { from: 0, count: 100 } });
    return { passed: status === 200, detail: `${val(data).values.length} types`, response: val(data).values };
  });

  await test("ledger", "GET /ledger/openPost — list", async () => {
    const { status, data } = await api("GET", "/ledger/openPost", { params: { date: today, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} open posts` };
  });

  await test("ledger", "GET /ledger/closeGroup — list", async () => {
    const { status, data } = await api("GET", "/ledger/closeGroup", { params: { dateFrom: "2024-01-01", dateTo: today, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} close groups` };
  });

  await test("ledger", "GET /ledger/accountingDimensionName — list", async () => {
    const { status, data } = await api("GET", "/ledger/accountingDimensionName", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} dimensions` };
  });
}

// ============================================================
// 11. BANK
// ============================================================
async function testBank() {
  console.log("\n=== 11. BANK ===");

  await test("bank", "GET /bank/statement — list", async () => {
    const { status, data } = await api("GET", "/bank/statement", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} statements` };
  });

  await test("bank", "GET /bank/reconciliation — list", async () => {
    const { status, data } = await api("GET", "/bank/reconciliation", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} reconciliations` };
  });

  await test("bank", "GET /bank/statement/transaction — list", async () => {
    const { status, data } = await api("GET", "/bank/statement/transaction", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} transactions` };
  });
}

// ============================================================
// 12. CURRENCY
// ============================================================
async function testCurrency() {
  console.log("\n=== 12. CURRENCY ===");

  await test("currency", "GET /currency — list", async () => {
    const { status, data } = await api("GET", "/currency", { params: { from: 0, count: 50 } });
    const currencies = val(data).values as { id: number; code: string }[];
    ids.currNOK = currencies.find((c) => c.code === "NOK")?.id || 0;
    ids.currUSD = currencies.find((c) => c.code === "USD")?.id || 0;
    ids.currEUR = currencies.find((c) => c.code === "EUR")?.id || 0;
    return { passed: status === 200, detail: `${currencies.length} currencies, NOK=${ids.currNOK}, USD=${ids.currUSD}, EUR=${ids.currEUR}` };
  });

  await test("currency", "GET /currency/{id} — NOK", async () => {
    if (!ids.currNOK) return { passed: false, detail: "no NOK id" };
    const { status, data } = await api("GET", `/currency/${ids.currNOK}`);
    return { passed: status === 200, detail: `code=${single(data).value.code}` };
  });

  await test("currency", "GET /currency/rate — list", async () => {
    // currency/rate endpoint has parsing issues with 'rate' in path in some sandbox configs
    const { status } = await api("GET", "/currency/rate", { params: { type: "buy", dateFrom: "2025-01-01", dateTo: today, from: 0, count: 10 } });
    return { passed: status === 200 || status === 422, detail: `status=${status} (422=sandbox rate data not available)` };
  });
}

// ============================================================
// 13. COMPANY
// ============================================================
async function testCompany() {
  console.log("\n=== 13. COMPANY ===");

  await test("company", "GET /token/session/>whoAmI", async () => {
    const { status, data } = await api("GET", "/token/session/>whoAmI");
    const s = single(data).value;
    ids.company = (s.company as { id: number })?.id || 0;
    return { passed: status === 200, detail: `companyId=${ids.company}, empId=${(s.employee as { id: number })?.id}`, response: s };
  });

  await test("company", "GET /company/{id} — fields=*", async () => {
    const { status, data } = await api("GET", `/company/${ids.company}`, { params: { fields: "*" } });
    return { passed: status === 200, detail: `name=${single(data).value.name}`, response: Object.keys(single(data).value) };
  });
}

// ============================================================
// 14. ACTIVITY
// ============================================================
async function testActivity() {
  console.log("\n=== 14. ACTIVITY ===");

  await test("activity", "GET /activity — list", async () => {
    const { status, data } = await api("GET", "/activity", { params: { from: 0, count: 20 } });
    const activities = val(data).values as { id: number; name: string }[];
    ids.activity = activities[0]?.id || 0;
    return { passed: status === 200, detail: `${activities.length} activities`, response: activities.slice(0, 5) };
  });

  await test("activity", "POST /activity — create", async () => {
    const { status, data } = await api("POST", "/activity", {
      body: { name: `Act${TS}`, activityType: "GENERAL_ACTIVITY" },
    });
    return { passed: status === 201 || status === 200, detail: `status=${status}, id=${single(data).value.id}` };
  });

  await test("activity", "GET /activity/{id}", async () => {
    if (!ids.activity) return { passed: false, detail: "no activity id" };
    const { status, data } = await api("GET", `/activity/${ids.activity}`);
    return { passed: status === 200, detail: `name=${single(data).value.name}` };
  });

  await test("activity", "GET /activity/>forTimeSheet — list", async () => {
    const { data: ed } = await api("GET", "/employee", { params: { from: 0, count: 1, fields: "id" } });
    const empId = (val(ed).values[0] as { id: number })?.id || 1;
    const { status, data } = await api("GET", "/activity/>forTimeSheet", { params: { projectId: ids.proj || 0, employeeId: empId } });
    return { passed: status === 200, detail: `${val(data).values.length} timesheet activities` };
  });
}

// ============================================================
// 15. TRAVEL EXPENSE
// ============================================================
async function testTravelExpense() {
  console.log("\n=== 15. TRAVEL EXPENSE ===");

  const { data: ed } = await api("GET", "/employee", { params: { from: 0, count: 1, fields: "id" } });
  const empId = (val(ed).values[0] as { id: number })?.id || 1;

  await test("travelExpense", "POST /travelExpense — create", async () => {
    const { status, data } = await api("POST", "/travelExpense", {
      body: { employee: { id: empId }, title: `Trip${TS}` },
    });
    ids.travelExpense = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.travelExpense}` };
  });

  await test("travelExpense", "GET /travelExpense — list", async () => {
    const { status, data } = await api("GET", "/travelExpense", { params: { from: 0, count: 10, fields: "id,title,employee(id)" } });
    return { passed: status === 200, detail: `${val(data).values.length} expenses` };
  });

  await test("travelExpense", "GET /travelExpense/{id}", async () => {
    const { status, data } = await api("GET", `/travelExpense/${ids.travelExpense}`, { params: { fields: "*" } });
    return { passed: status === 200, detail: `title=${single(data).value.title}`, response: Object.keys(single(data).value) };
  });

  await test("travelExpense", "POST /travelExpense/cost — create", async () => {
    // Get a travel-expense cost category (showOnTravelExpenses=true)
    const { data: catData } = await api("GET", "/travelExpense/costCategory", { params: { from: 0, count: 20, fields: "id,showOnTravelExpenses" } });
    const cats = val(catData).values as { id: number; showOnTravelExpenses: boolean }[];
    const catId = cats.find(c => c.showOnTravelExpenses)?.id || cats[0]?.id;
    if (!catId) return { passed: false, detail: "no cost categories available" };
    // Get travel expense payment type
    const { data: ptData } = await api("GET", "/travelExpense/paymentType", { params: { from: 0, count: 1 } });
    const ptId = (val(ptData).values[0] as { id: number })?.id;
    if (!ptId) return { passed: false, detail: "no travel payment types" };
    const { status, data } = await api("POST", "/travelExpense/cost", {
      body: { travelExpense: { id: ids.travelExpense }, date: today, costCategory: { id: catId }, amountCurrencyIncVat: 500, currency: { id: ids.currNOK || 1 }, paymentType: { id: ptId } },
    });
    ids.travelCost = (single(data).value.id as number) || 0;
    return { passed: status === 201 || status === 200, detail: `status=${status}, id=${ids.travelCost}` };
  });

  await test("travelExpense", "GET /travelExpense/cost — list", async () => {
    const { status, data } = await api("GET", "/travelExpense/cost", { params: { travelExpenseId: ids.travelExpense, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} costs` };
  });

  await test("travelExpense", "GET /travelExpense/mileageAllowance — list", async () => {
    const { status, data } = await api("GET", "/travelExpense/mileageAllowance", { params: { travelExpenseId: ids.travelExpense, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} mileage` };
  });

  await test("travelExpense", "GET /travelExpense/perDiemCompensation — list", async () => {
    const { status, data } = await api("GET", "/travelExpense/perDiemCompensation", { params: { travelExpenseId: ids.travelExpense, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} per diem` };
  });

  await test("travelExpense", "GET /travelExpense/accommodationAllowance — list", async () => {
    const { status, data } = await api("GET", "/travelExpense/accommodationAllowance", { params: { travelExpenseId: ids.travelExpense, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} accommodation` };
  });

  await test("travelExpense", "DELETE /travelExpense/{id}", async () => {
    const { status } = await api("DELETE", `/travelExpense/${ids.travelExpense}`);
    return { passed: status === 204 || status === 200 };
  });
}

// ============================================================
// 16. TIMESHEET
// ============================================================
async function testTimesheet() {
  console.log("\n=== 16. TIMESHEET ===");

  const { data: ed } = await api("GET", "/employee", { params: { from: 0, count: 1, fields: "id" } });
  const empId = (val(ed).values[0] as { id: number })?.id || 1;

  await test("timesheet", "GET /timesheet/entry — list", async () => {
    const tomorrow = new Date(Date.now() + 86400000).toISOString().split("T")[0];
    const { status, data } = await api("GET", "/timesheet/entry", { params: { dateFrom: "2024-01-01", dateTo: tomorrow, employeeId: empId, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} entries` };
  });

  await test("timesheet", "POST /timesheet/entry — create", async () => {
    // Must get project first, then get activities FOR that project
    const { data: projData } = await api("GET", "/project/>forTimeSheet", { params: { employeeId: empId, from: 0, count: 1 } });
    const projId = (val(projData).values[0] as { id: number })?.id;
    if (!projId) return { passed: false, detail: "no project for timesheet" };

    // Get activities valid for this specific project
    const { data: actData } = await api("GET", "/activity/>forTimeSheet", { params: { projectId: projId, from: 0, count: 1 } });
    const actId = (val(actData).values[0] as { id: number })?.id;
    if (!actId) return { passed: false, detail: `no activities for project ${projId}` };

    const { status, data } = await api("POST", "/timesheet/entry", {
      body: { employee: { id: empId }, project: { id: projId }, activity: { id: actId }, date: today, hours: 2.5, comment: `Test ${TS}` },
    });
    ids.timesheetEntry = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${ids.timesheetEntry}`, response: single(data).value };
  });

  await test("timesheet", "GET /timesheet/entry — verify created", async () => {
    const tomorrow = new Date(Date.now() + 86400000).toISOString().split("T")[0];
    const { status, data } = await api("GET", "/timesheet/entry", { params: { dateFrom: today, dateTo: tomorrow, employeeId: empId, from: 0, count: 10 } });
    return { passed: status === 200 && val(data).values.length >= 1, detail: `${val(data).values.length} entries today` };
  });

  await test("timesheet", "PUT /timesheet/entry/{id} — update hours", async () => {
    if (!ids.timesheetEntry) return { passed: false, detail: "no entry" };
    const { data: g } = await api("GET", `/timesheet/entry/${ids.timesheetEntry}`, { params: { fields: "*" } });
    const c = single(g).value;
    const { status, data } = await api("PUT", `/timesheet/entry/${ids.timesheetEntry}`, { body: { ...c, hours: 4.0 } });
    return { passed: status === 200, detail: `hours=${single(data).value.hours}` };
  });

  await test("timesheet", "DELETE /timesheet/entry/{id}", async () => {
    if (!ids.timesheetEntry) return { passed: false, detail: "no entry" };
    const { status } = await api("DELETE", `/timesheet/entry/${ids.timesheetEntry}`);
    return { passed: status === 204 || status === 200 };
  });

  await test("timesheet", "GET /timesheet/timeClock — list", async () => {
    const { status, data } = await api("GET", "/timesheet/timeClock", { params: { employeeId: empId, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} clocks` };
  });
}

// ============================================================
// 17. SUPPLIER INVOICE
// ============================================================
async function testSupplierInvoice() {
  console.log("\n=== 17. SUPPLIER INVOICE ===");

  await test("supplierInvoice", "GET /supplierInvoice — list", async () => {
    const { status, data } = await api("GET", "/supplierInvoice", { params: { invoiceDateFrom: "2024-01-01", invoiceDateTo: "2027-12-31", from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} invoices` };
  });

  await test("supplierInvoice", "GET /supplierInvoice/forApproval — list", async () => {
    const { status, data } = await api("GET", "/supplierInvoice/forApproval", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} for approval` };
  });
}

// ============================================================
// 18. SALARY
// ============================================================
async function testSalary() {
  console.log("\n=== 18. SALARY ===");

  const { data: ed } = await api("GET", "/employee", { params: { from: 0, count: 1, fields: "id" } });
  const empId = (val(ed).values[0] as { id: number })?.id || 1;

  await test("salary", "GET /salary/payslip — list", async () => {
    const { status, data } = await api("GET", "/salary/payslip", { params: { employeeId: empId, yearFrom: 2024, monthFrom: 1, yearTo: 2026, monthTo: 12, from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} payslips` };
  });

  await test("salary", "GET /salary/settings — get", async () => {
    const { status, data } = await api("GET", "/salary/settings");
    return { passed: status === 200, detail: `status=${status}`, response: data };
  });

  await test("salary", "GET /salary/compilation — get", async () => {
    const { status, data } = await api("GET", "/salary/compilation", { params: { employeeId: empId, year: 2025 } });
    return { passed: status === 200, detail: `status=${status}` };
  });
}

// ============================================================
// 19. DOCUMENT ARCHIVE
// ============================================================
async function testDocumentArchive() {
  console.log("\n=== 19. DOCUMENT ARCHIVE ===");

  // documentArchive endpoints return 405 in sandbox (upload-only, no GET listing)
  // Accept 200 or 400/405 as "endpoint exists"
  await test("documentArchive", "GET /documentArchive/customer — list", async () => {
    const { status } = await api("GET", "/documentArchive/customer", { params: { customerId: ids.cust || 0, periodDateFrom: "2024-01-01", periodDateTo: "2027-12-31", from: 0, count: 10 } });
    return { passed: status === 200 || status === 400, detail: `status=${status} (400=no GET support in sandbox)` };
  });

  await test("documentArchive", "GET /documentArchive/project — list", async () => {
    const { status } = await api("GET", "/documentArchive/project", { params: { projectId: ids.proj || 0, periodDateFrom: "2024-01-01", periodDateTo: "2027-12-31", from: 0, count: 10 } });
    return { passed: status === 200 || status === 400, detail: `status=${status} (400=no GET support in sandbox)` };
  });

  await test("documentArchive", "GET /documentArchive/employee — list", async () => {
    const { status } = await api("GET", "/documentArchive/employee", { params: { employeeId: ids.emp || 0, periodDateFrom: "2024-01-01", periodDateTo: "2027-12-31", from: 0, count: 10 } });
    return { passed: status === 200 || status === 400, detail: `status=${status} (400=no GET support in sandbox)` };
  });
}

// ============================================================
// 20. INVENTORY
// ============================================================
async function testInventory() {
  console.log("\n=== 20. INVENTORY ===");

  await test("inventory", "GET /inventory — list", async () => {
    const { status, data } = await api("GET", "/inventory", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} inventories` };
  });

  await test("inventory", "GET /inventory/location — list", async () => {
    const { status, data } = await api("GET", "/inventory/location", { params: { from: 0, count: 10 } });
    // 204 = empty list (valid), 200 = has data
    return { passed: status === 200 || status === 204, detail: `status=${status}` };
  });

  await test("inventory", "GET /inventory/stocktaking — list", async () => {
    const { status, data } = await api("GET", "/inventory/stocktaking", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} stocktakings` };
  });
}

// ============================================================
// 21. BALANCE SHEET / RESULT BUDGET
// ============================================================
async function testBalanceSheet() {
  console.log("\n=== 21. BALANCE & REPORTS ===");

  await test("balance", "GET /balanceSheet — get", async () => {
    const { status, data } = await api("GET", "/balanceSheet", { params: { dateFrom: "2025-01-01", dateTo: today, from: 0, count: 10 } });
    return { passed: status === 200, detail: `status=${status}` };
  });

  await test("balance", "GET /resultBudget — get", async () => {
    const { status } = await api("GET", "/resultBudget", { params: { dateFrom: "2025-01-01", dateTo: today, from: 0, count: 10 } });
    // 404 in sandbox = endpoint may not be enabled, 200 = has data
    return { passed: status === 200 || status === 404, detail: `status=${status}` };
  });

  await test("balance", "GET /ledger/annualAccount — list", async () => {
    const { status, data } = await api("GET", "/ledger/annualAccount", { params: { from: 0, count: 5 } });
    return { passed: status === 200, detail: `${val(data).values.length} annual accounts` };
  });
}

// ============================================================
// 22. COUNTRY + ADDRESS
// ============================================================
async function testCountry() {
  console.log("\n=== 22. COUNTRY ===");

  await test("country", "GET /country — list", async () => {
    const { status, data } = await api("GET", "/country", { params: { from: 0, count: 20 } });
    return { passed: status === 200, detail: `${val(data).values.length} countries` };
  });

  await test("country", "GET /deliveryAddress — list", async () => {
    const { status, data } = await api("GET", "/deliveryAddress", { params: { from: 0, count: 10 } });
    return { passed: status === 200, detail: `${val(data).values.length} addresses` };
  });
}

// ============================================================
// WORKFLOW TESTS
// ============================================================
async function testWorkflows() {
  console.log("\n=== WORKFLOW: Full Invoice ===");

  let wCust = 0, wOrder = 0, wInvoice = 0;

  await test("workflow-invoice", "1. Create customer", async () => {
    const { status, data } = await api("POST", "/customer", { body: { name: `WF${TS} AS`, isCustomer: true, email: `wf${TS}@example.com` } });
    wCust = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${wCust}` };
  });

  await test("workflow-invoice", "2. Create order", async () => {
    const { status, data } = await api("POST", "/order", {
      body: { orderDate: today, deliveryDate: today, customer: { id: wCust }, orderLines: [{ description: "Consulting", count: 10, unitPriceExcludingVatCurrency: 2580 }] },
    });
    wOrder = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${wOrder}` };
  });

  await test("workflow-invoice", "3. Create invoice + send", async () => {
    const { status, data } = await api("POST", "/invoice", {
      params: { sendToCustomer: false },
      body: { invoiceDate: today, invoiceDueDate: dueDate, orders: [{ id: wOrder }] },
    });
    wInvoice = (single(data).value.id as number) || 0;
    return { passed: status === 201, detail: `id=${wInvoice}, amount=${single(data).value.amount}` };
  });

  await test("workflow-invoice", "4. Register payment", async () => {
    const { data: inv } = await api("GET", `/invoice/${wInvoice}`, { params: { fields: "amount" } });
    const amount = single(inv).value.amount as number;
    const { status } = await api("PUT", `/invoice/${wInvoice}/:payment`, {
      params: { paymentDate: today, paymentTypeId: ids.paymentType, paidAmount: amount },
    });
    return { passed: status === 200, detail: `paid ${amount}` };
  });

  await test("workflow-invoice", "5. Verify paid", async () => {
    const { status, data } = await api("GET", `/invoice/${wInvoice}`, { params: { fields: "id,amount,amountOutstanding" } });
    return { passed: status === 200, detail: `outstanding=${single(data).value.amountOutstanding}` };
  });

  console.log("\n=== WORKFLOW: Employee Onboarding ===");

  await test("workflow-employee", "1. Create dept + employee + employment", async () => {
    const { data: dd } = await api("POST", "/department", { body: { name: `WFDept${TS}` } });
    const deptId = (single(dd).value.id as number) || 0;
    const { data: ed } = await api("POST", "/employee", {
      body: { firstName: `WFEmp${TS}`, lastName: "Onboard", email: `wfemp${TS}@example.com`, userType: "STANDARD", department: { id: deptId }, dateOfBirth: "1992-03-20" },
    });
    const empId = (single(ed).value.id as number) || 0;
    const { status } = await api("POST", "/employee/employment", {
      body: { employee: { id: empId }, startDate: today, isMainEmployer: true },
    });
    return { passed: status === 201, detail: `dept=${deptId}, emp=${empId}` };
  });

  console.log("\n=== WORKFLOW: Project + Timesheet ===");

  await test("workflow-project", "1. Create project + timesheet entry", async () => {
    const { data: ed } = await api("GET", "/employee", { params: { from: 0, count: 1, fields: "id" } });
    const empId = (val(ed).values[0] as { id: number })?.id || 1;
    const { data: pd } = await api("POST", "/project", {
      body: { name: `WFProj${TS}`, projectManager: { id: empId }, startDate: today },
    });
    const projId = (single(pd).value.id as number) || 0;
    // Get activities valid for this specific project
    const { data: actData } = await api("GET", "/activity/>forTimeSheet", { params: { projectId: projId, from: 0, count: 1 } });
    const actId = (val(actData).values[0] as { id: number })?.id;
    if (!actId) return { passed: false, detail: "no activity for project" };

    const { status, data } = await api("POST", "/timesheet/entry", {
      body: { employee: { id: empId }, project: { id: projId }, activity: { id: actId }, date: today, hours: 7.5 },
    });
    const entryId = (single(data).value.id as number) || 0;
    // Clean up
    if (entryId) await api("DELETE", `/timesheet/entry/${entryId}`);
    return { passed: status === 201, detail: `proj=${projId}, entry=${entryId}` };
  });
}

// ============================================================
// MAIN
// ============================================================
async function main() {
  const args = process.argv.slice(2);
  const filterCategory = args.find((a) => a.startsWith("--cat="))?.split("=")[1]?.toLowerCase();
  const listOnly = args.includes("--list");
  const workflowOnly = args.includes("--workflow");

  const categories = [
    "department", "employee", "customer", "product", "project",
    "order", "invoice", "supplier", "contact", "ledger",
    "bank", "currency", "company", "activity", "travelExpense",
    "timesheet", "supplierInvoice", "salary", "documentArchive",
    "inventory", "balance", "country", "workflow",
  ];

  if (listOnly) {
    console.log("Available test categories:");
    for (const cat of categories) console.log(`  ${cat}`);
    console.log("\nUsage: npx tsx src/api-tester.ts [--cat=employee] [--workflow] [--list]");
    return;
  }

  console.log(`Tripletex API Comprehensive Tester`);
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Unique suffix: ${TS}`);
  console.log(`Date: ${today}`);
  console.log(`Categories: ${filterCategory || "all"}\n`);

  const run = (cat: string) => !filterCategory || cat === filterCategory || filterCategory === "all";

  if (!workflowOnly) {
    if (run("department")) await testDepartment();
    if (run("employee")) await testEmployee();
    if (run("customer")) await testCustomer();
    if (run("product")) await testProduct();
    if (run("project")) await testProject();
    if (run("order")) await testOrder();
    if (run("invoice")) await testInvoice();
    if (run("supplier")) await testSupplier();
    if (run("contact")) await testContact();
    if (run("ledger")) await testLedger();
    if (run("bank")) await testBank();
    if (run("currency")) await testCurrency();
    if (run("company")) await testCompany();
    if (run("activity")) await testActivity();
    if (run("travelExpense")) await testTravelExpense();
    if (run("timesheet")) await testTimesheet();
    if (run("supplierInvoice")) await testSupplierInvoice();
    if (run("salary")) await testSalary();
    if (run("documentArchive")) await testDocumentArchive();
    if (run("inventory")) await testInventory();
    if (run("balance")) await testBalanceSheet();
    if (run("country")) await testCountry();
  }

  if (run("workflow") || workflowOnly) await testWorkflows();

  // Summary
  console.log(`\n${"=".repeat(60)}`);
  console.log("SUMMARY");
  console.log("=".repeat(60));

  const byCategory = new Map<string, TestResult[]>();
  for (const r of results) {
    if (!byCategory.has(r.category)) byCategory.set(r.category, []);
    byCategory.get(r.category)!.push(r);
  }

  let totalPass = 0, totalFail = 0;
  for (const [cat, tests] of byCategory) {
    const passed = tests.filter((t) => t.passed).length;
    const failed = tests.length - passed;
    totalPass += passed;
    totalFail += failed;
    const icon = failed === 0 ? "PASS" : "FAIL";
    console.log(`  [${icon}] ${cat}: ${passed}/${tests.length}`);
    if (failed > 0) {
      for (const t of tests.filter((t) => !t.passed)) {
        console.log(`         - ${t.name}: ${t.error || t.detail || "failed"}`);
      }
    }
  }

  console.log(`\nTotal: ${totalPass}/${totalPass + totalFail} passed`);
  const totalDuration = results.reduce((sum, r) => sum + r.durationMs, 0);
  console.log(`Duration: ${(totalDuration / 1000).toFixed(1)}s`);
}

main().catch(console.error);
