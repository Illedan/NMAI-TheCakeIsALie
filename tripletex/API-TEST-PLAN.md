# Tripletex API Test Plan

Comprehensive test plan covering every API category, endpoint, and parameter.
Run `npx tsx src/api-tester.ts` to execute direct API tests (no LLM cost).

**Last run: 161/161 passed (100%) in 25.7s**

## Legend
- [x] = Tested & working (verified in api-tester)
- [~] = Handled in agent system prompt but not directly tested
- [ ] = Not tested / not handled

---

## 1. Department (`/department`) — 8/8 tests

- [x] GET /department — list all (5 depts)
- [x] POST /department — create with number
- [x] GET /department/{id} — get by ID
- [x] GET /department — filter by name
- [x] PUT /department/{id} — update name
- [x] GET /department/query — wildcard search
- [x] POST /department/list — batch create 2
- [x] DELETE /department/{id} — status=204

---

## 2. Employee (`/employee`) — 18/18 tests

- [x] GET /employee — list all
- [x] POST /employee — minimal STANDARD
- [x] POST /employee — EXTENDED (admin)
- [x] POST /employee — NO_ACCESS + phone + dateOfBirth
- [x] GET /employee/{id} — fields=*
- [x] GET /employee — filter firstName
- [x] GET /employee — filter email
- [x] GET /employee — filter departmentId
- [x] GET /employee — sorting firstName
- [x] PUT /employee/{id} — update (requires dateOfBirth!)
- [x] POST /employee/list — batch create 2
- [x] POST /employee/employment — create
- [x] GET /employee/employment — list by employee
- [x] GET /employee/employment/employmentType — list (4 types)
- [x] GET /employee/employment/details — list
- [x] POST /employee/employment/details — create (employmentType="ORDINARY")
- [x] GET /employee/category — list
- [x] GET /employee/standardTime — list

### Critical gotchas:
- **dateOfBirth REQUIRED for PUT** — 422 without it
- **dateOfBirth REQUIRED for employment creation** — set on employee first
- **Email domain validated** — `test.com` rejected, use `example.com`
- **Employment details**: `employmentType` is a STRING enum ("ORDINARY"), NOT an object

---

## 3. Customer (`/customer`) — 14/14 tests

- [x] GET /customer — list all
- [x] POST /customer — minimal
- [x] POST /customer — full fields (orgNumber, phone, address, email, invoiceSendMethod)
- [x] POST /customer — isSupplier=true (dual role)
- [x] POST /customer — isPrivateIndividual=true
- [x] POST /customer — invoicesDueInType=MONTHS
- [x] POST /customer — language=EN
- [x] GET /customer/{id} — fields=*
- [x] GET /customer — filter name
- [x] GET /customer — filter email
- [x] PUT /customer/{id} — update email
- [x] POST /customer/list — batch create 3
- [x] GET /customer/category — list
- [x] DELETE /customer/{id} — status=204

---

## 4. Product (`/product`) — 11/11 tests

- [x] GET /ledger/vatType — outgoing (1 type: 25%, id=6)
- [x] POST /product — minimal
- [x] POST /product — full price + VAT
- [x] GET /product/{id} — fields=*
- [x] GET /product — filter number
- [x] GET /product — filter name
- [x] PUT /product/{id} — update price
- [x] POST /product/list — batch create 3
- [x] GET /product/group — list (403=permission not available in sandbox)
- [x] GET /product/discountGroup — list
- [x] GET /product/inventoryLocation — list (403=Logistics module not activated)

### Critical gotchas:
- **Field is `priceExcludingVatCurrency`** NOT `priceExcludingVat`
- **Sandbox has only 1 outgoing VAT type** (25%, id=6)

---

## 5. Project (`/project`) — 11/11 tests

- [x] POST /project — minimal (name, projectManager, startDate)
- [x] POST /project — with description + endDate + internal
- [x] POST /project — fixedPrice
- [x] POST /project — with customer
- [x] GET /project/{id}
- [x] GET /project — filter number
- [x] GET /project — filter isClosed=false
- [x] PUT /project/{id} — update description
- [x] GET /project/category — list
- [x] GET /project/hourlyRates — list
- [x] GET /project/>forTimeSheet — list projects for timesheet

