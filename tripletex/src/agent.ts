import Anthropic from "@anthropic-ai/sdk";
import { GoogleGenerativeAI, type FunctionDeclaration, type Part, SchemaType } from "@google/generative-ai";
import { TripletexClient, TripletexApiError } from "./tripletex-client.js";
import { handleApiDocsQuery } from "./api-docs.js";
import type { FileAttachment, ToolCall } from "./types.js";
import { createTripletexApi, type TripletexApi, type Schemas } from "./openapi-client.js";
import { validateApiCall, formatValidationError } from "./openapi-validator.js";

export type LLMProvider = "anthropic" | "gemini";

/**
 * Validate a tool call against the OpenAPI spec, then execute it.
 * Returns { result, isError } — validation failures are returned as errors
 * without hitting the API, saving a round-trip and error penalty.
 */
async function validateAndExecute(
  client: TripletexClient,
  call: ToolCall,
): Promise<{ result: unknown; isError: boolean }> {
  // Validate against OpenAPI spec before making the request
  const validation = validateApiCall(call.method, call.path, call.params, call.body);
  if (validation) {
    const msg = formatValidationError(validation);
    console.log(`OpenAPI validation blocked ${call.method} ${call.path}: ${validation.type}`);
    return { result: { error: true, validation: true, message: msg }, isError: true };
  }

  try {
    const result = await client.execute(call);
    return { result, isError: false };
  } catch (e) {
    if (e instanceof TripletexApiError) {
      return {
        result: {
          error: true,
          status: e.status,
          message: e.details.message || e.message,
          developerMessage: e.details.developerMessage,
          validationMessages: e.details.validationMessages,
        },
        isError: true,
      };
    }
    return { result: { error: true, message: String(e) }, isError: true };
  }
}

// Short system instruction — just enough for Gemini to understand the tool
const SYSTEM_INSTRUCTION = `You are an expert accounting agent for Tripletex (Norwegian accounting system).
You execute tasks using the tripletex_api tool (method, path, params, body). Auth is automatic.
This is a scored competition. Every API error costs points. Plan carefully, execute precisely, minimize calls.
After completing all API calls, respond with DONE.`;

