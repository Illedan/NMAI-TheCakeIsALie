# Issue credit note

**Score:** 10/10
**Rounds:** 4
**Last run:** 2 calls, 0 errors
**Reason:** The credit note was successfully created for the correct customer and invoice, fully cancelling the original amount of 36900 NOK. Verification confirmed the credit note (invoice 389) correctly references the original invoice (invoice 388) and has the correct negative amount.

## Representative prompt

Der Kunde Waldstein GmbH (Org.-Nr. 898006263) hat die Rechnung für "Beratungsstunden" (36900 NOK ohne MwSt.) reklamiert. Erstellen Sie eine vollständige Gutschrift, die die gesamte Rechnung storniert.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **MANDATORY DATE PARAMETERS:** Always include `invoiceDateFrom` and `invoiceDateTo` when calling `GET /invoice` or `GET /ledger/voucher`. Omitting these or providing null values will result in a 422 error.
2. **VERIFY BEFORE ACTING:** Always check the current state of an entity (e.g., invoice status, existing credit notes) before attempting to create new ones. This prevents redundant operations and 422 validation errors.
3. **MINIMIZE API CALLS:** Use specific `fields` in `GET` requests to reduce payload size and avoid retrieving unnecessary computed fields that can cause issues in subsequent `PUT` requests.
4. **ERROR HANDLING:** If an API call returns a 422 error, read the `validationMessages` carefully. Do not retry the same request; adjust the parameters or body based on the specific error message provided.
5. **DATE FORMATS:** Always use `YYYY-MM-DD` format for all date parameters.
6. **BATCH OPERATIONS:** Avoid using beta endpoints like `POST /customer/list` if they are known to return 403 errors; prefer individual `POST` calls for reliability.
7. **CREDIT NOTE VERIFICATION:** When a task requires a credit note, always verify if one already exists for the target invoice before attempting to create a new one to avoid duplicate credit notes.
8. **EFFICIENT SEARCHING:** When searching for entities by specific attributes (like `organizationNumber` or `customerId`), use query parameters in the `GET` request rather than fetching large lists and filtering manually.