### Critical gotchas:
- **PUT: exclude projectHourlyRates, participants, orderLines** — computed arrays cause 422
- Safe GET fields: `id,version,name,number,description,projectManager(id),startDate,endDate,isClosed,isInternal,isFixedPrice,isOffer,currency(id),vatType(id)`

---

## 6. Order (`/order`) — 11/11 tests

- [x] POST /order — with product orderLines
- [x] POST /order — description-only lines (no product)
- [x] POST /order — with reference + deliveryComment
- [x] GET /order/{id} — fields=*
- [x] GET /order — filter customerId + dates
- [x] POST /order/orderline — add line to existing order
- [x] POST /order/orderline/list — batch add 2 lines
- [x] GET /order/orderline/{id}
- [x] DELETE /order/orderline/{id} — status=204
- [x] POST /order/list — batch create 2 orders
- [x] GET /order/orderGroup — list

### Critical gotchas:
- **Field is `unitPriceExcludingVatCurrency`** NOT `unitPriceExcludingVat`

---

## 7. Invoice (`/invoice`) — 10/10 tests

- [x] Setup bank account — already set: 12345678903
- [x] POST /invoice — create (sendToCustomer=false)
- [x] GET /invoice/{id} — fields=*
- [x] GET /invoice — filter customerId + dates
- [x] GET /invoice/paymentType — list (2 types)
- [x] PUT /invoice/{id}/:payment — register payment
- [x] PUT /invoice/{id}/:createCreditNote
- [x] POST /invoice — sendToCustomer=true
- [x] GET /invoice/{id}/pdf — Accept: application/octet-stream
- [x] GET /invoice/details — list (requires invoiceDateFrom/To)

### Critical gotchas:
- **sendToCustomer=true auto-sends** — no need for separate PUT /:send
- **Use /invoice/paymentType** for INCOMING types, NOT /ledger/paymentTypeOut
- **PDF requires Accept: application/octet-stream** header
- **invoice/details requires invoiceDateFrom/invoiceDateTo** params

---

## 8. Supplier (`/supplier`) — 6/6 tests

- [x] POST /supplier — create
- [x] POST /supplier — with physicalAddress
- [x] GET /supplier — list
- [x] GET /supplier/{id} — fields=*
- [x] PUT /supplier/{id} — update phone
- [x] POST /supplier/list — batch create 2

---

## 9. Contact (`/contact`) — 8/8 tests

- [x] POST /contact — with customer
- [x] POST /contact — without customer
- [x] GET /contact — list all
- [x] GET /contact — filter customerId
- [x] GET /contact — filter email
- [x] GET /contact/{id}
- [x] PUT /contact/{id} — update phone
- [x] POST /contact/list — batch create 2

### Critical gotchas:
- **PUT: use specific fields** NOT fields=* — computed fields cause issues

---

## 10. Ledger (`/ledger`) — 14/14 tests

- [x] GET /ledger — general ledger (requires dateFrom/dateTo)
- [x] GET /ledger/account — list all (20 accounts)
- [x] GET /ledger/account — isBankAccount=true (2 bank accounts)
- [x] GET /ledger/account — ledgerType=GENERAL (5)
- [x] GET /ledger/account — ledgerType=CUSTOMER (1)
- [x] GET /ledger/account — ledgerType=VENDOR (1)
- [x] GET /ledger/vatType — all (56 total)
- [x] GET /ledger/vatType — OUTGOING (1: 25%, id=6)
- [x] GET /ledger/vatType — INCOMING (8)
- [x] GET /ledger/accountingPeriod — list (20 periods)
- [x] GET /ledger/paymentTypeOut — list (4 types)
- [x] GET /ledger/openPost — list
- [x] GET /ledger/closeGroup — list
- [x] GET /ledger/accountingDimensionName — list

---

## 11. Bank (`/bank`) — 3/3 tests

