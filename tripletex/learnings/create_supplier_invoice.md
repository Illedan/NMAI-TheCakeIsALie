# Create supplier + invoice

**Score:** 10/10
**Rounds:** 4
**Last run:** 8 calls, 2 errors
**Reason:** The supplier 'Supplier381905 AS' was successfully created with the correct email. The supplier invoice 'FAKTURA-381905' was registered as a voucher (type 9777825) with the correct total amount (12500), net amount (10000 on account 6300), and VAT amount (2500 on account 2710). All postings are balanced, include the supplier reference on the AP line, and use the correct account IDs verified via API.

## Representative prompt

Opprett leverandøren "Supplier381905 AS" med e-post sup381905@example.com. Registrer deretter leverandørfaktura FAKTURA-381905 fra denne leverandøren. Beløpet er 12500 kr inklusiv MVA (25%). Det gjelder kontortjenester (konto 6300). Registrer fakturaen som et bilag i regnskapet.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **Voucher Posting Accuracy (CRITICAL):** When using `POST /ledger/voucher` for supplier invoices, you must manually calculate and post the three lines: Expense (Debit), VAT (Debit), and AP/Supplier Debt (Credit). Ensure all four amount fields (`amount`, `amountCurrency`, `amountGross`, `amountGrossCurrency`) are identical for each row. Do NOT use `vatType` on these postings, as it often causes rounding errors or validation failures.
2.  **Supplier Invoice Fallback:** The `/incomingInvoice` endpoint is often restricted or requires specific schema structures. If a `POST /incomingInvoice` fails with a `422` or `403`, immediately fallback to `POST /ledger/voucher` using the "Leverandørfaktura" voucher type (`GET /ledger/voucherType` to find the ID).
3.  **API Error Handling:** If a `422` error occurs, inspect the `validationMessages` field in the response. It explicitly states which field is missing or invalid. Do not retry the same request; adjust the payload based on the error message.
4.  **Account Verification:** Always `GET /ledger/account` by number before posting to confirm the correct `id` and `vatLocked` status. Do not assume account IDs.
5.  **Efficiency:** Minimize API calls by filtering with `?name=` or `?number=` instead of fetching lists. Do not repeat `GET` calls for the same resource if the data has already been retrieved.
6.  **Supplier Creation:** When creating a supplier, use `POST /supplier` with `isSupplier:true`. Always verify the creation by checking the returned `id` and ensuring the name and email match the request.
7.  **Data Verification:** After any `POST` operation, verify the result by performing a `GET` on the specific resource ID to ensure all fields were correctly persisted.
8.  **Avoid Beta Endpoints:** Do not use endpoints marked [BETA] in the API docs, as they often return 403. Use standard CRUD endpoints instead.
9.  **Voucher Payload:** Do not include `sendToLedger` in the `POST /ledger/voucher` body; it is not a valid field and will cause a 422 error. The voucher is posted automatically upon creation.
10. **Supplier Reference:** When posting a supplier invoice voucher, the `supplier` object (containing the `id`) must be included ONLY on the AP (2400) posting row, not on the expense or VAT rows.
