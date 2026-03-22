# Process payroll

**Score:** 10/10
**Rounds:** 8
**Last run:** 4 calls, 0 errors
**Reason:** The salary transaction was successfully created for the correct employee with the specified base salary (40,850 NOK) and bonus (14,800 NOK). The system automatically generated the tax deduction as expected, and the transaction was verified via API to confirm all details were correctly registered.

## Representative prompt

Kjør lønn for Lars Berg (lars.berg@example.org) for denne måneden. Grunnlønn er 40850 kr. Legg til en engangsbonus på 14800 kr i tillegg til grunnlønnen. Dersom lønns-API-et ikke fungerer, kan du bruke manuelle bilag på lønnskontoer (5000-serien) for å registrere lønnskostnaden.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **PRIORITIZE SALARY/PAYROLL ENDPOINTS OVER MANUAL VOUCHERS**: When tasked with payroll, always use `POST /salary/transaction` with `generateTaxDeduction=true`. Manual voucher postings (5000-series) for salary are prone to validation errors regarding employee IDs and tax calculations.
2.  **MASTER RULE: USE EXACT ACCOUNT NUMBERS FROM THE PROMPT**: When the prompt specifies an account number (e.g., "account 6030"), use EXACTLY that account number. If the account doesn't exist, POST /ledger/account to create it first. NEVER substitute with a "similar" account.
3.  **VERIFY ENTITY EXISTENCE BEFORE ACTION**: Always search for the specific entity (employee, customer, supplier) using the provided unique identifier (email, organization number) before attempting any operations. If the search returns 0 results, do not proceed with dependent tasks.
4.  **MINIMIZE API CALLS**: Plan all steps before making any API calls. Use IDs from POST responses directly — NEVER GET after POST just to confirm. Fewer calls = higher efficiency bonus.
5.  **MANUAL VOUCHER POSTING RULES**: When posting manual vouchers:
    *   Every posting MUST have a "row" field (sequential integers: 1, 2, 3...).
    *   You MUST include ALL FOUR amount fields: `amount`, `amountCurrency`, `amountGross`, `amountGrossCurrency`. Set them all to the same value.
    *   Postings MUST be balanced (total debits = total credits).
    *   Do NOT include `description` or `customer`/`supplier` on individual postings unless absolutely necessary, as this often triggers "systemgenererte" errors.
6.  **AVOID BETA ENDPOINTS**: Do NOT use endpoints marked [BETA] in the API docs — they return 403. If you get 403, try an alternative non-BETA endpoint.
7.  **ERROR RECOVERY**: If an API call returns 422, check the `validationMessages` field in the response. It usually contains the exact reason for the failure. Fix the specific field identified, do not guess.
8.  **STRICT ADHERENCE TO TASK**: If a task specifies a name or email, search for that exact match. If the search fails, report it immediately rather than attempting to guess IDs or proceed with incomplete data.
9.  **EFFICIENCY RULES**: Always use today's date unless the task specifies a different date. When `sendToCustomer=true` on POST /invoice, the invoice is automatically sent — do NOT also call `PUT /:send`.
10. **VERIFICATION STRATEGY**: After performing a complex operation (like salary), use a single targeted GET call to verify the result. Do not perform exhaustive verification of every field if the primary transaction ID confirms the operation was successful.
