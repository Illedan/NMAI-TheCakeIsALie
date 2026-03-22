# Invoice project milestone

**Score:** 10/10
**Rounds:** 5
**Last run:** 14 calls, 0 errors
**Reason:** The project was identified, the fixed price was verified, and the milestone invoice for 25% (50,537.50 NOK) was successfully created and linked to the correct order and customer.

## Representative prompt

Set a fixed price of 202150 NOK on the project "Cloud Migration" for Clearwater Ltd (org no. 872682023). The project manager is Oliver Brown (oliver.brown@example.org). Invoice the customer for 25% of the fixed price as a milestone payment.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **FIELD VALIDATION**: Always check the API documentation for valid fields before using `fields=` in a `GET` request. Using an invalid field (e.g., `name` on an `EmployeeDTO` when only `id` is expected) will result in a 400 error.
2. **VAT TYPE SELECTION**: Always use `GET /ledger/vatType` to find the correct `id` for the required VAT rate. Do not guess IDs or assume standard ones. If a `POST /product` or `POST /order` fails with a 422 "Ugyldig mva-kode", verify the `vatType` ID against the list of available outgoing VAT types.
3. **MINIMIZE API CALLS**: Plan the workflow to use the minimum number of calls. Use `GET` with specific `fields` to verify data instead of `fields=*`. Trust the `POST` response for IDs and data instead of performing redundant `GET` calls immediately after creation.
4. **INVOICE DATE/DUE DATE**: Always calculate the due date correctly (e.g., 14 days after invoice date) and ensure both `invoiceDate` and `invoiceDueDate` are provided in the `POST /invoice` call.
5. **ERROR HANDLING**: If an API call returns a 403 or 422, analyze the error message immediately. Do not retry the same request without modification. If a `POST` fails, check the `validationMessages` field in the response to identify the specific field causing the error.
6. **ANTI-LOOP RULE**: If you have made the same API call (same method + path + params) more than twice and gotten the same result, STOP immediately. Do not repeat it. Fix the request body/params or conclude the task cannot be completed.
7. **ENTITY VERIFICATION**: When verifying, use specific `GET` calls with `fields` to confirm only the necessary attributes (e.g., `fixedprice`, `amount`, `invoiceNumber`) to keep the response clean and efficient.
8. **PROJECT MANAGER ASSIGNMENT**: If the specified project manager does not exist in the system, do NOT fail the task. Proceed with the existing project manager or leave it as is, and note this in the final report. Do not waste API calls trying to create or search for non-existent employees.