// Full reference moved to initial user message to reduce per-turn token usage
const SYSTEM_PROMPT = `You are an expert accounting agent for Tripletex, a Norwegian accounting system.
You receive a task prompt (possibly in Norwegian, English, Spanish, Portuguese, Nynorsk, German, or French) and must execute it using the Tripletex REST API.

You have access to a tool "tripletex_api" that makes HTTP requests to the Tripletex API.
Auth is handled automatically. Just specify the method, path (starting with /), optional params, and optional body.
List responses: {"values": [...], "fullResultSize": N}. Single responses: {"value": {...}}.
Use ?fields=* to see all fields. Linked entities use {"id": number} format.

=== ENDPOINT REFERENCE (use EXACT field names) ===

POST /employee — Create employee
  Required: firstName (string), lastName (string), email (string), userType (enum: "STANDARD"|"EXTENDED"|"NO_ACCESS"), department ({"id": number})
  Optional: phoneNumberMobile, bankAccountNumber, nationalIdentityNumber, employeeNumber, dateOfBirth, address, comments
  IMPORTANT: Do NOT set isContact=true — this makes the employee a "contact" which excludes them from normal employee listings.
  For admin role ("kontoadministrator"): use userType "EXTENDED". Note: admin permissions may also require setting roles via a separate endpoint.
  IMPORTANT: If the task specifies a START DATE, you must create an Employment record AFTER creating the employee:
    POST /employee/employment with body: {employee: {"id": employeeId}, startDate: "YYYY-MM-DD", isMainEmployer: true}
    NOTE: Employment creation REQUIRES the employee to have dateOfBirth set. If you need employment, include dateOfBirth when creating the employee (e.g. "1990-01-15").
  The startDate is on the Employment object, NOT on the Employee object.
  Similarly for employment details (salary, job title, etc): POST /employee/employment/details
  WORKING HOURS: If contract/PDF specifies "Arbeidstid" or working hours per day, you MUST:
    a) Include workingHoursScheme:"NOT_SHIFT" AND shiftDurationHours:X in the POST /employee/employment/details body
    b) ALSO call POST /employee/standardTime with body: {employee:{"id":empId}, fromDate:"YYYY-MM-DD", hoursPerDay:X}
    This is CRITICAL — without both of these, the "konfigurer standard arbeidstid" check WILL FAIL.
  Occupation codes: GET /employee/employment/occupationCode (NOT /employee/occupationCode!) to find valid codes.
  CRITICAL: The database uses 7-digit codes (e.g. "3512101"), NOT 4-digit STYRK codes (e.g. "3512").
  The "code" param does SUBSTRING search on 7-digit codes. A 4-digit STYRK code may NOT appear as a substring.
  OCCUPATION CODE SEARCH STRATEGY (max 2 attempts):
    1. GET /employee/employment/occupationCode?code={STYRK_CODE}1&count=20
       Append "1" to the 4-digit STYRK code to narrow results.
       Pick the result whose 7-digit "code" field STARTS WITH the 4-digit STYRK code.
    2. If 0 results: GET /employee/employment/occupationCode?code={STYRK_CODE}&count=20
    ALWAYS search by numeric code, NEVER by nameNO.
  Set occupationCode on employment details: occupationCode:{"id": codeId}
  First GET /department to find a department ID. First GET /employee to check if employee exists.
  Batch: POST /employee/list (Array of Employee)

PUT /employee/{id} — Update employee
  Include all fields you want to keep plus changes. Include version from GET response.
  CRITICAL: dateOfBirth is REQUIRED for PUT. If updating an employee, always include dateOfBirth.
  When GETting employee for update, use specific fields (NOT fields=*) to avoid sending back read-only computed fields.
  Good fields for GET: id,version,firstName,lastName,email,dateOfBirth,department(id),phoneNumberMobile

POST /customer — Create customer
  Required: name (string), isCustomer (boolean, set true)
  Optional: organizationNumber, email, invoiceEmail, phoneNumber, phoneNumberMobile, isSupplier, isPrivateIndividual, invoicesDueIn, invoicesDueInType ("DAYS"|"MONTHS"|"RECURRING_DAY_OF_MONTH"), invoiceSendMethod ("EMAIL"|"EHF"|"EFAKTURA"|"AVTALEGIRO"|"VIPPS"|"PAPER"|"MANUAL"), physicalAddress, postalAddress, deliveryAddress, accountManager (Employee ref), language ("NO"|"EN"), currency (Currency ref), bankAccounts (Array<string>)
  Address object: {addressLine1: string, addressLine2: string, postalCode: string, city: string}
  IMPORTANT: When a task specifies an address, ALWAYS set BOTH physicalAddress AND postalAddress with the same values.
  IMPORTANT: When email is provided, set BOTH email AND invoiceEmail to the same value.
  Batch: POST /customer/list (WARNING: This is a BETA endpoint, may return 403. Create individually if batch fails.)

POST /product — Create product
  Required: name (string)
  PRICE FIELDS — provide ONLY the one matching the task, do NOT send all three:
    - Task says "excluding VAT" / "eks. mva" / "exkl." / "hors TVA" / "sin IVA": send ONLY priceExcludingVatCurrency
    - Task says "including VAT" / "inkl. mva": send ONLY priceIncludingVatCurrency
    - Never send costExcludingVatCurrency unless task explicitly mentions cost price
  DO NOT use "priceExcludingVat" — the correct field is "priceExcludingVatCurrency"
  Optional: number (string, auto-generated if omitted), description, isStockItem, isInactive, currency, productUnit, account, department, supplier
  ALWAYS include vatType ({"id": number}) — products without vatType cause 422 on order lines.
  VAT: GET /ledger/vatType?typeOfVat=OUTGOING&from=0&count=100 ONCE to find VAT type IDs.
  CRITICAL: Must use typeOfVat=OUTGOING — without it you get INCOMING types which fail with 422.
  *** MANDATORY VAT RULE ***: If the task does NOT explicitly say "0%", "exempt", "avgiftsfri", "exento", "food", "15%", "12%", then ALWAYS use 25% VAT (høy sats). Pick the vatType with percentage=25.
  *** SANDBOX VAT CONSTRAINT ***: If POST /product fails with "Ugyldig mva-kode" when using vatType 25%, try outgoing vatType with id=6 instead. Do NOT waste calls retrying.
  WORKFLOW for products (GET /product?number=X FAILS — never use number= parameter):
    1. GET /product?query=<product_name>&count=100&from=0 — search by PRODUCT NAME
    2. If no match: GET /product?query=<product_number>&count=100&from=0
    3. If exact match found: use that ID. If name/price differs: PUT /product/{id} to update.
    4. If no match: POST /product to create it.
    5. If POST fails "number already in use": repeat search with count=100.
  NEVER add suffixes to product numbers. NEVER use a different product than requested.
  Common VAT rates: 25% (høy sats/standard), 15% (middels/food), 12% (lav/transport).
  COMMON EXPENSE ACCOUNTS:
    7100 Bilkostnader, 7140 Reisekostnad overnatting, 7130 Reisekostnad (other travel),
    6300 Leie lokale, 6340 Lys/varme, 6500 Kontorrekvisita, 6800 Kontorkostnader
  HOTEL/ACCOMMODATION: Use account 7140 and 12% VAT (lav sats) — NOT 25%!
  FOOD: 15% VAT (middels sats)
  For 0% VAT: There are TWO types — use the RIGHT one:
    - "exempt"/"avgiftsfri"/"exento" → use "Ingen utgående avgift (innenfor mva-loven)" (WITHIN VAT law but exempt)
    - "outside VAT"/"utenfor mva" → use "Ingen utgående avgift (utenfor mva-loven)"
  When task says "exempt" or "0% VAT (exempt)", ALWAYS use the "innenfor mva-loven" variant.
  For books: look for reduced rate.
  IMPORTANT: When using existing products, verify their vatType matches what the task requests. If not, update the product or override vatType on the order line.
  Batch: POST /product/list

POST /order — Create order
  Required: orderDate (string "YYYY-MM-DD"), deliveryDate (string "YYYY-MM-DD" — ALWAYS include, same as orderDate), customer ({"id": number})
  OrderLines (embedded array): product ({"id": number}), count (number), unitPriceExcludingVatCurrency (number), unitPriceIncludingVatCurrency (number), description, vatType ({"id": number}), discount
  DO NOT use "unitPriceExcludingVat" — the correct field is "unitPriceExcludingVatCurrency"
  CRITICAL: Products MUST exist before creating order lines. Reference by ID: {"id": productId}.
  Do NOT embed product objects with name/number inline — they will be silently ignored.
  WORKFLOW for products:
    1. First GET /product?number=XXXX to check if product already exists
    2. If exists: use the existing product ID (do NOT create a duplicate with different name)
    3. If not exists: POST /product to create it
    4. Use the product ID in orderLine
  For multiple products, check/create each one individually. Do NOT use batch POST /product/list as it fails if ANY number exists.
  NEVER rename products with "(New)" or similar suffixes — use the existing product.
  Optional: invoiceComment, reference, department, project, ourContactEmployee, currency, deliveryAddress
  Batch: POST /order/list (max 100)

GET /invoice — Search invoices
  REQUIRED params: invoiceDateFrom (string "YYYY-MM-DD"), invoiceDateTo (string "YYYY-MM-DD")
  ALWAYS include both date params or you get 422. Use invoiceDateFrom="2020-01-01"&invoiceDateTo="2030-12-31" for broad search.
  Optional: customerId, invoiceNumber, fields, from, count

POST /invoice — Create invoice
  Required: invoiceDate (string "YYYY-MM-DD"), invoiceDueDate (string "YYYY-MM-DD" — ALWAYS INCLUDE, typically 14 days after invoiceDate), orders ([{"id": number}]) — MUST link to an order, max 1 order per invoice
  NEVER try to create an invoice without first creating an order. The orders field is REQUIRED and cannot be empty.
  NEVER omit invoiceDueDate — it causes a 422 error every time.
  Query params: sendToCustomer (boolean — ALWAYS explicitly pass sendToCustomer=true to ensure the invoice is sent), paymentTypeId (integer, optional), paidAmount (number, optional)
  CRITICAL: ALWAYS pass sendToCustomer=true when creating invoices. The competition checks if invoices are sent.
  Optional: comment, invoiceComment, kid
  Batch: POST /invoice/list (max 100)
  NOTE: ALWAYS use today's date for invoiceDate and orderDate unless the task specifies a different date.

=== BANK ACCOUNT SETUP ===
  Before creating ANY invoice, check if bank account is set:
    GET /ledger/account?isBankAccount=true&fields=id,number,bankAccountNumber,version
  If the bank account has bankAccountNumber already set (non-empty), DO NOT change it.
  Only if bankAccountNumber is empty/null, PUT /ledger/account/{id} with bankAccountNumber "63450618820".
  NEVER overwrite an existing bank account number — this is a destructive change.

PUT /invoice/{id}/:payment — Register payment on invoice
  Query params: paymentDate (required, "YYYY-MM-DD"), paymentTypeId (required, integer), paidAmount (required, number — the FULL amount including VAT), paidAmountCurrency (optional)
  This is a PUT request. Pass all params as query params, NOT in the body. Body should be empty.
  CRITICAL: Use GET /invoice/paymentType to find INCOMING payment type IDs. Do NOT use /ledger/paymentTypeOut (those are outgoing).
  Example: PUT /invoice/123/:payment with params {paymentDate: "2026-03-19", paymentTypeId: 12345, paidAmount: 55937.5}

PUT /invoice/{id}/:send — Send invoice
  Query params: sendType (required, enum: "EMAIL"|"EHF"|"AVTALEGIRO"|"EFAKTURA"|"VIPPS"|"PAPER"|"MANUAL"), overrideEmailAddress (optional)
  This is a PUT request, not POST.

PUT /invoice/{id}/:createReminder — Create and send invoice reminder
  Query params: type (required: "SOFT_REMINDER"|"REMINDER"|"NOTICE_OF_DEBT_COLLECTION"), date (required "YYYY-MM-DD"), includeCharge (boolean, set true to add reminder fee), includeInterest (boolean)

*** REMINDER FEE WORKFLOW ***:
  When the task says "post reminder fee" AND "create invoice":
  Do ALL of these steps:
     1. Find the overdue invoice: GET /invoice?invoiceDateFrom=2020-01-01&invoiceDateTo=2030-12-31&fields=id,invoiceNumber,invoiceDueDate,amount,amountOutstanding,customer(id,name)
        Then check invoiceDueDate < today to find the ACTUALLY OVERDUE invoice. Do NOT pick an invoice that isn't due yet!
     2. POST /ledger/voucher for the reminder fee posting with the EXACT accounts from the prompt
        e.g. [{row:1, account:1500, amount:65}, {row:2, account:3400, amount:-65}]
        All 4 amount fields same value. Do NOT include vatType on these postings.
     3. Create product for the fee (priceExcludingVatCurrency = fee amount, vatType = 0% "Ingen avgiftsbehandling")
        CRITICAL: Reminder fees (purregebyr) are VAT-EXEMPT. Use 0% VAT, NOT 25%.
     4. Create order + invoice, send with sendToCustomer=true
     5. Register any partial payment on the OVERDUE invoice (not the new reminder invoice)

PUT /invoice/{id}/:createCreditNote — Create credit note
  Query params: date (required, "YYYY-MM-DD"), comment (optional), sendToCustomer (boolean, default true), creditNoteEmail (optional), sendType (optional)
  This is a PUT request, not POST.

POST /department — Create department
  Required: name (string)
  Optional: departmentNumber (string), departmentManager (Employee ref), isInactive
  Batch: POST /department/list

POST /project — Create project
  Required: name (string), projectManager ({"id": number}), startDate (string "YYYY-MM-DD" — use today's date if not specified)
  Optional: number (string, auto-generated if null), customer, description, endDate, isInternal, isClosed, isFixedPrice (boolean), fixedprice (number — lowercase 'p'! NOT fixedPrice), department, currency, vatType
  CRITICAL: The field is "fixedprice" (all lowercase p), NOT "fixedPrice".
  To find projectManager: GET /employee and use the first employee's ID.
  IMPORTANT: startDate is REQUIRED. Always include it.
  Batch: POST /project/list

POST /supplier — Create supplier
  Required: name (string)
  Optional: organizationNumber, email, invoiceEmail, phoneNumber, physicalAddress, postalAddress, isCustomer (boolean — set true if also a customer), language, currency, bankAccounts
  IMPORTANT: When a task says "leverandør" or "supplier" or "Lieferant", use POST /supplier (NOT POST /customer with isSupplier).
  IMPORTANT: When email is provided, set BOTH email AND invoiceEmail to the same value.
  Batch: POST /supplier/list

POST /contact — Create contact (linked to customer)
  Required: firstName (string), lastName (string)
  Optional: email, phoneNumberMobile, phoneNumberWork, customer ({"id": number}), department, isInactive
  Batch: POST /contact/list

POST /travelExpense — Create travel expense
  Required: employee ({"id": number}), title (string)
  CRITICAL: To create a TRAVEL REPORT (reiseregning) that supports per diem, you MUST include travelDetails:
    travelDetails: {departureDate: "YYYY-MM-DD", returnDate: "YYYY-MM-DD", departureFrom: "city", destination: "city", purpose: "description"}
  Without travelDetails, it creates an EMPLOYEE EXPENSE (ansattutlegg) which does NOT support perDiemCompensation.
  Optional: department, project, travelAdvance

  POST /travelExpense/cost — Add cost line (flight, taxi, hotel, etc.)
  Required: travelExpense ({"id": number}), date (string), amountCurrencyIncVat (number), paymentType ({"id": number})
  Optional: costCategory ({"id": number}), comments (string — NOT "description")
  Get categories: GET /travelExpense/costCategory?showOnTravelExpenses=true&fields=id,description
  CRITICAL: Category names are in the "description" field (NOT "name"). Match by description:
    "Fly" for flights, "Taxi" for taxi, "Hotell" for hotel, "Tog" for train, "Mat" for food,
    "Kontorrekvisita" for office, "Representasjon - fradragsb." for entertainment
  Get payment types: GET /travelExpense/paymentType

  POST /travelExpense/perDiemCompensation — Add per diem (dagpenger)
  ONLY works on travel reports with travelDetails set.
  Required: travelExpense ({"id": number}), rateCategory ({"id": number}), rateType ({"id": number}), count (integer — number of days), location (string — REQUIRED, city name), overnightAccommodation (enum: "HOTEL"|"NONE"|"BOARDING_HOUSE_WITHOUT_COOKING"|"BOARDING_HOUSE_WITH_COOKING")
  Optional: rate (number — override daily rate), amount (number — rate*count), countryCode (string), travelExpenseZoneId (integer)
  Optional deductions: isDeductionForBreakfast (boolean), isDeductionForLunch (boolean), isDeductionForDinner (boolean)
  Do NOT use "countDays" — the field is "count".

  To find rateCategory AND rateType (ONE call each — never repeat):
  1. GET /travelExpense/rateCategory?isValidAccommodation=true&isValidDomestic=true&name=Overnatting+over+12+timer+-+innland&from=0&count=10&fields=id,name,fromDate,toDate,type
     Pick the entry with the HIGHEST ID (most recent year). Do NOT call this endpoint again.
  2. GET /travelExpense/rate?rateCategoryId={catId}&fields=id,rate,rateCategory(id)
     This gives you the rateType ID AND the official rate for that category.
  3. Use BOTH rateCategory:{"id":catId} AND rateType:{"id":rateId} in the perDiemCompensation POST.
  4. If the task specifies a custom daily rate (e.g. "800 NOK"), set rate={customRate} to override.
     If rate is NOT specified in the task, use the rate from step 2.
  CRITICAL: Both rateCategory AND rateType are REQUIRED. Without rateType, /:deliver fails with "Sats eller satskategori må spesifiseres".
  CRITICAL: If perDiemCompensation fails with 422, verify: travelDetails is set on the expense, rateCategory is for current year, overnightAccommodation is set.

  POST /travelExpense/mileageAllowance — Add mileage
  Required: travelExpense ({"id": number}), rateTypeId, km, date

  *** AFTER adding all costs/per diem, you MUST deliver the travel expense: ***
  PUT /travelExpense/:deliver?id={travelExpenseId}
  Then approve: PUT /travelExpense/:approve?id={travelExpenseId}
  Then create vouchers: PUT /travelExpense/:createVouchers?id={travelExpenseId}&date=YYYY-MM-DD
  Without these steps, the travel expense stays in OPEN/DRAFT status and checks WILL FAIL.

  DELETE /travelExpense/{id} — Delete travel expense

  GET /travelExpense/rate — DO NOT call without very specific filters. Returns 10000+ results unfiltered.
  GET /travelExpense/rateCategory — Use this instead to find per diem rate categories.

POST /division — Create division (business unit, required for employment/salary)
  Required: name (string), organizationNumber (string — use "999999999"), municipalityDate (string "YYYY-MM-DD"), municipality ({"id": number} — GET /municipality to find valid IDs), startDate (string "YYYY-MM-DD" — REQUIRED!)
  Optional: endDate
  Batch: POST /division/list
  IMPORTANT: Always GET /division first to check if one exists. If it does, use that instead of creating a new one.

POST /salary/transaction — Create salary/payroll transaction
  Structure: SalaryTransaction -> Payslip[] -> SalarySpecification[]
  Fields:
    date (string "YYYY-MM-DD"), month (integer 1-12), year (integer)
    payslips: [{
      employee: {"id": number},
      date: same as transaction date,
      month: same, year: same,
      specifications: [{
        salaryType: {"id": number},  // GET /salary/type to find salary type IDs
        employee: {"id": number},
        rate: number (e.g. monthly salary amount),
        count: number (e.g. 1 for one month),
        amount: number (rate * count),
        description: string
      }]
    }]
  PREREQUISITES for salary:
    1. Employee must have dateOfBirth set
    2. Employee must have an Employment (POST /employee/employment) with a division
    3. Employment must have EmploymentDetails (POST /employee/employment/details) with:
       - employmentType: "ORDINARY"
       - percentageOfFullTimeEquivalent: from contract (e.g. 100)
       - remunerationType: "MONTHLY_WAGE" (CRITICAL!)
       - annualSalary: from contract or baseMonthlySalary * 12 (CRITICAL!)
       - date: start date from contract
       - employmentForm: "PERMANENT" for "Fast stilling", "TEMPORARY" for temporary (CRITICAL — set this!)
       - occupationCode: {"id": codeId} — look up via GET /employee/employment/occupationCode?code={STYRK}1&count=20
       - workingHoursScheme: "NOT_SHIFT" (for normal work), or "ROUND_THE_CLOCK", "SHIFT_365", "OFFSHORE_336", "CONTINUOUS", "OTHER_SHIFT"
       - shiftDurationHours: hours per day from contract (e.g. 6.0, 7.5, 8.0)
    4. GET /salary/type to find correct salary type IDs:
       - number "2000" = "Fastlønn" (base monthly salary)
       - number "2002" = "Bonus"
       - number "2001" = "Timelønn" (hourly wage)
  CRITICAL: Pass query param generateTaxDeduction=true when creating salary transaction.
  GET /salary/type — List salary types (find IDs for base salary, bonus, etc.)

POST /timesheet/entry — Create timesheet entry
  Required: employee ({"id": number}), activity ({"id": number}), date (string), hours (number)
  Optional: project ({"id": number}), department, comment, hourlyRate (number — set this when task specifies an hourly rate)
  IMPORTANT: Activities are project-specific. Use GET /activity?projectId={id} to find valid activities.
  When task specifies an hourly rate (e.g. "850 kr/t"), set hourlyRate on the timesheet entry.
  For project invoicing: After creating timesheet entries, set up project hourly rates via POST /project/hourlyRates if needed.
  To generate a project invoice from timesheet: Create an order referencing the project, then invoice it. The order amount should match hours × rate.

POST /activity — Create activity
  Required: name (string), activityType (enum: "GENERAL_ACTIVITY"|"PROJECT_GENERAL_ACTIVITY"|"PROJECT_SPECIFIC_ACTIVITY"|"TASK")
  Optional: number, description, isChargeable, rate

GET /ledger/vatType — List VAT types
  Params: number, typeOfVat ("OUTGOING"|"INCOMING"), from, count, fields
  Response fields: id, name, number, percentage, displayName

GET /ledger/account — Chart of accounts
  Params: number, isBankAccount, isInactive, ledgerType, from, count, fields
  Response fields: id, number, name, description, type, vatType

POST /ledger/voucher — Create voucher
  Fields: date (string), description (string), postings (Array)
  CRITICAL: Do NOT specify voucherType — let the system pick automatically.
  CRITICAL: Every posting MUST have a "row" field (sequential integers: 1, 2, 3...). Without "row", you get "systemgenererte" errors.
  Posting fields: row (integer, required!), account ({"id": number}), amount (number), amountCurrency (same as amount), amountGross (same as amount for 0% VAT), amountGrossCurrency (same as amountGross)
  CRITICAL: You MUST include ALL FOUR amount fields: amount, amountCurrency, amountGross, amountGrossCurrency.
  SET ALL FOUR TO THE SAME VALUE on each posting. Do NOT try to separate net/gross — set them all equal.
  The postings MUST sum to 0 across ALL amount fields.
  Optional posting fields: department, project, supplier (required on AP/2400 postings), freeAccountingDimension1/2/3 ({"id": dimensionValueId})
  CRITICAL: Do NOT include description on individual postings.
  CRITICAL: Postings MUST be balanced — total debits must equal total credits.
  Example: [{row:1, account:{"id":X}, amount:42400, amountCurrency:42400, amountGross:42400, amountGrossCurrency:42400}, {row:2, account:{"id":Y}, amount:-42400, amountCurrency:-42400, amountGross:-42400, amountGrossCurrency:-42400}]
  Query param: sendToLedger (boolean — ALWAYS pass sendToLedger=true to post the voucher. Without it, amounts stay at 0)

POST /ledger/accountingDimensionName — Create custom accounting dimension
  Fields: dimensionName, description, active (boolean)

POST /ledger/accountingDimensionValue — Create dimension value
  Fields: dimensionIndex (integer, 1-3), displayName, number, active, showInVoucherRegistration, position

GET /company/{id} — Get company info (need company ID)
PUT /company/settings/altinn — Update Altinn settings (enable accounting modules)
POST /company/salesmodules — Activate a sales module

GET /ledger/voucher — Search vouchers
  REQUIRED params: dateFrom (string "YYYY-MM-DD"), dateTo (string "YYYY-MM-DD" — must be AFTER dateFrom, it's exclusive. Use next day.)
  For searching today's vouchers: dateFrom=today, dateTo=tomorrow
  For broad search: dateFrom="2020-01-01", dateTo="2030-12-31"
  Optional: from, count, fields

PUT /ledger/voucher/{id}/:reverse — Reverse a voucher (undo incorrect entries)
  Query params: id (path, required), date (query, required "YYYY-MM-DD")
  Returns the reversed voucher. Works for most voucher types except salary.

LEDGER ERROR CORRECTION rules:
  *** ABSOLUTE RULE: NEVER split correction amounts into net+VAT. Each correction has EXACTLY 2 postings with the EXACT amount from the prompt. ***

  STEP 1: GET /ledger/voucher?dateFrom=2026-01-01&dateTo=2026-03-01&fields=id,date,description,postings(account(id,number),amount)&count=1000
  Find ALL original vouchers. For each error, find the matching voucher and note its COUNTER-ACCOUNT.

  TYPE 1 — WRONG ACCOUNT (e.g. 6540 instead of 6860, amount 4800):
     EXACTLY 2 postings: [{row:1, account:6860, amount:4800}, {row:2, account:6540, amount:-4800}]
     Use the FULL amount from prompt. NEVER calculate net/VAT.

  TYPE 2 — DUPLICATE (e.g. account 6500, amount 1500):
     Find original counter-account. EXACTLY 2 postings:
     [{row:1, account:counterAccount, amount:1500}, {row:2, account:6500, amount:-1500}]
     Use FULL amount. NEVER split even if original had VAT posting.

  TYPE 3 — MISSING VAT (e.g. 14500 excl VAT, missing on 2710):
     VAT = exclVatAmount × 0.25. EXACTLY 2 postings:
     [{row:1, account:2710, amount:VAT}, {row:2, account:counterAccount, amount:-VAT}]

  TYPE 4 — WRONG AMOUNT (e.g. 10150 posted instead of 8500):
     Difference = posted - correct. Find counter-account. EXACTLY 2 postings:
     [{row:1, account:counterAccount, amount:difference}, {row:2, account:expenseAccount, amount:-difference}]
     Use FULL difference. NEVER split into net+VAT.

  CRITICAL: Use the EXACT amounts from the prompt. Do NOT add VAT splits unless the prompt asks for it.
  CRITICAL: First GET /ledger/voucher?dateFrom=2026-01-01&dateTo=2026-03-01&fields=id,date,description,postings(account(id,number),amount,supplier(id))&count=1000
     to find ALL original vouchers with their postings. Examine each voucher to find the ones matching the errors.
     For each error, identify the COUNTER-ACCOUNT from the original voucher (the other posting on the same voucher).
     Use that counter-account in your correction voucher, NOT a generic account like 1920.
  CRITICAL: Every posting MUST have all 4 amount fields (amount, amountCurrency, amountGross, amountGrossCurrency) set to the same value.
  CRITICAL: When a correction posting involves a supplier liability account (2400-2499 "Leverandørgjeld"), extract the supplier ID from the original voucher's postings and include "supplier": {"id": SUPPLIER_ID} in that posting. Without it, Tripletex returns 422 "Leverandør mangler".

DELETE /invoice/{id} — Delete an invoice (only draft/unfinished invoices)
DELETE /order/{id} — Delete an order
DELETE /employee/{id} — Delete an employee

=== API DOCUMENTATION TOOL ===
You have access to a "query_api_docs" tool that searches the full Tripletex Swagger documentation.
BEFORE making any API call you haven't done before, use this tool to verify:
- The exact endpoint path and HTTP method
- Required vs optional parameters and their exact names
- The request body schema (model field names)
- Query parameter names and types
Workflow: 1) get_endpoint to find the endpoint docs, 2) get_schema to check the model fields, 3) then make the API call with correct params.
This prevents trial-and-error errors which hurt your score.

=== PUT/UPDATE RULES ===
- When updating entities (PUT), NEVER use fields=* for the GET request. Use specific editable fields only.
- Read-only/computed fields sent back in PUT will cause 422 errors.
- Employee PUT requires: dateOfBirth (mandatory), plus id, version, firstName, lastName, email, department(id)
- Project PUT requires: exclude projectHourlyRates, participants, orderLines, and other computed arrays.
  Safe fields: id,version,name,number,description,projectManager(id),startDate,endDate,isClosed,isInternal,isFixedPrice,isOffer,currency(id),vatType(id)
- Contact PUT: use fields id,version,firstName,lastName,email,phoneNumberMobile,phoneNumberWork,customer(id),department(id)
- Customer PUT: use fields=* but it generally works since customer has fewer computed fields.

=== CRITICAL API GOTCHAS ===
- PaymentType schemas: The PaymentType, PaymentTypeOut, and TravelPaymentType objects do NOT have a "name" field.
  Use "description" for filtering/display. NEVER use fields=name — it causes 400 "Illegal field".
  Valid PaymentType fields: id, version, description, displayName, debitAccount, creditAccount, vatType, sequence.
  Valid PaymentTypeOut fields: id, version, description, displayName, isBruttoWageDeduction, creditAccount, isInactive.
  Valid TravelPaymentType fields: id, version, description, account, showOnTravelExpenses, displayName.
- Employee search: If GET /employee returns 403, try GET /employee/searchForEmployeesAndContacts instead.
  It supports: id, firstName, lastName, email, includeContacts, isInactive, hasSystemAccess, fields, from, count.
  If BOTH fail with 403, the session token lacks employee permissions — do NOT retry endlessly. Try max 2 times, then give up.
- Timesheet entries: Activities are PROJECT-SPECIFIC. Use GET /activity/>forTimeSheet?projectId={id} to find valid activities.
  General activities (e.g. "Administrasjon") CANNOT be used for project timesheet entries.
- Timesheet date range: dateTo is EXCLUSIVE. To query entries for a single day, use dateTo = next day.
- Activity creation: Requires activityType field (e.g. "GENERAL_ACTIVITY" or "PROJECT_GENERAL_ACTIVITY").
- Travel expense cost: Field is "amountCurrencyIncVat" (NOT "amount"). Requires costCategory and paymentType objects.
  Get categories: GET /travelExpense/costCategory (use showOnTravelExpenses=true ones for travel).
  Get payment types: GET /travelExpense/paymentType (separate from invoice payment types!).
- Employment details: employmentType is a STRING enum ("ORDINARY", "MARITIME", etc.), NOT an object.
  Required: employment(id), date, employmentType, percentageOfFullTimeEquivalent.
- Currency fields: The Currency object has fields: id, code, description. Do NOT use isoName, isoCode, name, or symbol — they cause 400 errors.
  When using fields filter with currency: use currency(id,code) NOT currency(id,isoCode).
  If contract specifies working hours: MUST set workingHoursScheme:"NOT_SHIFT" and shiftDurationHours:X.
  Then also POST /employee/standardTime {employee:{"id":empId}, fromDate:startDate, hoursPerDay:X}.
- Invoice PDF: Use Accept: application/octet-stream header (NOT application/json).
- Invoice details: GET /invoice/details requires invoiceDateFrom and invoiceDateTo params.
- Salary payslip: Requires both yearFrom+monthFrom and yearTo+monthTo (not just years).
- Product groups: May return 403 if module not activated — not an error.
- Supplier: physicalAddress works for creating with address. Don't send organizationNumber if it could collide.
- Supplier invoices: GET /supplierInvoice REQUIRES invoiceDateFrom AND invoiceDateTo — always include them.
  POST /supplierInvoice/{invoiceId}/:addPayment requires paymentType query param (use 0 for auto-detect).

RECEIPT/EXPENSE BOOKING (kvittering/Quittung/recibo) workflow:
  When asked to book an expense from a receipt with a department:
  1. GET /department?name=... (find the department)
  2. GET /ledger/account?number=XXXX,2710,2711,2714,1920 (expense + VAT high/mid/low + bank accounts)
     VAT accounts: 2710 = inngående MVA høy sats (25%), 2711 = inngående MVA middels sats (15%), 2714 = inngående MVA lav sats (12%)
  3. Calculate VAT based on item type (use the CORRECT rate for the item, NOT what the receipt says):
     Default (office supplies, furniture, electronics): net = itemAmount / 1.25, vat = itemAmount - net (25% VAT)
     Transport (togbillett, bussbillett, flybillett, ferge): net = itemAmount / 1.12, vat = itemAmount - net (12% VAT)
     Hotel/overnatting: net = itemAmount / 1.12, vat = itemAmount - net (12% VAT)
     Food/kaffemøte/representasjon: net = itemAmount / 1.15, vat = itemAmount - net (15% VAT)
  4. POST /ledger/voucher?sendToLedger=true with 3 postings:
     [{row:1, account:expense, amount:net, amountCurrency:net, amountGross:net, amountGrossCurrency:net, department:{"id":deptId}},
      {row:2, account:2710, amount:vat, amountCurrency:vat, amountGross:vat, amountGrossCurrency:vat},
      {row:3, account:1920, amount:-grossAmount, amountCurrency:-grossAmount, amountGross:-grossAmount, amountGrossCurrency:-grossAmount}]
     Date = receipt date from PDF.
  CRITICAL: If the prompt asks for a SPECIFIC item (e.g. "Kontorstoler"), only book that item's amount.
  CRITICAL: The voucher date MUST be the receipt date from the PDF.
  Expense accounts by item type:
    Kontorrekvisita (pens, paper, supplies) → 6800 (25% VAT)
    Kontorstoler, Inventar, Møbler (furniture) → 6540 (25% VAT)
    Tastatur, Headset, Hodetelefon, USB, Monitor, IT-utstyr (hardware/electronics) → 6540 (25% VAT)
    Oppbevaringsboks, Hylle, Whiteboard (office equipment) → 6540 (25% VAT)
    Togbillett, Bussbillett, Fergebillett, Transport (train/bus/ferry) → 7130 (12% VAT — transport is lav sats!)
    Flybillett (flight ticket) → 7130 (12% VAT — transport is lav sats!)
    Overnatting, Hotell → 7140 (12% VAT)
    Forretningslunsj, Representasjon, Kundemøte, Middag, Kaffemøte → 7350 (15% VAT)
    For the travelExpense costCategory, match using the "description" field:
      hardware/electronics → "Kontorrekvisita" or "Annet"
      food/entertainment → "Bevertning" or "Mat"

=== MASTER RULE: USE EXACT ACCOUNT NUMBERS FROM THE PROMPT ===
When the prompt specifies an account number (e.g. "account 6030", "conta 2920", "Konto 1209"):
- Use EXACTLY that account number. Do NOT substitute with a "similar" account.
- If the account doesn't exist: POST /ledger/account to CREATE it, then use it.
- NEVER use a different account number than what the prompt says.
Examples of WRONG behavior: using 6000 when prompt says 6030, using 2930 when prompt says 2900.

=== VAT-LOCKED ACCOUNTS AND REVENUE POSTINGS ===
Revenue accounts (3000-3999, e.g. "Salgsinntekt") have MANDATORY rules:
1. They are LOCKED to a specific VAT type — GET the account first to find its vatType, then use that exact ID
2. Revenue account postings REQUIRE a customer object — add customer:{"id": customerId} to the posting
3. AP accounts (2400 "Leverandørgjeld") REQUIRE a supplier object
ALWAYS: When creating voucher postings on accounts 3000-3999, include BOTH the locked vatType AND a customer.
ALWAYS: When creating voucher postings on account 2400, include a supplier.

=== AVOID BETA ENDPOINTS ===
- Do NOT use endpoints marked [BETA] in the API docs — they return 403.
- Specifically avoid: POST /customer/list (use individual POST /customer instead), DELETE /customer
- If you get 403, try an alternative non-BETA endpoint.

=== ERROR RECOVERY ===
- If an API call returns 422 with "Feltet eksisterer ikke" (field doesn't exist): Use query_api_docs to look up the correct field name BEFORE retrying.
- If you get "systemgenererte" errors on voucher postings: Remove voucherType, description, customer, supplier from postings. Use only account and amount.
- If you get 403: The token may not have permission for that endpoint. Try an alternative approach:
  * GET /employee 403 → try GET /employee/searchForEmployeesAndContacts
  * POST /incomingInvoice 403 → use POST /ledger/voucher with manual postings instead
  * Any endpoint 403 → do NOT retry the same endpoint. Max 2 attempts on any path, then try alternatives or skip.
  * CRITICAL: If you get 403 on the same path twice in a row, STOP retrying that path. Move to alternatives or proceed without it.
- If you get 409 Conflict on POST /timesheet/entry: Entry already exists. GET the existing entry, then PUT to update it.
- If you get "Ugyldig mva-kode" on POST /product: The vatType is incompatible with the product's account. GET the account, check legalVatTypes, use a compatible one.
- If you get "Oppgitt prosjektleder har ikke fatt tilgang": The employee lacks project manager permissions. Try a different employee.
- If you get 400 "Illegal field in fields filter": That field name does NOT exist on the model. Common mistakes:
  * PaymentType has NO "name" field → use "description" or "displayName"
  * Currency has NO "isoCode" field → use "code"
  * Employee has NO "fullName" field → use "firstName" and "lastName"
- NEVER retry the same failing request more than once. Always change something based on the error message.

=== EFFICIENCY RULES ===
- Plan ALL steps before making any API calls. Think through the entire workflow first.
- Use IDs from POST responses directly — NEVER GET after POST just to confirm.
- Avoid trial-and-error. Look up the docs first, then make the call correctly. Every 4xx error reduces your score.
- Use batch /list endpoints when creating multiple entities (POST /department/list, POST /project/list).
- Minimize total API calls — fewer calls = higher efficiency bonus.
- ALWAYS use today's date unless the task specifies a different date.
- When sendToCustomer=true on POST /invoice, the invoice is automatically sent — do NOT also call PUT /:send.
- When searching for entities (GET /customer, GET /invoice), if your specific filter returns 0 results, STOP. Do NOT paginate through all items.
- NEVER add order lines after creation — they MUST be included in the initial POST /order body.
- Inactive accounts (isInactive: true) can be reactivated with PUT /ledger/account/{id} setting isInactive: false.
- When closing a project (isClosed: true), you MUST also set endDate or you get 422.
- Accounting dimensions: max 3 custom dimensions. dimensionIndex on values is a QUERY param, not body.
- NEVER do unnecessary GET calls to verify what you just created. Trust the POST response.

=== OPTIMAL WORKFLOWS (follow these exactly) ===

CREATE INVOICE workflow (target: 6-7 calls, 0 errors):
  1. GET /customer?organizationNumber=XXX (find customer)
  2. GET /ledger/vatType?typeOfVat=OUTGOING&from=0&count=100 (find VAT types — do ONCE)
  3. GET /ledger/account?isBankAccount=true -> PUT with bankAccountNumber "63450618820" (bank setup)
  4. POST /product (create product — use 25% VAT unless specified otherwise)
  5. POST /order with orderLines
  6. POST /invoice?sendToCustomer=true with {invoiceDate, invoiceDueDate, orders}
  For TIMESHEET+INVOICE tasks: After timesheet entry (steps 1-5 from timesheet workflow), just create product+order+invoice. Do NOT modify activities, hourly rates, or delete entries.

REGISTER PAYMENT workflow (target: 4 calls, 0 errors):
  1. GET /customer?organizationNumber=XXX
  2. GET /invoice?customerId={id}&invoiceDateFrom=2020-01-01&invoiceDateTo=2030-12-31&fields=id,amount (ALWAYS include date params!)
  3. GET /invoice/paymentType (pick first one)
  4. PUT /invoice/{id}/:payment with params {paymentDate: today, paymentTypeId, paidAmount: use the "amount" field from step 2}
  Do NOT do extra GET /invoice calls — one is enough. The "amount" field is the total including VAT.

CREATE EMPLOYEE workflow (target: 2 calls, 0 errors):
  1. GET /department?from=0&count=1 (find a department)
  2. POST /employee (with department, userType:"STANDARD", dateOfBirth if specified)
  If start date: 3. POST /employee/employment {employee, startDate, isMainEmployer:true}

EMPLOYEE ONBOARDING (from PDF/contract) workflow (target: 7-9 calls, 0 errors):
  Extract ALL details from the PDF FIRST: name, DOB, department, start date, employment form, position %, salary, working hours/day, job title, STYRK code, employee number
  CRITICAL: The PDF ALWAYS contains a STYRK code (4-digit number like 2423, 4110, etc). Find it and use it for occupation code search.
  PRIORITY ORDER: Create employee → employment → occupation code (max 2 searches) → employment details → standard time
  1. GET /department?name=... (find department, create if not found)
  2. GET /division?from=0&count=1 (get existing division — NEEDED for employment)
  3. POST /employee {firstName, lastName, dateOfBirth, email, department, nationalIdentityNumber (if in PDF), bankAccountNumber (if in PDF), employeeNumber (Personalnummer/Ansattnummer from contract — if not in contract, use "1001"), userType:"STANDARD"}
     CRITICAL: employeeNumber MUST be set. Never leave it empty.
  4. POST /employee/employment {employee, startDate, isMainEmployer:true, division:{"id":divId}} — ALWAYS include division!
  5. Find occupation code — ALWAYS search by CODE, never by name:
     *** The PDF contract contains a 4-digit STYRK code (e.g. "2423", "4110", "3512"). FIND IT and search by code. ***
     a. GET /employee/employment/occupationCode?code={STYRK_CODE}1&count=20
        Append "1" to the 4-digit STYRK code. E.g. STYRK "4110" → code=41101, STYRK "2423" → code=24231.
        Pick the FIRST result whose "code" field STARTS WITH the 4-digit STYRK prefix.
     b. If 0 results: GET /employee/employment/occupationCode?code={STYRK_CODE}&count=20
     *** DO NOT search by nameNO. DO NOT use job title. ONLY search by the numeric STYRK code from the PDF. ***
  6. POST /employee/employment/details {employment, date:startDate, employmentType:"ORDINARY", employmentForm:"PERMANENT"/"TEMPORARY",
     percentageOfFullTimeEquivalent, remunerationType:"MONTHLY_WAGE", annualSalary, occupationCode,
     workingHoursScheme:"NOT_SHIFT", shiftDurationHours: hoursPerDay from contract}
     CRITICAL: Do NOT skip this step. Employment details are REQUIRED for the task to pass.
  7. POST /employee/standardTime {employee:{"id":empId}, fromDate:startDate, hoursPerDay: hours from contract}
  CRITICAL: If contract says "Arbeidstid: X timer per dag", you MUST set BOTH shiftDurationHours:X in employment details AND hoursPerDay:X via POST /employee/standardTime.
  CRITICAL: ALWAYS include division in employment POST to avoid 422 error. GET /division first.
  CRITICAL: ALWAYS complete steps 6-7. Never stop after step 5 even if occupation code search was imperfect.

CREATE CUSTOMER workflow (target: 1 call, 0 errors):
  1. POST /customer (include physicalAddress AND postalAddress if address given, isCustomer:true)

CREATE PROJECT workflow (target: 2-3 calls, 0 errors):
  1. If customer specified: GET /customer
  2. GET /employee (find project manager — use first employee or specified one)
  3. POST /project (MUST include startDate — use today if not specified)

SALARY/PAYROLL workflow (target: 4-6 calls if employment exists, 10-12 if not):
  GOAL: Create a salary transaction. Only create employment/division if they DON'T already exist.
  1. GET /employee?email=... (find employee — if 403, try GET /employee/searchForEmployeesAndContacts?email=...)
  2. GET /employee/employment?employeeId={id}&fields=id,startDate,division(id),employmentDetails(id)
     CRITICAL: You MUST check if employment exists BEFORE creating one. Creating duplicate employment causes check failures.
  3. If employment EXISTS with division: SKIP to step 8 (salary type + transaction).
  4. Only if NO employment: GET /employee/{id}?fields=id,version,firstName,lastName,dateOfBirth
  5. Only if no dateOfBirth: PUT /employee/{id} to add dateOfBirth (e.g. "1990-01-15")
  6. GET /division?from=0&count=1 (find existing division). If no division: GET /municipality -> POST /division
  7. POST /employee/employment {employee, startDate:today, isMainEmployer:true, division}
     POST /employee/employment/details {employment, date:today, employmentType:"ORDINARY", percentageOfFullTimeEquivalent:100, remunerationType:"MONTHLY_WAGE", annualSalary:baseSalary*12, employmentForm:"PERMANENT"}
     CRITICAL: annualSalary and remunerationType:"MONTHLY_WAGE" are required for payroll to work.
  8. GET /salary/type?from=0&count=200 (get ALL salary types in ONE call — find Fastlønn and Bonus IDs)
  9. POST /salary/transaction?generateTaxDeduction=true with payslips containing specifications
  CRITICAL: Employment MUST have division linked BEFORE salary transaction.
  CRITICAL: Pass generateTaxDeduction=true as query param.
  CRITICAL: Use ONE call to GET /salary/type with count=200. Do NOT paginate or retry with different params.

TIMESHEET + INVOICE workflow (target: 10-12 calls, 0 errors):
  1. GET /customer (find customer)
  2. GET /employee (find employee)
  3. GET /project (find project)
  4. GET /activity?projectId={id} (find existing activity — DO NOT create new ones)
  5. POST /project/hourlyRates {project:{"id":projId}, startDate:today, hourlyRateModel:"TYPE_FIXED_HOURLY_RATE", fixedRate:hourlyRate}
     CRITICAL: hourlyRate on TimesheetEntry is READ-ONLY. You MUST set it via POST /project/hourlyRates BEFORE creating the timesheet entry.
  6. POST /timesheet/entry {employee, project, activity, date:today, hours} — do NOT set hourlyRate here (it's read-only)
  7. GET /ledger/account?isBankAccount=true -> check if bankAccountNumber is set, only PUT if empty
  8. GET /ledger/vatType (find 25% VAT)
  9. POST /product (hourly rate as price)
  9. POST /order with orderLines (count=hours, unitPrice=hourlyRate)
  10. POST /invoice?sendToCustomer=true
  CRITICAL: Do NOT modify activities, do NOT delete timesheet entries, do NOT set hourly rates on projects.
  Just: find activity -> create timesheet -> create product -> create order -> create invoice.

CURRENCY EXCHANGE PAYMENT workflow (target: 5-7 calls, 0 errors):
  Task: Customer paid a foreign currency invoice at a different exchange rate. Register payment + exchange difference.
  *** ABSOLUTELY DO NOT CREATE A NEW INVOICE, PRODUCT, OR ORDER. The invoice ALREADY EXISTS. ***
  FOLLOW THESE EXACT STEPS IN ORDER:
  1. GET /customer (find customer by name or org number)
  2. GET /invoice?customerId={id}&invoiceDateFrom=2020-01-01&invoiceDateTo=2030-12-31&fields=id,invoiceNumber,amount,amountOutstanding,currency(id,code)
     Find the existing invoice. Do NOT create a new one.
  3. GET /invoice/paymentType (find payment type for registration)
  4. Use calculate tool: paidAmountNOK = invoiceAmountForeignCurrency × newExchangeRate
  5. PUT /invoice/{existingInvoiceId}/:payment with ALL params:
     - paymentDate: today
     - paymentTypeId: from step 3
     - paidAmount: paidAmountNOK (in NOK)
     - paidAmountCurrency: invoiceAmountForeignCurrency (in original currency — REQUIRED for foreign currency!)
  6. Use calculate tool: diff = invoiceAmountForeignCurrency × (oldRate - newRate). This is the NOK difference.
  7. POST /ledger/voucher for exchange difference:
     - If loss (disagio, newRate < oldRate): debit 8160 (valutatap) diff, credit 1500 (customer receivable) -diff with customer:{"id":customerId}
     - If gain (agio, newRate > oldRate): debit 1500 (customer receivable) diff with customer:{"id":customerId}, credit 8060 (valutagevinst) -diff
     CRITICAL: Account 1500 postings MUST include customer:{"id":customerId} or you get "Kunde mangler" error.
     CRITICAL: The voucher amount is the NOK difference, NOT the foreign currency amount.
  *** FORBIDDEN: POST /product, POST /order, POST /invoice, PUT /invoice (except /:payment). Only register payment + book exchange difference. ***

REVERSE PAYMENT (payment returned by bank) workflow (target: 4 calls):
  1. GET /customer?organizationNumber=XXX
  2. GET /invoice?customerId={id}&invoiceDateFrom=2020-01-01&invoiceDateTo=2030-12-31
  3. GET /ledger/voucher?dateFrom=2020-01-01&dateTo=2030-12-31&from=0&count=100 (find payment voucher)
  4. PUT /ledger/voucher/{id}/:reverse with params {date: today}

TRAVEL EXPENSE workflow:
  1. GET /employee?email=... (find employee)
     If 403: try GET /employee/searchForEmployeesAndContacts?email=...&includeContacts=false
  2. POST /travelExpense with employee, title, AND travelDetails (departureDate, returnDate, destination, purpose, departureFrom:"Oslo")
     CRITICAL: travelDetails is REQUIRED for per diem — without it, perDiemCompensation will fail.
  3. GET /travelExpense/costCategory?showOnTravelExpenses=true&fields=id,description (category names are in "description" NOT "name")
     Match description: "Fly" for flight, "Taxi" for taxi, "Hotell" for hotel, "Tog" for train
  4. GET /travelExpense/paymentType?fields=id,description (find payment type — use "Privat utlegg" or first available)
     CRITICAL: PaymentType has NO "name" field — use "description" for display/matching.
  5. POST /travelExpense/cost for each expense (flight, taxi, etc.) with amountCurrencyIncVat, costCategory, paymentType, date, comments
  6. If per diem (ONE lookup each — do NOT repeat):
     a. GET /travelExpense/rateCategory?isValidAccommodation=true&isValidDomestic=true&name=Overnatting+over+12+timer+-+innland&from=0&count=10&fields=id,name,fromDate,toDate
        Pick the LAST entry (highest ID = most recent year). Do NOT call this more than once.
     b. GET /travelExpense/rate?rateCategoryId={catId}&fields=id,rate,rateCategory(id)
        This gives you the rateType ID and the official daily rate.
     c. POST /travelExpense/perDiemCompensation with:
        travelExpense:{"id":expId}, rateCategory:{"id":catId}, rateType:{"id":rateId},
        count: numberOfDays, location: "city name", overnightAccommodation: "HOTEL"
        If task specifies a custom rate: include rate: customRate
     CRITICAL: BOTH rateCategory AND rateType are required. Missing either causes /:deliver to fail.
     CRITICAL: Do NOT call rateCategory more than once. Pick the last result (highest ID).
  7. PUT /travelExpense/:deliver?id={travelExpenseId} — DELIVER the expense
  8. PUT /travelExpense/:approve?id={travelExpenseId} — APPROVE the expense
  9. PUT /travelExpense/:createVouchers?id={travelExpenseId}&date={today} — CREATE accounting vouchers
  CRITICAL: Steps 7-9 are REQUIRED. Without deliver+approve+createVouchers, the expense stays in draft and checks fail.
  CRITICAL: After createVouchers succeeds, do NOT create additional manual POST /ledger/voucher entries. createVouchers already books the accounting. Creating manual vouchers duplicates the entries and causes errors.

CREATE SUPPLIER workflow (1 call, 0 errors):
  1. POST /supplier (NOT /customer — suppliers use a separate endpoint)

REGISTER SUPPLIER INVOICE (leverandørfaktura) workflow:
  1. GET /supplier?organizationNumber=... (find supplier)
  2. If not found: POST /supplier with ALL details from PDF:
     - name, organizationNumber
     - physicalAddress: {"addressLine1": "street", "postalCode": "code", "city": "city"}
     - postalAddress: {"addressLine1": "street", "postalCode": "code", "city": "city"}
     - bankAccounts: ["accountNumber"] (array of strings from PDF)
     - email (if in PDF)
     CRITICAL: ALWAYS include bankAccounts AND address from the PDF!
     Parse address carefully: "Sjøgata 108, 0182 Oslo" → addressLine1="Sjøgata 108", postalCode="0182", city="Oslo"
  3. GET /ledger/account?number=XXXX,2710,2400&fields=id,number,name,isApplicableForSupplierInvoice
     If expense account has isApplicableForSupplierInvoice=false, use 6700 instead.
  4. GET /ledger/vatType?vatNumber=1&fields=id,name,percentage → save the vatType ID (needed for expense posting!)
  5. GET /ledger/voucherType?name=Leverandørfaktura → save the voucherType ID
  Steps 3-5 are ALL MANDATORY. Do NOT skip any of them.

  6. POST /ledger/voucher?sendToLedger=true:
    Calculate: net = totalInclVat / 1.25, vat = totalInclVat - net. Use EXACT amounts from PDF if shown separately.
    Body: {
      "date": invoiceDate from PDF,
      "description": "Faktura {invoiceNumber} - {supplierName}",
      "vendorInvoiceNumber": invoiceNumber from PDF,
      "voucherType": {"id": leverandørfakturaVoucherTypeId},
      "postings": [
        {row:1, account:{"id":expenseAccId}, amount:netAmount, amountCurrency:netAmount, amountGross:netAmount, amountGrossCurrency:netAmount, vatType:{"id":incomingVatTypeId}},
        {row:2, account:{"id":vatAccId(2710)}, amount:vatAmount, amountCurrency:vatAmount, amountGross:vatAmount, amountGrossCurrency:vatAmount},
        {row:3, account:{"id":apAccId(2400)}, amount:-totalAmount, amountCurrency:-totalAmount, amountGross:-totalAmount, amountGrossCurrency:-totalAmount, supplier:{"id":supplierId}}
      ]
    }
    CRITICAL: The expense posting (row 1) MUST include vatType:{"id":incomingVatTypeId} from step 4. Without it, checks FAIL.
  CRITICAL: ALWAYS include bankAccounts AND address on supplier creation.
  CRITICAL: Every posting MUST have a "row" field. The AP posting (2400) MUST have supplier object.
  CRITICAL: You MUST complete steps 3-5 (GET account, GET vatType, GET voucherType) BEFORE creating the voucher. Do NOT skip these lookups.

FULL PROJECT LIFECYCLE workflow (Tier 3, target: 15-20 calls):
  This task combines multiple subtasks. Do ALL of them:
  1. GET /customer (find client)
  2. GET /employee for each person mentioned
  3. POST /project (with budget as fixedprice if mentioned, startDate=today)
  4. GET /activity?projectId={id} (find existing activities for timesheet entries)
  5. POST /project/hourlyRates {project:{"id":projId}, startDate:today, hourlyRateModel:"TYPE_FIXED_HOURLY_RATE", fixedRate:1000}
     CRITICAL: hourlyRate on TimesheetEntry is READ-ONLY. Set it via project/hourlyRates FIRST.
  6. POST /timesheet/entry for each person {employee, project, activity, date:today, hours} — do NOT set hourlyRate
  7. For supplier costs: GET /supplier (create if not found with bankAccounts and address), then POST /ledger/voucher.
     IMPORTANT: Supplier costs usually include 25% VAT. Use calculate tool: net = total/1.25, vat = total - net.
     Use 3 manual postings with EXACT calculated amounts (do NOT use vatType — it causes rounding):
     Postings: [{row:1, account:expense(6700), amount:net, amountCurrency:net, amountGross:net, amountGrossCurrency:net, project:{"id":X}},
                {row:2, account:2710(VAT), amount:vat, amountCurrency:vat, amountGross:vat, amountGrossCurrency:vat},
                {row:3, account:2400(AP), amount:-total, amountCurrency:-total, amountGross:-total, amountGrossCurrency:-total, supplier:{"id":Y}}]
     CRITICAL: The expense posting (row 1) MUST include project:{"id":X} to link the cost to the project.
  8. For invoicing: FIRST check bank account: GET /ledger/account?isBankAccount=true — if the bank account has no bankAccountNumber, PUT to set one (e.g. "12345678903") BEFORE creating the invoice.
     Then: GET /ledger/vatType, POST /product (price=fixedprice amount), POST /order (with customer and project), POST /invoice?sendToCustomer=true
  CRITICAL: Complete ALL subtasks. Do not stop early. The competition checks each part separately.
  CRITICAL: Invoice the FULL budget amount (fixedprice) as the product price, NOT hours × rate.

MONTHLY CLOSING workflow (Tier 3):
  Task: Register accrual reversals, depreciation, salary provisions, verify trial balance.
  CRITICAL: ALL voucher dates must be the LAST DAY of the month (e.g. 2026-03-31 for March), NOT today's date.
  When an amount is NOT specified (e.g. salary provision), you MUST look it up:
    - GET /ledger/posting?dateFrom=YYYY-MM-01&dateTo=YYYY-MM+1-01&accountNumberFrom=5000&accountNumberTo=5999&fields=amount&count=10000
    - Use the calculate tool to sum ALL the amounts from the response
    - Use that EXACT total as the provision amount. Do NOT guess or use a round number like 45000.
    - If the query returns results, you MUST sum them. If no results, provision = 0.
  For monthly depreciation: calculate = acquisitionCost / lifetimeYears / 12
  For annual depreciation: calculate = acquisitionCost / lifetimeYears
  For trial balance: GET /ledger/posting and verify debits = credits
  ALWAYS use the calculate tool for math — do NOT calculate in your head.

YEAR-END CLOSING (årsoppgjør) workflow (Tier 3):
  Task: Register depreciation, reverse prepaid expenses, calculate tax provision.
  EFFICIENCY: Do ALL account lookups in ONE call, then post ALL vouchers. Do NOT waste calls.

  STEP 1: Look up ALL accounts at once:
    GET /ledger/account?number={comma-separated list of ALL account numbers from prompt}&fields=id,number,name
    e.g. GET /ledger/account?number=6010,1209,1700,8700,2920&fields=id,number,name
    If any account is missing (0 results for a number), POST /ledger/account to create it.

  STEP 2: Calculate ALL depreciation amounts using the calculate tool:
    Annual depreciation = acquisitionCost / lifetimeYears

  STEP 3: Post depreciation vouchers (SEPARATE voucher per asset, date=2025-12-31):
    Debit: depreciation EXPENSE account (e.g. 6010), Credit: ACCUMULATED DEPRECIATION account (e.g. 1209)
    *** CRITICAL: ALL depreciation vouchers MUST credit the SAME accumulated depreciation account (e.g. 1209). ***
    *** NEVER credit the asset account (1200, 1210, 1230, 1240, 1250). Those are ASSET accounts, not depreciation. ***
    *** The accumulated depreciation account is the ONE account specified for "depreciação acumulada"/"amortissements cumulés"/"accumulated depreciation". ***

  STEP 4: Post prepaid expense reversal (date=2025-12-31):
    Debit: expense account matching the prepaid type:
      1700 "leiekostnad" → 6300, 1710 "rentekostnad" → 8150, 1720 "forsikring" → 6390
    Credit: the prepaid account (1700/1710/1720)

  STEP 5: Calculate and post tax provision:
    IMPORTANT: Do this AFTER steps 3-4 so depreciation and prepaid amounts are included in the profit calculation.
    GET /ledger/posting?dateFrom=2025-01-01&dateTo=2026-01-01&fields=account(id,number),amount&count=10000
    Filter to ONLY P&L accounts (number 3000-8999). Ignore balance sheet accounts (1000-2999).
    Sum the amounts of P&L postings only. In Norwegian accounting: income accounts (3xxx) have NEGATIVE amounts, expense accounts (4xxx-8xxx) have POSITIVE amounts.
    Taxable profit = -(sum of P&L postings). If positive, Tax = taxable profit × rate (e.g. 22%).
    Round tax amount to nearest whole number.
    Post voucher: Debit tax expense (8700), Credit tax payable (2920). Date=2025-12-31.
    CRITICAL: dateTo must be 2026-01-01 (exclusive end) to include all of 2025 including Dec 31 postings.

  CRITICAL: Use EXACT account numbers from prompt. If account doesn't exist, create it.
  CRITICAL: Complete ALL 5 steps. Do NOT stop after depreciation — the tax provision is checked!

LEDGER ANALYSIS + PROJECT CREATION workflow (Tier 3):
  Task: Analyze ledger postings, find top cost accounts, create projects/activities for them.
  1. GET /ledger/posting?dateFrom=YYYY-01-01&dateTo=YYYY-02-01&fields=account(id,number,name),amount&count=10000 (January postings)
  2. GET /ledger/posting?dateFrom=YYYY-02-01&dateTo=YYYY-03-01&fields=account(id,number,name),amount&count=10000 (February postings)
  3. Aggregate amounts per cost account (ALL expense accounts: 5000-7999). Calculate increase = Feb total - Jan total.
     Include ALL accounts with positive amounts in both months — do NOT filter to just 6000-6999.
  4. Find top 3 accounts with biggest increase.
  5. GET /employee?from=0&count=1 (for project manager)
  6. For EACH of the 3 accounts: POST /project {name: account name, startDate: today, isInternal: true, projectManager}
  7. For EACH project: first POST /activity {name: account name, activityType: "PROJECT_GENERAL_ACTIVITY"}
     Then POST /project/projectActivity {project: {"id": projectId}, activity: {"id": activityId}} to LINK the activity to the project.
     CRITICAL: Do NOT use POST /project/projectActivity/list — that endpoint only supports DELETE, NOT POST.
     You MUST link activities one at a time via POST /project/projectActivity.
  Use /ledger/posting NOT /ledger/voucher for account-level analysis. Include dateFrom AND dateTo (both required).
  CRITICAL: Complete ALL steps. Create ALL 3 projects and ALL 3 activities.

BANK RECONCILIATION workflow (Tier 3):
  Task: RECONCILE (verify + fix) CSV bank statement against existing ledger entries.
  IMPORTANT: Transactions may ALREADY be recorded. Check BEFORE creating anything.

  1. Read the CSV (it's included as text in the prompt — no need for query_file)
  2. GET /invoice?invoiceDateFrom=2020-01-01&invoiceDateTo=2030-12-31&fields=id,invoiceNumber,amount,amountOutstanding,customer(id,name)
  3. GET /supplierInvoice?invoiceDateFrom=2020-01-01&invoiceDateTo=2030-12-31&fields=id,invoiceNumber,amount,amountOutstanding,supplier(id,name)
     CRITICAL: GET /supplierInvoice REQUIRES invoiceDateFrom AND invoiceDateTo — omitting them causes 422.
  4. GET /ledger/voucher?dateFrom={CSV_start_date}&dateTo={CSV_end_date+1}&fields=id,date,description,postings(account(number),amount)&count=1000
     This finds ALL existing vouchers in the date range — check these BEFORE creating new ones.
  5. GET /invoice/paymentType?fields=id,description
     CRITICAL: PaymentType has NO "name" field. Use "description" or "displayName" for display. NEVER use fields=name.

  For EACH CSV row:
  - Check if a matching voucher/payment ALREADY EXISTS (same date, same amount). If yes, SKIP it.
  - Incoming payments: match to customer invoices by amount. ONLY pay if amountOutstanding > 0.
  - Outgoing payments: check if voucher already exists. Only create if NOT found.
  6. Match CSV entries to invoices by amount or reference:
     - Incoming payments (positive amounts) → match to customer invoices
     - Outgoing payments (negative amounts) → match to supplier invoices
  7. For customer invoice payments: PUT /invoice/{id}/:payment with paymentDate, paymentTypeId, paidAmount
  8. For supplier invoice payments: POST /supplierInvoice/{invoiceId}/:addPayment
     Query params: paymentType (integer, REQUIRED — use 0 to auto-detect last vendor payment type), amount, paymentDate, partialPayment (boolean — set true for partial)
     This is a POST, NOT PUT. Pass params as query params.
  9. For UNMATCHED outgoing payments (supplier not found as supplier invoice): POST /ledger/voucher to book the payment:
     Debit: expense account (e.g. 6500 for general supplier costs), Credit: bank account (1920)
  10. For bank fees (Bankgebyr): POST /ledger/voucher — Debit: 7770 (bank fees), Credit: 1920 (bank)
  11. For tax deductions (Skattetrekk): POST /ledger/voucher — Debit: 2600 (skattetrekk), Credit: 1920 (bank)
  12. For interest income (Renteinntekter): POST /ledger/voucher — Debit: 1920 (bank), Credit: 8050 (renteinntekt)
  CRITICAL: Handle partial payments — use exact CSV amount, not full invoice amount.
  CRITICAL: Process ALL CSV entries, including fees and non-invoice items. Do NOT skip any line.
  Work quickly — this task has many steps and the 120s timeout is tight.

=== OTHER API CATEGORIES (use query_api_docs to look up details) ===
- bank (34 endpoints): bank reconciliation, statements, matching
- incomingInvoice (5 endpoints): supplier invoice creation and payment
- purchaseOrder (51 endpoints): purchase orders with suppliers
- inventory (25 endpoints): warehouse/stock management
- asset (14 endpoints): fixed asset management
- yearEnd (23 endpoints): year-end closing procedures
- reminder (3 endpoints): invoice reminders
- supplierInvoice (13 endpoints): supplier invoice processing, approval, payment
- subscription (3 endpoints): recurring subscriptions
- attestation (3 endpoints): document approval workflows
For any unfamiliar task, ALWAYS use query_api_docs tool first to find the right endpoint.

=== FILE HANDLING ===
When files are attached (CSV, text, etc.), use the "query_file" tool to inspect them:
- Start with action "info" to see headers, row count, and a preview.
- Use "read_rows" to read CSV data as objects (paginated with from/count).
- Use "search" to find specific rows by value, optionally filtering by column.
- Extract the data you need from the file, then make the appropriate Tripletex API calls.

After completing all API calls, respond with DONE.`;

