# Full project lifecycle

**Score:** 10/10
**Rounds:** 4
**Last run:** 19 calls, 3 errors
**Reason:** All project lifecycle steps were completed: project created with budget, timesheets for both employees recorded, supplier cost booked with correct VAT and project link, and customer invoice generated. Verification confirmed all entities and values match the task requirements.

## Representative prompt

Exécutez le cycle de vie complet du projet 'Migration Cloud Rivière' (Rivière SARL, nº org. 855961962) : 1) Le projet a un budget de 480500 NOK. 2) Enregistrez le temps : Camille Dubois (chef de projet, camille.dubois@example.org) 62 heures et Lucas Leroy (consultant, lucas.leroy@example.org) 108 he...

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **PROJECT MANAGER PERMISSIONS**: Before creating a project, verify the `projectManager` has the necessary access. If a `422` error occurs, do not retry with the same ID. List employees (`GET /employee`) and select one confirmed to have the required permissions.
2. **VOUCHER BALANCING & VAT**: Every `POST /ledger/voucher` must be perfectly balanced (sum of all `amount` fields = 0). When booking supplier costs with VAT, use three postings: net expense (debit), VAT (debit), and total liability (credit to 2400). Ensure all four amount fields (`amount`, `amountCurrency`, `amountGross`, `amountGrossCurrency`) are identical for each row. Do not use the `vatType` field on individual voucher postings to avoid rounding errors.
3. **TIMESHEET ACTIVITIES**: Always use existing project-specific activities (`activityType: "PROJECT_GENERAL_ACTIVITY"`) found via `GET /activity?projectId={id}`. Do not attempt to create new activities if the name already exists or if a suitable one is already available.
4. **API PARAMETER VALIDATION**: When using `GET` endpoints that require date ranges (like `/ledger/posting`, `/timesheet/entry`, or `/invoice`), always provide both `dateFrom` and `dateTo` to avoid `422` errors.
5. **MINIMIZE API CALLS**: Plan the entire workflow before executing. Use `GET` filters (e.g., `?organizationNumber=...`) to find IDs in a single call. Trust the `POST` response for created entity IDs instead of performing redundant `GET` calls to verify.
6. **INVOICE CREATION**: Always create a product, then an order, then an invoice. Ensure the `invoiceDueDate` is explicitly set (e.g., 14 days after `invoiceDate`) to avoid `422` errors. Always set `sendToCustomer=true` to ensure the invoice is processed.
7. **SUPPLIER VS CUSTOMER**: Always use the dedicated `/supplier` endpoint for suppliers. Do not use `/customer` with `isSupplier=true` as it may lead to inconsistencies or permission issues.
8. **REQUEST MAPPING ERRORS**: When `POST`ing to sub-resources (like `projectActivity`), avoid nested objects if the API expects flat query parameters or specific path structures. If a `422` "Request mapping failed" occurs, check if the endpoint requires query parameters instead of a JSON body.
