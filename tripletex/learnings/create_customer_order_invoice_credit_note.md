# Create customer + order + invoice + credit note

**Score:** 10/10
**Rounds:** 4
**Last run:** 8 calls, 1 errors
**Reason:** The customer was created, a product was successfully identified/created, an order was placed, the invoice was generated and sent, and a credit note was created for the invoice. All steps were verified via API calls.

## Representative prompt

Opprett kunde 'Kredit64381905 AS' (kred64381905@example.com). Lag bestilling med 'Lisens' 1 stk à 25000 kr eks. mva. Fakturer. Deretter lag en kreditnota for fakturaen.

## Learnings

{"learnings": [
  {"priority": 1, "issue": "Product creation failures due to existing names", "warning": "Always check if a product exists using GET /product?query=... before attempting to POST /product. If it exists, use the existing ID.", "solution": "Use GET /product?query=... to find the ID. If not found, then POST /product."},
  {"priority": 2, "issue": "Unnecessary API calls", "warning": "Avoid redundant GET calls after a successful POST. Trust the response body of the POST request.", "solution": "Extract IDs directly from the POST response body."},
  {"priority": 3, "issue": "VAT type selection errors", "warning": "Always use GET /ledger/vatType to find the correct ID. Never guess IDs. Ensure the typeOfVat matches the transaction (OUTGOING for sales, INCOMING for purchases).", "solution": "Call GET /ledger/vatType?typeOfVat=OUTGOING&from=0&count=100 once at the start of the session."},
  {"priority": 4, "issue": "Credit Note creation", "warning": "There is no direct 'create credit note' endpoint. Credit notes must be created by generating a new order with negative quantities for the original items and invoicing it, OR by using the /invoice/{id}/:createCreditNote endpoint.", "solution": "Use the /invoice/{id}/:createCreditNote endpoint for existing invoices."},
  {"priority": 5, "issue": "Date filtering errors", "warning": "GET endpoints with date filters require both 'from' and 'to' parameters. 'to' is exclusive.", "solution": "Always provide both parameters and set 'to' to the next day for single-day queries."},
  {"priority": 6, "issue": "Batch endpoint limitations", "warning": "Avoid batch endpoints (e.g., /customer/list, /product/list) as they are often unstable or restricted.", "solution": "Create entities individually using POST /customer or POST /product."},
  {"priority": 7, "issue": "Voucher posting errors", "warning": "Every voucher posting must have a 'row' field (sequential integers) and all four amount fields (amount, amountCurrency, amountGross, amountGrossCurrency) set to the same value.", "solution": "Include 'row' and set all four amount fields to the same value."},
  {"priority": 8, "issue": "Customer duplication", "warning": "Multiple customers with the same name can be created if not checked first.", "solution": "Always search for existing customers by email or organization number before creating a new one."}
]}