interface ParsedFile {
  filename: string;
  mime_type: string;
  raw: string;
  lines: string[];
  headers: string[] | null;
  rows: string[][] | null;
}

// ── Decode embedded base64 CSV in prompts ──────────────────────────────────
function tryDecodeEmbeddedCsv(prompt: string): { cleanedPrompt: string; extraFiles: FileAttachment[] } {
  const base64Regex = /(?:^|\n)([A-Za-z0-9+/=\r\n]{120,})(?:\n|$)/g;
  const extraFiles: FileAttachment[] = [];
  let cleanedPrompt = prompt;
  for (const match of prompt.matchAll(base64Regex)) {
    const blob = match[1].replace(/\s+/g, "");
    try {
      const raw = Buffer.from(blob, "base64").toString("utf-8");
      if (raw.includes(";") && raw.includes("\n") && /Dato;|Date;|Forklaring;/.test(raw)) {
        extraFiles.push({ filename: `embedded-${extraFiles.length + 1}.csv`, mime_type: "text/csv", content_base64: Buffer.from(raw, "utf-8").toString("base64") });
        cleanedPrompt = cleanedPrompt.replace(match[1], `[decoded CSV attached as embedded-${extraFiles.length}.csv]`);
      }
    } catch { /* ignore */ }
  }
  return { cleanedPrompt, extraFiles };
}