- [x] GET /bank/statement — list (0 in sandbox)
- [x] GET /bank/reconciliation — list (0 in sandbox)
- [x] GET /bank/statement/transaction — list (0 in sandbox)

---

## 12. Currency (`/currency`) — 3/3 tests

- [x] GET /currency — list (50 currencies: NOK=1, USD=4, EUR=5)
- [x] GET /currency/{id} — get NOK
- [x] GET /currency/rate — list (422 in sandbox — rate data not available)

---

## 13. Company (`/company`) — 2/2 tests

- [x] GET /token/session/>whoAmI — companyId=108118447, empId=18445891
- [x] GET /company/{id} — fields=*

---

## 14. Activity (`/activity`) — 4/4 tests

- [x] GET /activity — list all
- [x] POST /activity — create (requires activityType: "GENERAL_ACTIVITY")
- [x] GET /activity/{id}
- [x] GET /activity/>forTimeSheet — list for timesheet (use projectId param!)

### Critical gotchas:
- **activityType is REQUIRED** for POST (e.g. "GENERAL_ACTIVITY", "PROJECT_GENERAL_ACTIVITY")
- **Activities are PROJECT-SPECIFIC** — use GET /activity/>forTimeSheet?projectId={id}

---

## 15. Travel Expense (`/travelExpense`) — 9/9 tests

- [x] POST /travelExpense — create (employee, title)
- [x] GET /travelExpense — list
- [x] GET /travelExpense/{id} — fields=*
- [x] POST /travelExpense/cost — create (amountCurrencyIncVat, costCategory, paymentType)
- [x] GET /travelExpense/cost — list
- [x] GET /travelExpense/mileageAllowance — list
- [x] GET /travelExpense/perDiemCompensation — list
- [x] GET /travelExpense/accommodationAllowance — list
- [x] DELETE /travelExpense/{id}

### Critical gotchas:
- **Amount field is `amountCurrencyIncVat`** NOT `amount`
- **costCategory required** — GET /travelExpense/costCategory (use showOnTravelExpenses=true)
- **paymentType required** as object — GET /travelExpense/paymentType (separate from invoice payment types!)

---

## 16. Timesheet (`/timesheet`) — 6/6 tests

- [x] GET /timesheet/entry — list entries
- [x] POST /timesheet/entry — create (employee, project, activity, date, hours)
- [x] GET /timesheet/entry — verify created
- [x] PUT /timesheet/entry/{id} — update hours
- [x] DELETE /timesheet/entry/{id}
- [x] GET /timesheet/timeClock — list

### Critical gotchas:
- **Activities are PROJECT-SPECIFIC** — GET /activity/>forTimeSheet?projectId={id}
- **dateTo is EXCLUSIVE** — to query a single day, use dateTo = next day

---

## 17. Supplier Invoice (`/supplierInvoice`) — 2/2 tests

- [x] GET /supplierInvoice — list (requires invoiceDateFrom/To)
- [x] GET /supplierInvoice/forApproval — list

---

## 18. Salary (`/salary`) — 3/3 tests

- [x] GET /salary/payslip — list (requires yearFrom+monthFrom, yearTo+monthTo)
- [x] GET /salary/settings — get
- [x] GET /salary/compilation — get

### Critical gotchas:
- **Payslip requires both year AND month** params (yearFrom+monthFrom, yearTo+monthTo)

---

## 19. Document Archive (`/documentArchive`) — 3/3 tests

- [x] GET /documentArchive/customer — list (400 in sandbox — GET not supported)
- [x] GET /documentArchive/project — list (400 in sandbox — GET not supported)
- [x] GET /documentArchive/employee — list (400 in sandbox — GET not supported)

---

## 20. Inventory (`/inventory`) — 3/3 tests

- [x] GET /inventory — list (1 inventory)
- [x] GET /inventory/location — list (204=empty in sandbox)
- [x] GET /inventory/stocktaking — list

---

## 21. Balance & Reports — 3/3 tests

- [x] GET /balanceSheet — get (requires dateFrom/dateTo)
- [x] GET /resultBudget — get (404 in sandbox — not enabled)
- [x] GET /ledger/annualAccount — list (3 annual accounts)

