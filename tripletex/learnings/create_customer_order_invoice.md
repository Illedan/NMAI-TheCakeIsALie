# Create customer + order + invoice

**Score:** 10/10
**Rounds:** 4
**Last run:** 8 calls, 1 errors
**Reason:** The customer was identified, the order was created with the correct products and prices, the order was successfully converted to an invoice, and full payment was registered. Verification confirmed all entities exist with the expected values.

## Representative prompt

Opprett ein ordre for kunden Vestfjord AS (org.nr 960144015) med produkta Konsulenttimar (1874) til 34750 kr og Nettverksteneste (9344) til 14350 kr. Konverter ordren til faktura og registrer full betaling.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **VAT Handling is Critical**: Always use `GET /ledger/vatType?typeOfVat=OUTGOING` to find the correct VAT IDs. Never assume IDs. If the task does not specify a VAT rate, use 25% (høy sats) for standard sales. For 0% VAT, distinguish between "exempt" (innenfor mva-loven) and "outside" (utenfor mva-loven).
2.  **Order/Invoice Workflow**: Always create the customer first, then the product (if it doesn't exist), then the order, and finally the invoice. Never attempt to create an invoice without a linked order.
3.  **Payment Registration**: Use `PUT /invoice/{id}/:payment` with `paymentDate`, `paymentTypeId`, and `paidAmount`. Always use `GET /invoice/paymentType` to find the correct incoming payment type ID.
4.  **Minimize API Calls**: Plan the workflow before executing. Use `GET` with specific filters (e.g., `organizationNumber=`, `number=`) instead of fetching large lists. Trust the `POST` response IDs instead of re-fetching data.
5.  **Data Verification**: After completing a task, perform targeted `GET` calls to verify that the created entities (customer, order, invoice) exist and contain the expected values (amounts, IDs, status).
6.  **Amount Fields**: When creating vouchers or order lines, ensure all required amount fields (e.g., `amount`, `amountCurrency`, `amountGross`, `amountGrossCurrency`) are set to the same value to avoid rounding errors or validation failures.
7.  **Avoid Beta Endpoints**: Do not use endpoints marked [BETA] (e.g., `POST /customer/list`). Use individual `POST` calls instead.
8.  **Date Handling**: Always use today's date (`2026-03-21`) unless the task specifies otherwise. For invoice due dates, calculate a standard term (e.g., 14 days) if not provided.
9.  **Avoid Redundant Calls**: Do not call `GET` for the same resource multiple times if the information is already available from a previous `GET` or `POST` response.
10. **Filter Correctly**: When searching for invoices or ledger entries, ensure `dateFrom` and `dateTo` are valid. `dateTo` must be strictly greater than `dateFrom` to avoid 422 validation errors. If searching for a single day, use `dateFrom=YYYY-MM-DD` and `dateTo=YYYY-MM-DD+1`.
11. **Invoice Creation Payload**: When creating an invoice via `POST /invoice`, ensure the body contains the `orders` array (e.g., `{"orders": [{"id": orderId}]}`) and the `invoiceDate`/`invoiceDueDate` fields. Do not pass these as query parameters if the endpoint expects them in the body.
12. **Avoid Unnecessary Retries**: If an API call fails with a 422, analyze the `validationMessages` carefully. Do not retry the exact same request; adjust the payload based on the error message.