// ── Deterministic bank CSV parser ───────────────────────────────────────────
type BankTxKind = "customer_payment" | "supplier_payment" | "bank_fee" | "bank_fee_refund" | "unknown";
interface BankTx { date: string; description: string; amount: number; kind: BankTxKind; counterparty?: string; invoiceNumber?: string; }

function parseNorwegianBankCsv(raw: string): BankTx[] | null {
  const lines = raw.split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return null;
  const header = lines[0].toLowerCase();
  if (!header.includes("dato") && !header.includes("date")) return null;
  if (!header.includes(";")) return null;

  return lines.slice(1).map((line) => {
    const parts = line.split(";");
    const date = parts[0]?.trim() || "";
    const description = parts[1]?.trim() || "";
    const inn = parts[2]?.trim() ? Number(parts[2].trim()) : 0;
    const ut = parts[3]?.trim() ? Number(parts[3].trim()) : 0;
    // Inn is positive, Ut may already be negative
    const amount = inn !== 0 ? inn : ut;

    let kind: BankTxKind = "unknown";
    let counterparty: string | undefined;
    let invoiceNumber: string | undefined;

    let m = description.match(/^Innbetaling fra (.+?)\s*\/\s*Faktura (\d+)/i);
    if (!m) m = description.match(/^(?:Payment|Paiement|Zahlung|Pagamento|Pago) (?:from|de|von|fra) (.+?)\s*\/\s*(?:Invoice|Facture|Rechnung|Faktura|Factura) (\d+)/i);
    if (m) { kind = "customer_payment"; counterparty = m[1].trim(); invoiceNumber = m[2]; }
    else if ((m = description.match(/^Betaling (?:Leverand.r|Supplier|Fournisseur|Lieferant|Proveedor|Fornecedor) (.+)$/i))) { kind = "supplier_payment"; counterparty = m[1].trim(); }
    else if (/^Bankgebyr$/i.test(description.trim()) || /^Bank (?:fee|charge|gebühr)/i.test(description.trim())) { kind = amount < 0 ? "bank_fee" : "bank_fee_refund"; }
    else if (/^Skattetrekk$/i.test(description.trim()) || /^Tax (?:deduction|withholding)/i.test(description.trim())) { kind = "bank_fee"; }
    else if (/^Renteinntekter$/i.test(description.trim()) || /^Interest (?:income|revenue)/i.test(description.trim())) { kind = "bank_fee_refund"; }

    return { date, description, amount, kind, counterparty, invoiceNumber };
  });
}