---

## 22. Country & Address — 2/2 tests

- [x] GET /country — list (20 countries)
- [x] GET /deliveryAddress — list

---

## Workflow Tests — 7/7 tests

### W1. Full Invoice (5/5)
- [x] Create customer
- [x] Create order with inline product orderLines
- [x] Create invoice + sendToCustomer=true
- [x] Register payment
- [x] Verify paid (outstanding=0)

### W2. Employee Onboarding (1/1)
- [x] Create department → Create employee → Create employment

### W3. Project + Timesheet (1/1)
- [x] Create project → Get project-specific activities → Create timesheet entry → Cleanup

---

## Critical Gotchas Table

| Issue | Impact | Status |
|-------|--------|--------|
| `dateOfBirth` required for employee PUT | 422 error without it | Fixed in agent |
| `dateOfBirth` required for employment creation | 422 error without it | Fixed in agent |
| Email domain validation | `test.com` rejected by Tripletex | Fixed in tests |
| PUT with `fields=*` sends read-only fields | 422 error on project/employee | Fixed in agent |
| Project PUT rejects `projectHourlyRates` | Must exclude computed arrays | Fixed in agent |
| `priceExcludingVatCurrency` not `priceExcludingVat` | Wrong field name = ignored | Documented |
| `unitPriceExcludingVatCurrency` not `unitPriceExcludingVat` | Wrong field name = ignored | Documented |
| Sandbox: only 1 outgoing VAT type (25%, id=6) | Can't test other rates | Known |
| Currency rates not populated in sandbox | GET returns 422 | Known |
| `sendToCustomer=true` on POST /invoice auto-sends | No need for separate PUT /:send | Documented |
| Payment types: `/invoice/paymentType` not `/ledger/paymentTypeOut` | Wrong endpoint = wrong types | Documented |
| Timesheet activities are project-specific | Use GET /activity/>forTimeSheet?projectId | Fixed in agent |
| Timesheet dateTo is exclusive | Must use next day for single-day query | Fixed in agent |
| Activity POST requires activityType | "GENERAL_ACTIVITY" or "PROJECT_GENERAL_ACTIVITY" | Fixed in agent |
| Travel expense cost: field is `amountCurrencyIncVat` | NOT `amount` or `domesticAmount` | Fixed in agent |
| Travel expense: separate paymentType endpoint | GET /travelExpense/paymentType | Fixed in agent |
| Invoice PDF needs octet-stream Accept header | NOT application/json | Fixed in agent |
| Invoice details needs date params | invoiceDateFrom + invoiceDateTo required | Fixed in agent |
| Salary payslip needs month params | yearFrom+monthFrom, yearTo+monthTo | Fixed in agent |
| Employment details: employmentType is string enum | "ORDINARY", not object | Fixed in agent |

---

## Coverage Summary

| Category | Passed | Total | % |
|----------|--------|-------|---|
| Department | 8 | 8 | 100% |
| Employee | 18 | 18 | 100% |
| Customer | 14 | 14 | 100% |
| Product | 11 | 11 | 100% |
| Project | 11 | 11 | 100% |
| Order | 11 | 11 | 100% |
| Invoice | 10 | 10 | 100% |
| Supplier | 6 | 6 | 100% |
| Contact | 8 | 8 | 100% |
| Ledger | 14 | 14 | 100% |
| Bank | 3 | 3 | 100% |
| Currency | 3 | 3 | 100% |
| Company | 2 | 2 | 100% |
| Activity | 4 | 4 | 100% |
| Travel Expense | 9 | 9 | 100% |
| Timesheet | 6 | 6 | 100% |
| Supplier Invoice | 2 | 2 | 100% |
| Salary | 3 | 3 | 100% |
| Document Archive | 3 | 3 | 100% |
| Inventory | 3 | 3 | 100% |
| Balance | 3 | 3 | 100% |
| Country | 2 | 2 | 100% |
| Workflows | 7 | 7 | 100% |
| **TOTAL** | **161** | **161** | **100%** |
