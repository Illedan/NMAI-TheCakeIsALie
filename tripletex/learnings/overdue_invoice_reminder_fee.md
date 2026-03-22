# Overdue invoice + reminder fee

**Score:** 10/10
**Rounds:** 10
**Last run:** 10 calls, 0 errors
**Reason:** The overdue invoice was correctly identified, a partial payment of 5,000 NOK was registered, and a reminder fee of 70 NOK was invoiced and sent to the customer. Ledger postings were verified to show the correct debit to account 1500 and credit to account 3400 as specified.

## Representative prompt

One of your customers has an overdue invoice. Find the overdue invoice and post a reminder fee of 70 NOK. Debit accounts receivable (1500), credit reminder fees (3400). Also create an invoice for the reminder fee to the customer and send it. Additionally, register a partial payment of 5000 NOK on th...

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

*   **Mandatory Search Filters**: 
    *   `GET /invoice` **always** requires `invoiceDateFrom` and `invoiceDateTo`.
    *   `GET /ledger/posting` and `GET /ledger/voucher` **always** require `dateFrom` and `dateTo`.
*   **Reducing API Calls via Field Expansion**: To minimize calls, use the `fields` parameter to expand linked entities. 
    *   Example: When fetching a product, use `GET /product?name=...&fields=id,name,account(id,number,name),vatType(id)` to verify the ledger account and VAT settings in a single request instead of making follow-up `GET /ledger/account/{id}` calls.
    *   Example: When fetching an invoice, use `fields=id,amount,amountOutstanding,postings(account(number),amount,description)` to verify both the balance and the ledger entries at once.
*   **Invoice Field Names**: The `InvoiceDTO` does not contain `totalAmountIncludingVatCurrency`. Use `amount` (total in company currency) or `amountCurrency` (total in invoice currency).
*   **Sending Invoices**: To send an invoice during creation, use the query parameter `sendToCustomer=true` on `POST /invoice`. Ensure the customer has a valid `email` and `invoiceEmail` set first. To send an existing invoice, use `PUT /invoice/{id}/:send?sendType=EMAIL`.
*   **Reminder Fee Workflow**:
    1. Identify the customer and overdue invoice (`invoiceDueDate` < today and `amountOutstanding` > 0).
    2. Find or create a "Reminder Fee" product. Ensure it uses a VAT-exempt `vatType` (ID 0) and the correct revenue account (e.g., 3400).
    3. Create an `order` for the customer with this product.
    4. Finalize with `POST /invoice` using `sendToCustomer=true`.
*   **Partial Payments**: Use `PUT /invoice/{id}/:payment`. Find the `paymentTypeId` (e.g., "Betalt til bank") via `GET /invoice/paymentType`. The `paidAmount` is the actual amount paid (including VAT).
*   **Reliable Voucher Verification**: Avoid using `GET /ledger/posting` with `voucherId` filters. Instead, expand the `voucher` or `postings` field within an invoice GET: `GET /invoice/{id}?fields=voucher(id,postings(account(number),amount,description))`.
*   **Voucher Posting Logic**: In `PostingDTO`, a positive `amount` is a Debit, and a negative `amount` is a Credit.
*   **Account Activation**: Check `isInactive` in `GET /ledger/account`. If `true`, use `PUT /ledger/account/{id}` with `{"isInactive": false}` before using the account.
*   **POST /invoice Body Requirements**: A request body is mandatory. Include `orders`, `invoiceDate`, and `invoiceDueDate` inside the JSON body.