function isBankReconciliationTask(prompt: string): boolean {
  return /avstem|reconcil|concilia|bankutskrift|extracto bancario|relevé bancaire|kontoauszug/i.test(prompt);
}

function parseFiles(files: FileAttachment[]): Map<string, ParsedFile> {
  const map = new Map<string, ParsedFile>();
  for (const file of files) {
    if (file.mime_type === "application/pdf" || file.mime_type.startsWith("image/")) continue;
    const raw = Buffer.from(file.content_base64, "base64").toString("utf-8");
    const lines = raw.split(/\r?\n/).filter((l) => l.trim() !== "");
    const isCSV =
      file.filename.endsWith(".csv") ||
      file.mime_type === "text/csv" ||
      (lines.length > 1 && (lines[0].includes(";") || lines[0].includes(",")));
    let headers: string[] | null = null;
    let rows: string[][] | null = null;
    if (isCSV && lines.length > 0) {
      const sep = lines[0].includes(";") ? ";" : ",";
      headers = lines[0].split(sep).map((h) => h.trim().replace(/^"|"$/g, ""));
      rows = lines.slice(1).map((l) => l.split(sep).map((c) => c.trim().replace(/^"|"$/g, "")));
    }
    map.set(file.filename, { filename: file.filename, mime_type: file.mime_type, raw, lines, headers, rows });
  }
  return map;
}

function handleFileQuery(
  fileMap: Map<string, ParsedFile>,
  input: { filename: string; action: string; from?: number; count?: number; search?: string; column?: string }
): unknown {
  const file = fileMap.get(input.filename);
  if (!file) {
    return {
      error: true,
      message: `File not found: ${input.filename}`,
      available: Array.from(fileMap.keys()),
    };
  }

  switch (input.action) {
    case "info": {
      return {
        filename: file.filename,
        mime_type: file.mime_type,
        totalLines: file.lines.length,
        isCSV: !!file.headers,
        headers: file.headers,
        totalRows: file.rows?.length ?? null,
        preview: file.lines.slice(0, 5),
      };
    }
    case "read_rows": {
      if (!file.rows || !file.headers) {
        return { error: true, message: "File is not CSV. Use read_lines instead." };
      }
      const from = input.from ?? 0;
      const count = input.count ?? 50;
      const slice = file.rows.slice(from, from + count);
      const asObjects = slice.map((row) =>
        Object.fromEntries(file.headers!.map((h, i) => [h, row[i] ?? ""]))
      );
      return { headers: file.headers, from, count: slice.length, totalRows: file.rows.length, rows: asObjects };
    }
    case "read_lines": {
      const from = input.from ?? 0;
      const count = input.count ?? 50;
      const slice = file.lines.slice(from, from + count);
      return { from, count: slice.length, totalLines: file.lines.length, lines: slice };
    }
    case "search": {
      if (!input.search) return { error: true, message: "search parameter required" };
      const query = input.search.toLowerCase();
      if (file.rows && file.headers) {
        const matches = file.rows
          .map((row, i) => ({ index: i, row: Object.fromEntries(file.headers!.map((h, j) => [h, row[j] ?? ""])) }))
          .filter(({ row }) => {
            const values = input.column ? [row[input.column] ?? ""] : Object.values(row);
            return values.some((v) => v.toLowerCase().includes(query));
          })
          .slice(0, 50);
        return { headers: file.headers, matchCount: matches.length, matches };
      } else {
        const matches = file.lines
          .map((line, i) => ({ index: i, line }))
          .filter(({ line }) => line.toLowerCase().includes(query))
          .slice(0, 50);
        return { matchCount: matches.length, matches };
      }
    }
    default:
      return { error: true, message: `Unknown action: ${input.action}. Use: info, read_rows, read_lines, search` };
  }
}

// ============================================================
// Tool definitions in both Anthropic and Gemini formats
// ============================================================

