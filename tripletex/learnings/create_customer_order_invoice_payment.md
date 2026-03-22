# Create customer + order + invoice + payment

**Score:** 10/10
**Rounds:** 6
**Last run:** 7 calls, 0 errors
**Reason:** The task was fully completed as requested: the customer was identified, the order was created with the correct products and prices, the order was converted to an invoice, and the full payment was registered. Verification confirmed all steps were successful and the invoice balance is zero.

## Representative prompt

Erstellen Sie einen Auftrag für den Kunden Grünfeld GmbH (Org.-Nr. 920238882) mit den Produkten Datenberatung (5628) zu 23000 NOK und Cloud-Speicher (1573) zu 16550 NOK. Wandeln Sie den Auftrag in eine Rechnung um und registrieren Sie die vollständige Zahlung.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **Date Filtering (CRITICAL):** When using `GET` endpoints with date filters (e.g., `invoiceDateFrom`, `invoiceDateTo`), `invoiceDateFrom` must be strictly less than or equal to `invoiceDateTo`. If you need to query a single day, use `invoiceDateFrom=YYYY-MM-DD` and `invoiceDateTo=YYYY-MM-DD` (or the next day if the API requires an exclusive range).
2.  **VAT Handling (CRITICAL):** Always verify the `vatType` for products and order lines using `GET /ledger/vatType`. If the task does not specify a VAT rate, default to 25% (høy sats) unless the product is inherently exempt. Never guess IDs; always look them up.
3.  **Order Line Embedding:** Always embed `orderLines` directly within the `POST /order` request body. Do not attempt to create order lines via a separate `POST /order/{id}/orderLines` endpoint, as this often results in 404 errors.
4.  **Customer/Supplier Existence:** Always check for the existence of a customer or supplier using `GET /customer?organizationNumber=...` or `GET /supplier?organizationNumber=...` before attempting to create a new one to avoid duplicates and 422 errors.
5.  **API Efficiency:** Minimize API calls by using specific field filters (e.g., `fields=id,version,name`) instead of `fields=*`. Trust the response from a `POST` request to obtain IDs for subsequent steps; avoid unnecessary `GET` calls to verify what was just created unless required for debugging.
6.  **Payment Registration:** Use `PUT /invoice/{id}/:payment` to register payments. Always retrieve the correct `paymentTypeId` via `GET /invoice/paymentType` first. Ensure the `paidAmount` matches the total invoice amount (including VAT).
7.  **Error Handling:** On 422 errors, always inspect the `validationMessages` field in the response to identify the specific missing or incorrect fields. Never retry the same failing request more than once without changing the parameters or body based on the error message.
8.  **Anti-Loop Rule:** If you have made the same API call (same method + path + params) more than twice and received the same result, stop immediately. Analyze the previous responses to identify why the request is failing and adjust your strategy.
9.  **Verification Strategy:** When asked to verify work, use targeted `GET` calls on the specific IDs created (e.g., `GET /invoice/{id}`) rather than broad searches that return multiple results, which can be confusing and inefficient.
