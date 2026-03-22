# Record payment

**Score:** 10/10
**Rounds:** 5
**Last run:** 2 calls, 0 errors
**Reason:** The task was to register payment for an invoice that was already fully paid. I verified the customer and the invoice status, confirmed the outstanding amount was 0, and reported that the task was already complete.

## Representative prompt

Kunden Nordhav AS (org.nr 841333608) har en utestående faktura på 14200 kr eksklusiv MVA for "Skylagring". Registrer full betaling på denne fakturaen.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **VERIFY BEFORE ACTING**: Always check the current status of an invoice (e.g., `amountOutstanding`) before attempting to register a payment. If `amountOutstanding` is 0, the invoice is already settled, and no further action is required.
2. **VAT-LOCKED ACCOUNTS AND REVENUE POSTINGS**: Revenue accounts (3000-3999) are locked to specific VAT types. Always GET the account first to find its `vatType`, then use that exact ID. Revenue postings require a `customer` object; AP postings (2400) require a `supplier` object.
3. **INVOICE WORKFLOW**: Always create the customer, then the product, then the order, then the invoice. Never attempt to create an invoice without an order. Always pass `sendToCustomer=true` to ensure the invoice is sent.
4. **PAYMENT REGISTRATION**: Use `PUT /invoice/{id}/:payment` with `paymentDate`, `paymentTypeId`, and `paidAmount`. Do not use `POST` for payments. Always GET `invoice/paymentType` first to find the correct ID.
5. **API EFFICIENCY**: Plan all steps before executing. Use `GET` with specific filters (e.g., `organizationNumber=`) rather than listing all entities. Avoid unnecessary `GET` calls after a successful `POST` if the response already contains the necessary information.
6. **ERROR HANDLING**: If a `POST` fails with 422, check the `validationMessages` and adjust the body. Do not retry the same failing request more than twice. If a loop occurs, stop and try a different approach (e.g., searching by name instead of number).
7. **DATE FORMATS**: Always use `YYYY-MM-DD`. For `GET /invoice` and `GET /ledger/voucher`, `dateFrom` and `dateTo` are mandatory.
8. **AVOID BETA ENDPOINTS**: Do not use endpoints marked [BETA] (e.g., `POST /customer/list`). Use individual `POST` calls instead.
9. **TASK COMPLETION**: If a task is already completed (e.g., invoice already paid), report this immediately after verification. Do not attempt to perform redundant actions.