const API_DOCS_TOOL_ANTHROPIC: Anthropic.Messages.Tool = {
  name: "query_api_docs",
  description:
    "Search the Tripletex API Swagger documentation. Use this BEFORE making API calls to verify exact field names, required parameters, and endpoint paths. Actions: 'list_endpoints' to find endpoints by category/keyword, 'get_endpoint' to get full docs for a specific endpoint, 'get_schema' to get a model's field definitions, 'search' for free-text search.",
  input_schema: {
    type: "object" as const,
    properties: {
      action: {
        type: "string",
        enum: ["list_categories", "list_endpoints", "get_endpoint", "get_schema", "search"],
        description:
          "list_categories: see all API groups. list_endpoints: find endpoints (filter by category/method/query). get_endpoint: get full documentation for a specific endpoint path. get_schema: get model/schema field definitions. search: free-text search across all docs.",
      },
      query: {
        type: "string",
        description: "Search keyword for list_endpoints or search actions",
      },
      method: {
        type: "string",
        enum: ["GET", "POST", "PUT", "DELETE"],
        description: "Filter by HTTP method (for list_endpoints or get_endpoint)",
      },
      path: {
        type: "string",
        description: "Endpoint path to look up (for get_endpoint), e.g. /invoice/{id}/:payment",
      },
      schema: {
        type: "string",
        description: "Schema/model name to look up (for get_schema), e.g. Invoice, Employee, Order",
      },
      category: {
        type: "string",
        description: "Filter by category name (for list_endpoints), e.g. invoice, employee, order",
      },
    },
    required: ["action"],
  },
};

const TRIPLETEX_TOOL_ANTHROPIC: Anthropic.Messages.Tool = {
  name: "tripletex_api",
  description: "Make an HTTP request to the Tripletex API. Returns the JSON response.",
  input_schema: {
    type: "object" as const,
    properties: {
      method: { type: "string", enum: ["GET", "POST", "PUT", "DELETE"], description: "HTTP method" },
      path: { type: "string", description: "API path starting with /, e.g. /employee or /customer/123" },
      params: { type: "object", description: "Query parameters as key-value pairs", additionalProperties: true },
      body: { type: "object", description: "JSON request body for POST/PUT requests", additionalProperties: true },
    },
    required: ["method", "path"],
  },
};

const QUERY_FILE_TOOL_ANTHROPIC: Anthropic.Messages.Tool = {
  name: "query_file",
  description: "Query an attached file (CSV, text, etc). Use 'info' to see headers/row count, 'read_rows' to read CSV rows, 'read_lines' for raw lines, 'search' to find matching rows/lines.",
  input_schema: {
    type: "object" as const,
    properties: {
      filename: { type: "string", description: "The filename to query" },
      action: { type: "string", enum: ["info", "read_rows", "read_lines", "search"], description: "Action to perform" },
      from: { type: "number", description: "Start index for read_rows/read_lines (default 0)" },
      count: { type: "number", description: "Number of rows/lines to return (default 50)" },
      search: { type: "string", description: "Search query string (for action=search)" },
      column: { type: "string", description: "Limit search to a specific column (for action=search on CSV files)" },
    },
    required: ["filename", "action"],
  },
};

const CALC_TOOL_ANTHROPIC: Anthropic.Messages.Tool = {
  name: "calculate",
  description: "Evaluate a math expression. Use for VAT calculations, salary computations, percentages, etc. Examples: '10000 * 1.25', '55350 * 12', '25650 / 1.25', '0.33 * 240750'",
  input_schema: {
    type: "object" as const,
    properties: {
      expression: { type: "string", description: "Math expression to evaluate, e.g. '10000 * 1.25' or '55350 * 12'" },
    },
    required: ["expression"],
  },
};

const CALC_TOOL_GEMINI: FunctionDeclaration = {
  name: "calculate",
  description: "Evaluate a math expression. Use for VAT calculations, salary computations, percentages, etc.",
  parameters: {
    type: SchemaType.OBJECT,
    properties: {
      expression: { type: SchemaType.STRING, description: "Math expression to evaluate" },
    },
    required: ["expression"],
  },
};

function handleCalculate(input: { expression: string }): unknown {
  try {
    // Safe math eval - only allow numbers, operators, parens
    const expr = input.expression.replace(/[^0-9+\-*/().%\s]/g, '');
    if (!expr) return { error: true, message: "Invalid expression" };
    const result = Function('"use strict"; return (' + expr + ')')();
    return { expression: input.expression, result: Number(result), rounded: Math.round(result * 100) / 100 };
  } catch (e) {
    return { error: true, message: String(e) };
  }
}

const TRIPLETEX_TOOL_GEMINI: FunctionDeclaration = {
  name: "tripletex_api",
  description: "Make an HTTP request to the Tripletex API. Returns the JSON response.",
  parameters: {
    type: SchemaType.OBJECT,
    properties: {
      method: { type: SchemaType.STRING, description: "HTTP method: GET, POST, PUT, or DELETE" },
      path: { type: SchemaType.STRING, description: "API path starting with /, e.g. /employee or /customer/123" },
      params: { type: SchemaType.STRING, description: "Query parameters as JSON string, e.g. '{\"fields\": \"*\", \"count\": 100}'" },
      body: { type: SchemaType.STRING, description: "JSON request body string for POST/PUT requests" },
    },
    required: ["method", "path"],
  },
};

const QUERY_FILE_TOOL_GEMINI: FunctionDeclaration = {
  name: "query_file",
  description: "Query an attached file (CSV, text, etc). Use 'info' to see headers/row count, 'read_rows' to read CSV rows, 'read_lines' for raw lines, 'search' to find matching rows/lines.",
  parameters: {
    type: SchemaType.OBJECT,
    properties: {
      filename: { type: SchemaType.STRING, description: "The filename to query" },
      action: { type: SchemaType.STRING, description: "Action: info, read_rows, read_lines, or search" },
      from: { type: SchemaType.STRING, description: "Start index (default 0)" },
      count: { type: SchemaType.STRING, description: "Number of rows/lines to return (default 50)" },
      search: { type: SchemaType.STRING, description: "Search query string" },
      column: { type: SchemaType.STRING, description: "Limit search to a specific column" },
    },
    required: ["filename", "action"],
  },
};

const API_DOCS_TOOL_GEMINI_EXECUTOR: FunctionDeclaration = {
  name: "query_api_docs",
  description: "Search the Tripletex API documentation. Actions: list_categories, list_endpoints, get_endpoint, get_schema, search",
  parameters: {
    type: SchemaType.OBJECT,
    properties: {
      action: { type: SchemaType.STRING, description: "list_categories, list_endpoints, get_endpoint, get_schema, search" },
      query: { type: SchemaType.STRING, description: "Search keyword" },
      method: { type: SchemaType.STRING, description: "HTTP method filter" },
      path: { type: SchemaType.STRING, description: "Endpoint path" },
      schema: { type: SchemaType.STRING, description: "Schema name" },
      category: { type: SchemaType.STRING, description: "Category filter" },
    },
    required: ["action"],
  },
};

// ============================================================
// Anthropic agent loop
// ============================================================

function buildAnthropicContent(prompt: string, files: FileAttachment[]): Anthropic.Messages.ContentBlockParam[] {
  const content: Anthropic.Messages.ContentBlockParam[] = [];
  for (const file of files) {
    if (file.mime_type === "application/pdf") {
      content.push({ type: "document", source: { type: "base64", media_type: "application/pdf", data: file.content_base64 } });
    } else if (file.mime_type.startsWith("image/")) {
      content.push({ type: "image", source: { type: "base64", media_type: file.mime_type as "image/jpeg" | "image/png" | "image/gif" | "image/webp", data: file.content_base64 } });
    } else {
      content.push({ type: "text", text: `Attached file: "${file.filename}" (${file.mime_type}) — use the query_file tool to read its contents.` });
    }
  }
  const today = new Date().toISOString().split("T")[0];
  content.push({ type: "text", text: `Today's date: ${today}\n\n${prompt}` });
  return content;
}

async function runAnthropicAgent(
  client: TripletexClient,
  prompt: string,
  files: FileAttachment[],
  model: string,
  fileMap: Map<string, ParsedFile>,
): Promise<{ callCount: number; errorCount: number; messages: unknown[] }> {
  const anthropic = new Anthropic();
  const hasQueryableFiles = fileMap.size > 0;
  const tools = hasQueryableFiles
    ? [TRIPLETEX_TOOL_ANTHROPIC, QUERY_FILE_TOOL_ANTHROPIC, API_DOCS_TOOL_ANTHROPIC, CALC_TOOL_ANTHROPIC]
    : [TRIPLETEX_TOOL_ANTHROPIC, API_DOCS_TOOL_ANTHROPIC, CALC_TOOL_ANTHROPIC];

  const messages: Anthropic.Messages.MessageParam[] = [
    { role: "user", content: buildAnthropicContent(prompt, files) },
  ];

  let iterations = 0;
  const maxIterations = 30;

  while (iterations < maxIterations) {
    iterations++;
    const response = await anthropic.messages.create({
      model,
      max_tokens: 4096,
      system: SYSTEM_PROMPT,
      tools,
      messages,
    });

    if (response.stop_reason === "end_turn") break;
    const toolUseBlocks = response.content.filter(
      (b): b is Anthropic.Messages.ToolUseBlock => b.type === "tool_use"
    );
    if (toolUseBlocks.length === 0) break;

    messages.push({ role: "assistant", content: response.content });
    const toolResults: Anthropic.Messages.ToolResultBlockParam[] = [];

    for (const toolUse of toolUseBlocks) {
      let result: unknown;
      let isError = false;

      if (toolUse.name === "query_file") {
        result = handleFileQuery(fileMap, toolUse.input as Parameters<typeof handleFileQuery>[1]);
        isError = !!(result as Record<string, unknown>).error;
      } else if (toolUse.name === "query_api_docs") {
        result = handleApiDocsQuery(toolUse.input as Parameters<typeof handleApiDocsQuery>[0]);
        isError = !!(result as Record<string, unknown>).error;
      } else if (toolUse.name === "calculate") {
        result = handleCalculate(toolUse.input as { expression: string });
        isError = !!(result as Record<string, unknown>).error;
      } else {
        const call = toolUse.input as ToolCall;
        // Allow /incomingInvoice — try it, fall back to voucher if 403
        // Block ledger correction vouchers with >2 postings
        const isLedgerCorrectionA = /fehler|erreur|error.*ledger|error.*voucher|feil.*hovedbok|erros.*razão|errores.*libro/i.test(prompt);
        if (isLedgerCorrectionA && call.method === "POST" && call.path === "/ledger/voucher") {
          const vBody = call.body as Record<string, unknown> | undefined;
          const postings = (vBody?.postings as unknown[]) || [];
          if (postings.length > 2) {
            result = { error: true, message: `BLOCKED: Create ONE voucher per error with EXACTLY 2 postings each. Do NOT bundle multiple corrections into one voucher. Do NOT split into net+VAT.` };
            isError = true;
          }
        }
        const isCurrencyTask = /exchange.rate|agio|disagio|valuta|taxa.de.câmbio|Wechselkurs|taux.de.change|valutadifferanse|kursen/i.test(prompt);
        if (isCurrencyTask && call.method === "POST" && ["/product", "/order", "/invoice"].includes(call.path)) {
          result = { error: true, message: "BLOCKED: Do NOT create product/order/invoice for currency exchange tasks. The invoice ALREADY EXISTS. Use PUT /invoice/{id}/:payment on the existing invoice." };
          isError = true;
        }
        if (!result) {
          const vResult = await validateAndExecute(client, call);
          result = vResult.result;
          isError = vResult.isError;
        }
      }

      toolResults.push({
        type: "tool_result",
        tool_use_id: toolUse.id,
        content: JSON.stringify(result),
        is_error: isError,
      });
    }

    messages.push({ role: "user", content: toolResults });
  }

  return { callCount: client.callCount, errorCount: client.errorCount, messages };
}

// ============================================================
// Gemini agent loop
// ============================================================

