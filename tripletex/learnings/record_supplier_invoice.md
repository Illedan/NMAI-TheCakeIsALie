# Record supplier invoice

**Score:** 10/10
**Rounds:** 10
**Last run:** 8 calls, 1 errors
**Reason:** The supplier invoice was correctly recorded as a voucher with the appropriate accounts (6700 for office services, 2710 for VAT, 2400 for AP), correct amounts (net 4440, VAT 1110, total 5550), and the supplier linked to the AP posting. Account 7100 was avoided as it is restricted for supplier invoices, and 6700 was used as a valid alternative.

## Representative prompt

Wir haben die Rechnung INV-2026-2399 vom Lieferanten Waldstein GmbH (Org.-Nr. 859252303) über 5550 NOK einschließlich MwSt. erhalten. Der Betrag betrifft Bürodienstleistungen (Konto 7100). Erfassen Sie die Lieferantenrechnung mit der korrekten Vorsteuer (25 %).

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **ACCOUNT VALIDATION IS MANDATORY**: Before posting to an account, check `isApplicableForSupplierInvoice` via `GET /ledger/account`. If an account is locked for supplier invoices (like 7100), do not force the posting. Choose the most appropriate alternative that is permitted for supplier invoices (e.g., 6700 for general services).
2.  **VOUCHER POSTING RULES**: Every posting in a voucher must include all four amount fields (`amount`, `amountCurrency`, `amountGross`, `amountGrossCurrency`) set to the exact same value. Postings must be balanced (sum to 0). Every posting must have a sequential `row` integer.
3.  **SUPPLIER INVOICE WORKFLOW**: Always use `GET /ledger/voucherType` to find the ID for "Leverandørfaktura" and include it in the voucher body. Always include the `supplier` object on the AP (2400) posting.
4.  **VAT CALCULATION**: When booking supplier invoices manually, calculate net and VAT amounts precisely. Use `net = total / 1.25` and `vat = total - net`. Do not use `vatType` on manual voucher postings to avoid rounding errors; instead, book the VAT amount directly to the VAT account (e.g., 2710).
5.  **MINIMIZE API CALLS**: Plan the entire workflow before starting. Use `GET` filters (e.g., `number=`, `organizationNumber=`) to avoid large list responses and unnecessary pagination. Trust the `POST` response for IDs rather than performing follow-up `GET` calls.
6.  **AVOID LOOPING**: If a `GET` call returns the same result 3 times, stop immediately. Re-evaluate the approach or the endpoint parameters.
7.  **DATE HANDLING**: Always use the date specified in the task (e.g., invoice date from PDF). If no date is specified, use today's date.
8.  **ERROR RECOVERY**: If a request fails with 422, check the validation messages and the endpoint reference. Do not retry the same failing request more than once. If an account is restricted, do not attempt to bypass system constraints.
9.  **AVOID BETA ENDPOINTS**: Do not use endpoints marked [BETA] in the API docs (e.g., `POST /customer/list`). Use individual `POST` calls instead.
