# Monthly accounting closing

**Score:** 10/10
**Rounds:** 6
**Last run:** 8 calls, 0 errors
**Reason:** All tasks were completed as requested: periodization of prepaid expenses, monthly depreciation calculation (278500/4/12 = 5802.08), and salary provision were all correctly calculated and posted to the specified accounts (6300/1700, 6020/1209, 5000/2930). The voucher is balanced and verified via API.

## Representative prompt

Gjer månavslutninga for mars 2026. Periodiser forskotsbetalt kostnad (12000 kr per månad frå konto 1700 til kostnadskonto). Bokfør månadleg avskriving for eit driftsmiddel med innkjøpskost 278500 kr og levetid 4 år (lineær avskriving til konto 6020). Kontroller at saldobalansen går i null. Bokfør og...

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **Voucher Integrity and Balancing:** Every voucher must be perfectly balanced (total debits = total credits). Every posting must include all four amount fields (`amount`, `amountCurrency`, `amountGross`, `amountGrossCurrency`) set to the exact same value. Always include a `row` field (sequential integers) for every posting.
2.  **Verify Account IDs and Existence:** Always verify account IDs and existence using `GET /ledger/account` before using them in a `POST` request. Never assume an account exists based on standard accounting practices or previous knowledge.
3.  **Date Filtering for Vouchers:** When searching for vouchers, ensure the `dateTo` parameter is at least one day after the target date (e.g., `dateFrom=2026-03-31&dateTo=2026-04-01`) to avoid 422 errors caused by an empty or invalid date range.
4.  **Minimize API Calls:** Plan the entire workflow before starting. Combine information gathering (e.g., fetching multiple accounts in one call) to reduce the total number of requests.
5.  **Error Handling:** When a 422 error occurs, analyze the `validationMessages` in the response body. Do not retry the same request without fixing the payload based on the specific error message.
6.  **Clean Up After Errors:** If an attempt fails and creates partial or incorrect data, perform the necessary cleanup (reversals or deletions) before attempting the task again to ensure the ledger remains accurate.
7.  **Verify Endpoint Existence:** Do not guess endpoint paths. If a `POST` or `GET` returns a 404, stop immediately. Use `GET /` or search the API documentation to confirm the correct path. Do not repeat failed calls.
8.  **Avoid Duplicate Vouchers:** Before creating a new voucher, always search for existing ones for the same period and purpose. If a voucher already exists, do not create a duplicate. If an existing voucher is incorrect, reverse it (`PUT /ledger/voucher/{id}/:reverse`) before creating a corrected one.