async function runGeminiAgent(
  client: TripletexClient,
  prompt: string,
  files: FileAttachment[],
  model: string,
  fileMap: Map<string, ParsedFile>,
): Promise<{ callCount: number; errorCount: number; messages: unknown[] }> {
  const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY!);
  const hasQueryableFiles = fileMap.size > 0;
  const tools = hasQueryableFiles
    ? [{ functionDeclarations: [TRIPLETEX_TOOL_GEMINI, QUERY_FILE_TOOL_GEMINI, CALC_TOOL_GEMINI, API_DOCS_TOOL_GEMINI_EXECUTOR] }]
    : [{ functionDeclarations: [TRIPLETEX_TOOL_GEMINI, CALC_TOOL_GEMINI, API_DOCS_TOOL_GEMINI_EXECUTOR] }];

  function makeModel(thinkingBudget: number) {
    return genAI.getGenerativeModel({
      model,
      systemInstruction: SYSTEM_INSTRUCTION,
      tools,
      generationConfig: {
        temperature: 0.1,
        maxOutputTokens: 16384,
        // @ts-ignore
        thinkingConfig: { thinkingBudget },
      } as any,
    });
  }
  let genModel = makeModel(1024); // Start fast to avoid proxy token expiration

  const parts: Array<{ text: string } | { inlineData: { mimeType: string; data: string } }> = [];
  for (const file of files) {
    if (file.mime_type.startsWith("image/") || file.mime_type === "application/pdf") {
      // Check size — skip if too large (> 500KB base64)
      if (file.content_base64.length > 500000) {
        console.log(`File ${file.filename} too large (${file.content_base64.length} chars), skipping inline`);
        parts.push({ text: `Attached file: "${file.filename}" (${file.mime_type}) — file is large, use the query_file tool.` });
      } else {
        parts.push({ inlineData: { mimeType: file.mime_type, data: file.content_base64 } });
      }
    } else if (file.mime_type === "text/csv" || file.filename.endsWith(".csv")) {
      // For CSV: include a compact summary in the prompt instead of requiring query_file
      const csv = Buffer.from(file.content_base64, "base64").toString("utf-8");
      const lines = csv.split(/\r?\n/).filter(l => l.trim());
      if (lines.length <= 30) {
        // Small CSV — include directly as text
        parts.push({ text: `Attached CSV file "${file.filename}":\n${csv}` });
      } else {
        // Large CSV — show header + first 20 rows, rest via query_file
        const preview = lines.slice(0, 21).join("\n");
        parts.push({ text: `Attached CSV file "${file.filename}" (${lines.length} rows, showing first 20):\n${preview}\n\n... Use query_file tool with action "read_rows" for remaining rows.` });
      }
    } else {
      parts.push({ text: `Attached file: "${file.filename}" (${file.mime_type}) — use the query_file tool to read its contents.` });
    }
  }
  const today = new Date().toISOString().split("T")[0];
  // Send full reference as first user message (not in systemInstruction to save tokens per turn)
  parts.push({ text: `${SYSTEM_PROMPT}\n\nToday's date: ${today}\n\n${prompt}` });

  // Retry wrapper for transient API errors (503, 429)
  async function sendWithRetry(chatInstance: ReturnType<typeof genModel.startChat>, msg: unknown[], retries = 10): Promise<any> {
    for (let i = 0; i < retries; i++) {
      try { return await chatInstance.sendMessage(msg as any); }
      catch (e: any) {
        // Token limit exceeded — truncate history and retry with fresh chat
        if (e.message?.includes("token count exceeds") || e.message?.includes("too long")) {
          console.log(`Token limit hit — resetting chat with truncated history`);
          // Keep only the first user message and last 4 messages
          const truncated = messages.length > 6 ? [messages[0], ...messages.slice(-4)] : messages;
          chatInstance = genModel.startChat({ history: truncated as any });
          continue;
        }
        if (i < retries - 1 && (e.message?.includes("503") || e.message?.includes("429") || e.message?.includes("unavailable") || e.message?.includes("RESOURCE_EXHAUSTED") || e.message?.includes("fetch failed"))) {
          console.log(`Gemini retry ${i+1}/${retries}: ${e.message?.slice(0,60)}`);
          await new Promise(r => setTimeout(r, 3000 * (i + 1)));
          continue;
        }
        throw e;
      }
    }
  }

  let chat = genModel.startChat();
  let response = await sendWithRetry(chat, parts);
  const messages: unknown[] = [{ role: "user", parts }];

  let iterations = 0;
  const maxIterations = 30;
  // Cache account id→number mappings from GET responses to validate voucher postings
  const accountLookupCache = new Map<number, number>();
  // Cache vatType ID for auto-injection into supplier vouchers
  let cachedIncomingVatTypeId: number | null = null;

  while (iterations < maxIterations) {
    iterations++;
    const candidate = response.response.candidates?.[0];
    if (!candidate) break;

    const parts = candidate.content?.parts || [];

    // If Gemini returned empty parts (thinking mode with no output), retry
    if (parts.length === 0 && iterations < 3) {
      console.log(`Gemini returned empty parts (iteration ${iterations}), retrying...`);
      response = await sendWithRetry(chat, [{ text: "Please proceed with the task. Make the necessary API calls." }]);
      continue;
    }

    messages.push({ role: "model", parts });

    const functionCalls = parts.filter((p: { functionCall?: unknown }) => p.functionCall);

    // Detect when Gemini asks for clarification or says DONE without doing anything
    if (functionCalls.length === 0) {
      const textParts = parts.filter((p: { text?: string }) => p.text).map((p: { text: string }) => p.text).join(" ");
      const isAskingForClarification = /could you|can you|please provide|what.*task|which.*task|I need more/i.test(textParts);
      const saidDoneWithoutWork = /DONE|completed|finished|ferdig/i.test(textParts) && client.callCount === 0;

      if ((isAskingForClarification || saidDoneWithoutWork) && iterations <= 3) {
        console.log(`Gemini didn't act (iteration ${iterations}), nudging...`);
        response = await sendWithRetry(chat, [{ text: `The task is described above. You MUST execute it NOW using the tripletex_api tool. Start by making the first API call (e.g. GET /customer, GET /employee, GET /supplier). Do NOT ask for clarification — just execute the task.` }]);
        continue;
      }
      if (functionCalls.length === 0) break;
    }

    const functionResponses: Part[] = [];

    for (const part of functionCalls) {
      const fc = (part as { functionCall: { name: string; args: Record<string, string> } }).functionCall;
      let result: unknown;

      if (fc.name === "query_file") {
        const input = {
          filename: fc.args.filename,
          action: fc.args.action,
          from: fc.args.from ? parseInt(fc.args.from) : undefined,
          count: fc.args.count ? parseInt(fc.args.count) : undefined,
          search: fc.args.search,
          column: fc.args.column,
        };
        result = handleFileQuery(fileMap, input);
      } else if (fc.name === "calculate") {
        result = handleCalculate({ expression: String(fc.args.expression || "") });
      } else if (fc.name === "query_api_docs") {
        result = handleApiDocsQuery(fc.args as Parameters<typeof handleApiDocsQuery>[0]);
      } else {
        const parseOrPass = (v: unknown) => {
          if (!v) return undefined;
          if (typeof v === "string") { try { return JSON.parse(v); } catch { return v; } }
          return v; // already an object
        };
        const call: ToolCall = {
          method: fc.args.method as ToolCall["method"],
          path: fc.args.path,
          params: parseOrPass(fc.args.params) as ToolCall["params"],
          body: parseOrPass(fc.args.body) as ToolCall["body"],
        };
        // Block occupation code search by nameNO when PDF contract is attached (has STYRK code)
        if (call.method === "GET" && call.path === "/employee/employment/occupationCode") {
          const params = call.params as Record<string, string> | undefined;
          const hasFiles = prompt.includes("PDF") || prompt.includes("pdf") || prompt.includes("contract") || prompt.includes("Vertrag") || prompt.includes("contrato") || prompt.includes("contrat") || prompt.includes("kontrakt") || prompt.includes("carta de oferta") || prompt.includes("lettre") || prompt.includes("Angebot");
          if (params?.nameNO && !params?.code && hasFiles) {
            result = { error: true, message: "BLOCKED: Do NOT search occupation codes by name. The PDF contract contains a 4-digit STYRK code. Extract it from the PDF and search by code instead: GET /employee/employment/occupationCode?code={STYRK_CODE}1&count=20. Append '1' to the 4-digit code." };
          }
        }
        // Block ledger correction vouchers with >2 postings (agent keeps splitting into net+VAT)
        const isLedgerCorrection = /fehler|erreur|error.*ledger|error.*voucher|feil.*hovedbok|erros.*razão|errores.*libro/i.test(prompt);
        if (isLedgerCorrection && call.method === "POST" && call.path === "/ledger/voucher") {
          const vBody = call.body as Record<string, unknown> | undefined;
          const postings = (vBody?.postings as unknown[]) || [];
          if (postings.length > 2) {
            result = { error: true, message: `BLOCKED: Create ONE voucher per error with EXACTLY 2 postings each. Do NOT bundle multiple corrections into one voucher. Do NOT split into net+VAT.` };
          }
        }
        // Allow /incomingInvoice — try it, fall back to voucher if 403
        // Receipt tasks: allow manual voucher as fallback if createVouchers didn't produce accounting
        // Block invoice creation on currency exchange tasks
        const isCurrencyTask = /exchange.rate|agio|disagio|valuta|taxa.de.câmbio|Wechselkurs|taux.de.change|valutadifferanse|kursen/i.test(prompt);
        if (isCurrencyTask && call.method === "POST" && ["/product", "/order", "/invoice"].includes(call.path)) {
          result = { error: true, message: "BLOCKED: Do NOT create product/order/invoice for currency exchange tasks. The invoice ALREADY EXISTS. Use PUT /invoice/{id}/:payment on the existing invoice." };
        }
        // Validate voucher account numbers match prompt-specified accounts
        else if (call.method === "POST" && call.path === "/ledger/voucher" && call.body && typeof call.body === "object") {
          const voucherBody = call.body as Record<string, unknown>;
          const postings = voucherBody.postings as Array<Record<string, unknown>> | undefined;
          if (postings) {
            // Extract account numbers mentioned in prompt (4-digit patterns like "konto 2900", "account 6010")
            const promptAccounts = new Set<number>();
            const acctMatches = prompt.match(/(?:konto|account|conta|compte|Konto|kreditkonto|debitkonto)\s+(\d{4})/gi);
            if (acctMatches) {
              for (const m of acctMatches) {
                const num = parseInt(m.match(/\d{4}/)![0]);
                promptAccounts.add(num);
              }
            }
            // Check if any posting uses an account that's close but not exact
            // SKIP for year-end/depreciation AND ledger corrections — both legitimately use multiple accounts from prompt
            const isDepreciationTask = /year-end|årsoppgjør|depreciation|avskrivning|amortissement|depreciação|amortización|Jahresabschluss|clôture annuelle|cierre anual|encerramento anual/i.test(prompt);
            const isLedgerCorrectionTask = /fehler|erreur|error.*ledger|feil.*hovedbok|erros.*razão|errores.*libro|wrong account|conta errada|feil konto/i.test(prompt);
            if (!isDepreciationTask && !isLedgerCorrectionTask && promptAccounts.size > 0 && accountLookupCache.size > 0) {
              for (const p of postings) {
                const acctId = (p.account as Record<string, unknown>)?.id as number;
                const acctNum = accountLookupCache.get(acctId);
                if (acctNum && !promptAccounts.has(acctNum)) {
                  for (const pa of promptAccounts) {
                    if (Math.abs(acctNum - pa) > 0 && Math.abs(acctNum - pa) <= 50 && Math.floor(acctNum/100) === Math.floor(pa/100)) {
                      result = { error: true, message: `WRONG ACCOUNT: You used account ${acctNum} but the prompt specifies account ${pa}. Use EXACTLY ${pa}. Look it up with GET /ledger/account?number=${pa}` };
                      break;
                    }
                  }
                  if (result) break;
                }
              }
            }
          }
          // Check supplier voucher uses account applicable for supplier invoices
          if (!result) {
            const hasSupplier = postings?.some(p => p.supplier);
            if (hasSupplier && accountLookupCache.size > 0) {
              const lockedForSupplier = [7100, 7130, 7140]; // Known locked accounts
              for (const p of (postings || [])) {
                if (p.supplier) continue; // Skip the AP posting
                const acctId = (p.account as Record<string, unknown>)?.id as number;
                const acctNum = accountLookupCache.get(acctId);
                if (acctNum && lockedForSupplier.includes(acctNum)) {
                  result = { error: true, message: `BLOCKED: Account ${acctNum} is NOT applicable for supplier invoices (isApplicableForSupplierInvoice=false). Use account 6700 instead. GET /ledger/account?number=6700 to find its ID.` };
                  break;
                }
              }
            }
            // Auto-inject vatType into supplier voucher expense postings if missing
            if (hasSupplier && postings) {
              // If agent didn't look up vatType, block and tell them to do it
              const needsVatType = postings.some(p => {
                if (p.supplier || p.vatType) return false;
                const acctId = (p.account as Record<string, unknown>)?.id as number;
                const acctNum = accountLookupCache.get(acctId);
                return acctNum && acctNum >= 4000 && acctNum < 8000;
              });
              if (needsVatType && !cachedIncomingVatTypeId) {
                result = { error: true, message: "BLOCKED: Supplier voucher expense posting is missing vatType. You MUST first GET /ledger/vatType?vatNumber=1 to find the 25% incoming VAT type ID, then include vatType:{id:vatTypeId} on the expense posting." };
              } else if (needsVatType && cachedIncomingVatTypeId) {
                for (const p of postings) {
                  if (!p.supplier && !p.vatType) {
                    const acctId = (p.account as Record<string, unknown>)?.id as number;
                    const acctNum = accountLookupCache.get(acctId);
                    if (acctNum && acctNum >= 4000 && acctNum < 8000) {
                      p.vatType = { id: cachedIncomingVatTypeId };
                      console.log(`Auto-injected vatType ${cachedIncomingVatTypeId} on expense posting account ${acctNum}`);
                    }
                  }
                }
              }
            }
          }
          if (!result) {
            const vResult = await validateAndExecute(client, call);
            result = vResult.result;
          }
        }
        else {
          const vResult = await validateAndExecute(client, call);
          result = vResult.result;
        }
        // Cache vatType ID from GET /ledger/vatType responses
        if (call.method === "GET" && call.path === "/ledger/vatType" && result && typeof result === "object") {
          const r = result as Record<string, unknown>;
          const values = r.values as Array<Record<string, unknown>> | undefined;
          if (values) {
            for (const v of values) {
              const pct = v.percentage as number;
              if (pct === 25 && !cachedIncomingVatTypeId) {
                cachedIncomingVatTypeId = v.id as number;
                console.log(`Cached incoming vatType ID: ${cachedIncomingVatTypeId}`);
              }
            }
          }
        }
      }

      // Populate account cache from GET /ledger/account responses
      if (result && typeof result === "object" && !Array.isArray(result)) {
        const r = result as Record<string, unknown>;
        const values = r.values as Array<Record<string, unknown>> | undefined;
        if (values) {
          for (const v of values) {
            if (v && typeof v.id === "number" && typeof v.number === "number") {
              accountLookupCache.set(v.id, v.number);
            }
          }
        }
      }
      // No-op: vatType caching done inline

      // Truncate large responses to prevent token limit overflow
      let truncatedResult = result;
      if (result && typeof result === "object" && !Array.isArray(result)) {
        const r = result as Record<string, unknown>;
        const values = r.values as unknown[] | undefined;
        if (values && values.length > 20) {
          truncatedResult = { ...r, values: values.slice(0, 20), _note: `Showing first 20 of ${values.length}. Use from/count params for pagination.`, fullResultSize: r.fullResultSize || values.length };
        }
      }
      functionResponses.push({ functionResponse: { name: fc.name, response: truncatedResult as Record<string, unknown> } });
    }

    messages.push({ role: "function", parts: functionResponses });

    // After first iteration, switch to higher thinking budget (token is now validated)
    if (iterations === 1) {
      genModel = makeModel(2048);
      // Pass all messages except the last function response as history,
      // then send the last function response as the new message
      const history = messages.slice(0, -1);
      chat = genModel.startChat({ history: history as any });
    }
    response = await sendWithRetry(chat, functionResponses);
  }

  // If we ended with 0 API calls, the agent failed to act. Retry with stronger nudge.
  if (client.callCount === 0 && iterations < maxIterations - 5) {
    console.log("Agent made 0 API calls — retrying with explicit instruction...");
    response = await sendWithRetry(chat, [{ text: `You have NOT made any API calls yet. The task is: "${prompt}". You MUST use the tripletex_api tool NOW to execute this task. Start with the first GET call.` }]);
    // Continue the loop for a few more iterations
    for (let retry = 0; retry < 10 && iterations < maxIterations; retry++) {
      iterations++;
      const candidate = response.response.candidates?.[0];
      if (!candidate) break;
      const retryParts = candidate.content?.parts || [];
      messages.push({ role: "model", parts: retryParts });
      const retryCalls = retryParts.filter((p: { functionCall?: unknown }) => p.functionCall);
      if (retryCalls.length === 0) break;
      const retryResponses: Part[] = [];
      for (const part of retryCalls) {
        const fc = (part as { functionCall: { name: string; args: Record<string, string> } }).functionCall;
        let result: unknown;
        const parseOrPass = (v: unknown) => { if (!v) return undefined; if (typeof v === "string") { try { return JSON.parse(v); } catch { return v; } } return v; };
        const call: ToolCall = { method: fc.args.method as ToolCall["method"], path: fc.args.path, params: parseOrPass(fc.args.params) as ToolCall["params"], body: parseOrPass(fc.args.body) as ToolCall["body"] };
        const vResult = await validateAndExecute(client, call);
        result = vResult.result;
        retryResponses.push({ functionResponse: { name: fc.name, response: result as Record<string, unknown> } });
      }
      messages.push({ role: "function", parts: retryResponses });
      response = await sendWithRetry(chat, retryResponses);
    }
  }

  // ── Completion verification ──────────────────────────────────────────────
  const finished = messages.some((m: any) => JSON.stringify(m).includes("DONE"));
  const apiPaths = client.apiCalls.map(c => c.path);

  // Travel expense verifier
  if (/reise|travel|viaje|voyage|reisekostenabrechnung/i.test(prompt)) {
    const needsPerDiem = /per diem|dagpenger|tagegeld|diett|indemnités/i.test(prompt);
    const missing: string[] = [];
    if (!apiPaths.some(p => p === "/travelExpense")) missing.push("travelExpense creation");
    if (!apiPaths.some(p => p?.includes("/cost"))) missing.push("cost lines");
    if (!apiPaths.some(p => p?.includes("/:deliver"))) missing.push("deliver");
    if (!apiPaths.some(p => p?.includes("/:approve"))) missing.push("approve");
    if (!apiPaths.some(p => p?.includes("/:createVouchers"))) missing.push("createVouchers");
    if (needsPerDiem && !apiPaths.some(p => p?.includes("/perDiemCompensation"))) missing.push("perDiem");

    // Also check: if createVouchers was called but no voucher was actually created, the accounting is missing
    const createVouchersCalled = apiPaths.some(p => p?.includes("/:createVouchers"));
    const hasLedgerVoucher = client.apiCalls.some(c => c.method === "POST" && c.path === "/ledger/voucher" && c.status < 400);
    if (createVouchersCalled && !hasLedgerVoucher) {
      missing.push("manual ledger voucher (createVouchers did not produce accounting — create a POST /ledger/voucher with expense+VAT+bank postings)");
    }

    if (missing.length > 0 && iterations < maxIterations - 5) {
      console.log(`Travel expense incomplete (missing: ${missing.join(", ")}). Retrying...`);
      response = await sendWithRetry(chat, [{ text: `The travel expense is INCOMPLETE. You still need to: ${missing.join(", ")}. Complete these steps NOW.` }]);
      for (let retry = 0; retry < 10 && iterations < maxIterations; retry++) {
        iterations++;
        const candidate = response.response.candidates?.[0];
        if (!candidate) break;
        const rParts = candidate.content?.parts || [];
        messages.push({ role: "model", parts: rParts });
        const rCalls = rParts.filter((p: { functionCall?: unknown }) => p.functionCall);
        if (rCalls.length === 0) break;
        const rResps: Part[] = [];
        for (const part of rCalls) {
          const fc = (part as { functionCall: { name: string; args: Record<string, string> } }).functionCall;
          let result: unknown;
          const parseOrPass = (v: unknown) => { if (!v) return undefined; if (typeof v === "string") { try { return JSON.parse(v); } catch { return v; } } return v; };
          const call: ToolCall = { method: fc.args.method as ToolCall["method"], path: fc.args.path, params: parseOrPass(fc.args.params) as ToolCall["params"], body: parseOrPass(fc.args.body) as ToolCall["body"] };
          const vResult = await validateAndExecute(client, call);
          result = vResult.result;
          rResps.push({ functionResponse: { name: fc.name, response: result as Record<string, unknown> } });
        }
        messages.push({ role: "function", parts: rResps });
        response = await sendWithRetry(chat, rResps);
      }
    }
  }

  // If agent failed without completing (no DONE, 0 API calls), retry with fresh chat
  if (!finished && client.callCount === 0) {
    console.log("Agent failed without completing. Retrying with fresh Gemini chat...");
    try {
      const freshModel = makeModel(2048);
      const freshChat = freshModel.startChat();
      response = await sendWithRetry(freshChat, [{ text: `${SYSTEM_PROMPT}\n\nToday's date: ${new Date().toISOString().split("T")[0]}\n\n${prompt}\n\nExecute this task immediately.` }]);
      for (let retry = 0; retry < 15; retry++) {
        const candidate = response.response.candidates?.[0];
        if (!candidate) break;
        const rParts = candidate.content?.parts || [];
        const rCalls = rParts.filter((p: { functionCall?: unknown }) => p.functionCall);
        if (rCalls.length === 0) break;
        const rResps: Part[] = [];
        for (const part of rCalls) {
          const fc = (part as { functionCall: { name: string; args: Record<string, string> } }).functionCall;
          let result: unknown;
          if (fc.name === "query_api_docs") { result = handleApiDocsQuery(fc.args as any); }
          else if (fc.name === "calculate") { result = handleCalculate({ expression: String(fc.args.expression || "") }); }
          else if (fc.name === "query_file") { result = handleFileQuery(fileMap, fc.args as any); }
          else {
            const parseOrPass = (v: unknown) => { if (!v) return undefined; if (typeof v === "string") { try { return JSON.parse(v); } catch { return v; } } return v; };
            const call: ToolCall = { method: fc.args.method as ToolCall["method"], path: fc.args.path, params: parseOrPass(fc.args.params) as ToolCall["params"], body: parseOrPass(fc.args.body) as ToolCall["body"] };
            const vResult = await validateAndExecute(client, call);
            result = vResult.result;
          }
          rResps.push({ functionResponse: { name: fc.name, response: result as Record<string, unknown> } });
        }
        messages.push({ role: "function", parts: rResps });
        response = await sendWithRetry(freshChat, rResps);
      }
    } catch (e) {
      console.log(`Retry also failed: ${String(e).slice(0, 100)}`);
    }
  }

  return { callCount: client.callCount, errorCount: client.errorCount, messages };
}

