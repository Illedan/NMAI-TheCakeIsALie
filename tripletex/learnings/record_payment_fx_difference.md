# Record payment + FX difference

**Score:** 10/10
**Rounds:** 9
**Last run:** 7 calls, 1 errors
**Reason:** The task was fully completed: the payment was registered on the existing invoice, the currency gain (agio) was calculated correctly based on the difference between the original and payment exchange rates, and a voucher was posted to the correct accounts (1500 and 8060) with the customer linked to the receivable posting. All steps were verified via API calls.

## Representative prompt

Me sende ein faktura på 11219 EUR til Bølgekraft AS (org.nr 825006206) då kursen var 10.02 NOK/EUR. Kunden har no betalt, men kursen er 10.29 NOK/EUR. Registrer betalinga og bokfør valutadifferansen (agio) på rett konto.

## Learnings

{
  "learnings": [
    {
      "priority": 1,
      "warning": "Verify the existence of all required entities (customers, invoices, products) before attempting financial operations.",
      "solution": "Perform a targeted search (e.g., by `organizationNumber` for customers or `invoiceNumber` for invoices) immediately. If the entity is not found, do not proceed; report the missing data and stop."
    },
    {
      "priority": 2,
      "warning": "When registering payments for foreign currency invoices, the `paidAmountCurrency` field is mandatory.",
      "solution": "Always include both `paidAmount` (in base currency) and `paidAmountCurrency` (in the original invoice currency) when calling the `PUT /invoice/{id}/:payment` endpoint to avoid validation errors."
    },
    {
      "priority": 3,
      "warning": "Voucher postings involving customers or suppliers require specific object structures.",
      "solution": "When posting to accounts like 1500 (receivables) or 2400 (payables), the customer or supplier must be passed as an object: `customer: {id: X}` or `supplier: {id: Y}`. Passing just the ID integer will cause a 422 validation error."
    },
    {
      "priority": 4,
      "warning": "Always include mandatory date parameters (`invoiceDateFrom` and `invoiceDateTo`) when searching for invoices.",
      "solution": "Omitting these parameters will result in a 422 error. Use a broad range (e.g., 2020-01-01 to 2030-12-31) if the specific date is unknown, but always include them."
    },
    {
      "priority": 5,
      "warning": "Minimize total API calls to improve efficiency.",
      "solution": "Plan all steps before making any API calls. Use IDs from previous responses directly. Avoid unnecessary GET calls to verify what you just created; trust the POST response."
    },
    {
      "priority": 6,
      "warning": "Avoid beta endpoints.",
      "solution": "Do not use endpoints marked [BETA] in the API documentation, as they often return 403 errors. Use stable alternatives."
    },
    {
      "priority": 7,
      "warning": "Incorrect usage of `GET /ledger/voucher` with date parameters.",
      "solution": "When searching for a specific voucher by ID, use `GET /ledger/voucher/{id}` directly instead of the search endpoint, which requires mandatory date range parameters."
    }
  ]
}