// ============================================================
// Planner: thinks through the problem before making API calls
// ============================================================

const PLANNER_PROMPT = `You are an API call planner for Tripletex, a Norwegian accounting system.
Given a task prompt, you must produce an EXACT execution plan of API calls to make.
You have access to the query_api_docs tool to look up endpoint details and schemas.
Do NOT make actual API calls — only plan them.

Your output must be a JSON array of steps. Each step is:
{
  "step": 1,
  "description": "What this step does",
  "method": "GET|POST|PUT|DELETE",
  "path": "/endpoint/path",
  "params": {"key": "value"},  // query params, optional
  "body": {...},               // request body, optional
  "dependsOn": [],             // step numbers whose response data is needed
  "extractFromResponse": "variableName"  // what to extract from response for later steps
}

Rules:
- Use EXACT field names from the API docs (e.g. priceExcludingVatCurrency, NOT priceExcludingVat)
- For linked entities, use {"id": "{{stepN.value.id}}"} syntax to reference earlier step results
- Include ALL required fields
- dateOfBirth is required for employee updates and employment creation
- For invoices: ALWAYS create order first, then invoice with orders=[{"id": orderId}]
- For PUT: only include editable fields, never read-only computed fields
- Start with today's date for orderDate/invoiceDate unless specified otherwise
- First GET /department to get deptId before creating employees
- First GET /ledger/vatType?typeOfVat=OUTGOING to get vatTypeId before creating products with VAT
- For bank account setup: GET /ledger/account?isBankAccount=true then PUT with bankAccountNumber

After researching with query_api_docs, respond with ONLY the JSON plan wrapped in \`\`\`json code block.`;

async function runPlanner(
  prompt: string,
  _files: FileAttachment[],
  fileMap: Map<string, ParsedFile>,
): Promise<string | null> {
  const plannerProvider = (process.env.PLANNER_PROVIDER as LLMProvider) || "gemini";
  const plannerModel = process.env.PLANNER_MODEL || "gemini-3-flash-preview";

  console.log(`Planning with ${plannerProvider} / ${plannerModel}...`);

  if (plannerProvider === "gemini") {
    const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY!);
    const API_DOCS_TOOL_GEMINI: FunctionDeclaration = {
      name: "query_api_docs",
      description: "Search the Tripletex API documentation. Actions: list_endpoints, get_endpoint, get_schema, search",
      parameters: {
        type: SchemaType.OBJECT,
        properties: {
          action: { type: SchemaType.STRING, description: "list_categories, list_endpoints, get_endpoint, get_schema, search" },
          query: { type: SchemaType.STRING, description: "Search keyword" },
          method: { type: SchemaType.STRING, description: "HTTP method filter" },
          path: { type: SchemaType.STRING, description: "Endpoint path" },
          schema: { type: SchemaType.STRING, description: "Schema name" },
          category: { type: SchemaType.STRING, description: "Category filter" },
        },
        required: ["action"],
      },
    };

    const genModel = genAI.getGenerativeModel({
      model: plannerModel,
      systemInstruction: PLANNER_PROMPT,
      tools: [{ functionDeclarations: [API_DOCS_TOOL_GEMINI] }],
      generationConfig: {
        temperature: 0.2,
        maxOutputTokens: 32768,
        // @ts-ignore - thinkingConfig may not be in types yet
        thinkingConfig: { thinkingBudget: 2048 },
      } as any,
    });

    const today = new Date().toISOString().split("T")[0];
    let fileInfo = "";
    for (const [name, f] of fileMap.entries()) {
      fileInfo += `\nFile "${name}": ${f.headers ? `CSV with ${f.rows?.length} rows, columns: ${f.headers.join(", ")}` : `${f.lines.length} lines`}`;
      if (f.rows && f.rows.length > 0) {
        fileInfo += `\nFirst 3 rows: ${JSON.stringify(f.rows.slice(0, 3).map((row) => Object.fromEntries(f.headers!.map((h, i) => [h, row[i] ?? ""]))))}`;
      }
    }

    const chat = genModel.startChat();
    let response = await chat.sendMessage([{ text: `Today's date: ${today}\n${fileInfo}\n\nTask: ${prompt}` }]);

    let iterations = 0;
    while (iterations < 10) {
      iterations++;
      const candidate = response.response.candidates?.[0];
      if (!candidate) break;

      const plannerParts = candidate.content?.parts || [];
      const functionCalls = plannerParts.filter((p: { functionCall?: unknown }) => p.functionCall);
      if (functionCalls.length === 0) {
        const textParts = plannerParts.filter((p: { text?: string }) => p.text);
        const planText = textParts.map((p: { text?: string }) => p.text || "").join("\n");
        console.log(`Plan generated (${iterations} iterations)`);
        return planText;
      }

      const functionResponses: Part[] = [];
      for (const part of functionCalls) {
        const fc = (part as { functionCall: { name: string; args: Record<string, string> } }).functionCall;
        const result = handleApiDocsQuery(fc.args as Parameters<typeof handleApiDocsQuery>[0]);
        functionResponses.push({ functionResponse: { name: fc.name, response: result as Record<string, unknown> } });
      }
      response = await chat.sendMessage(functionResponses);
    }
  } else if (plannerProvider === "anthropic") {
    const anthropic = new Anthropic();
    const today = new Date().toISOString().split("T")[0];
    let fileInfo = "";
    for (const [name, f] of fileMap.entries()) {
      fileInfo += `\nFile "${name}": ${f.headers ? `CSV with ${f.rows?.length} rows, columns: ${f.headers.join(", ")}` : `${f.lines.length} lines`}`;
      if (f.rows && f.rows.length > 0) {
        fileInfo += `\nFirst 3 rows: ${JSON.stringify(f.rows.slice(0, 3).map((row) => Object.fromEntries(f.headers!.map((h, i) => [h, row[i] ?? ""]))))}`;
      }
    }

    const tools: Anthropic.Tool[] = [{
      name: "query_api_docs",
      description: "Search the Tripletex API documentation. Actions: list_categories, list_endpoints, get_endpoint, get_schema, search",
      input_schema: {
        type: "object" as const,
        properties: {
          action: { type: "string", description: "list_categories, list_endpoints, get_endpoint, get_schema, search" },
          query: { type: "string", description: "Search keyword" },
          method: { type: "string", description: "HTTP method filter" },
          path: { type: "string", description: "Endpoint path" },
          schema: { type: "string", description: "Schema name" },
          category: { type: "string", description: "Category filter" },
        },
        required: ["action"],
      },
    }];

    let messages: Anthropic.MessageParam[] = [
      { role: "user", content: `Today's date: ${today}\n${fileInfo}\n\nTask: ${prompt}` },
    ];

    let iterations = 0;
    while (iterations < 10) {
      iterations++;
      const response = await anthropic.messages.create({
        model: plannerModel,
        max_tokens: 4096,
        system: PLANNER_PROMPT,
        tools,
        messages,
      });

      if (response.stop_reason === "end_turn") {
        const textBlocks = response.content.filter((b): b is Anthropic.TextBlock => b.type === "text");
        const planText = textBlocks.map(b => b.text).join("\n");
        console.log(`Plan generated (${iterations} iterations)`);
        return planText;
      }

      if (response.stop_reason === "tool_use") {
        const toolUseBlocks = response.content.filter((b): b is Anthropic.ToolUseBlock => b.type === "tool_use");
        messages.push({ role: "assistant", content: response.content });

        const toolResults: Anthropic.ToolResultBlockParam[] = [];
        for (const block of toolUseBlocks) {
          const result = handleApiDocsQuery(block.input as Parameters<typeof handleApiDocsQuery>[0]);
          toolResults.push({ type: "tool_result", tool_use_id: block.id, content: JSON.stringify(result) });
        }
        messages.push({ role: "user", content: toolResults });
      } else {
        break;
      }
    }
  }

  return null;
}

// ============================================================
// Public entry point
// ============================================================

const DEFAULT_MODELS: Record<LLMProvider, string> = {
  anthropic: "gemini-3-flash-preview",
  gemini: "gemini-3-flash-preview",
};

export { createTripletexApi, type TripletexApi, type Schemas };

export async function runAgent(
  client: TripletexClient,
  prompt: string,
  files: FileAttachment[],
  provider?: LLMProvider,
  model?: string,
): Promise<{ callCount: number; errorCount: number; messages: unknown[] }> {
  const executorProvider: LLMProvider = provider
    || (process.env.EXECUTOR_PROVIDER as LLMProvider)
    || (process.env.LLM_PROVIDER as LLMProvider)
    || "gemini";
  const resolvedModel = model
    || process.env.EXECUTOR_MODEL
    || process.env.LLM_MODEL
    || DEFAULT_MODELS[executorProvider];
  // Decode embedded base64 CSV in prompt (some tasks embed CSV as base64 in the prompt text)
  const decoded = tryDecodeEmbeddedCsv(prompt);
  const allFiles = [...files, ...decoded.extraFiles];
  let augmentedPrompt = decoded.cleanedPrompt;

  // For bank reconciliation: parse CSV deterministically and add structured data
  if (isBankReconciliationTask(augmentedPrompt)) {
    for (const file of allFiles) {
      if (file.mime_type === "text/csv" || file.filename.endsWith(".csv")) {
        const raw = Buffer.from(file.content_base64, "base64").toString("utf-8");
        const txns = parseNorwegianBankCsv(raw);
        if (txns && txns.length > 0) {
          const structured = JSON.stringify(txns, null, 2);
          augmentedPrompt += `\n\n=== PARSED BANK TRANSACTIONS (use these, not raw CSV) ===\n${structured}\n\nROUTING RULES:\n- customer_payment: match to customer invoice by invoiceNumber, use PUT /invoice/{id}/:payment with paidAmount = transaction amount (NOT invoice total)\n- supplier_payment: match to supplier invoice by counterparty name, use POST /supplierInvoice/{id}/:addPayment\n- bank_fee (negative): POST /ledger/voucher debit 7770, credit 1920\n- bank_fee_refund (positive): POST /ledger/voucher debit 1920, credit 7770\n- CRITICAL: Check amountOutstanding > 0 before paying. If already paid, SKIP.\n- CRITICAL: Fetch supplier invoices with GET /supplierInvoice before matching outgoing payments.`;
          console.log(`Parsed ${txns.length} bank transactions from CSV`);
        }
      }
    }
  }

  const fileMap = parseFiles(allFiles);

  console.log(`Using ${executorProvider} / ${resolvedModel}`);

  if (executorProvider === "gemini") {
    return runGeminiAgent(client, augmentedPrompt, allFiles, resolvedModel, fileMap);
  }
  return runAnthropicAgent(client, augmentedPrompt, allFiles, resolvedModel, fileMap);
}
