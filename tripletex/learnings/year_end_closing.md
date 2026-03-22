# Year-end closing

**Score:** 8/10
**Rounds:** 6
**Last run:** 15 calls, 1 errors
**Reason:** The annual closing was performed correctly, but the depreciation amounts calculated in the final verification step (48614, 36408, 27019) differed slightly from the amounts actually posted in the vouchers (48900, 36408, 27019) due to a manual calculation error during the posting phase. All other requirements, including separate vouchers, account usage, and tax provision logic, were fully met.

## Representative prompt

Effectuez la clôture annuelle simplifiée pour 2025 : 1) Calculez et comptabilisez l'amortissement annuel de trois immobilisations : Inventar (340300 NOK, 7 ans linéaire, compte 1240), Programvare (218450 NOK, 6 ans, compte 1250), Kjøretøy (216150 NOK, 8 ans, compte 1230). Utilisez le compte 6010 pou...

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **CALCULATE BEFORE POSTING:** NEVER perform mental math for financial postings. Use the `calculate` tool for every single amount (depreciation, tax, accruals) to ensure the values posted match the requirements exactly. Verify the math twice before calling `POST /ledger/voucher`.
2.  **VOUCHER INTEGRITY & DUPLICATE PREVENTION:** Before creating any voucher, ALWAYS perform a `GET /ledger/voucher` with date filters to check for existing entries. If a voucher with the same description, accounts, and amounts already exists, do NOT create a duplicate. If an incorrect voucher exists, use `PUT /ledger/voucher/{id}/:reverse` to undo it before posting the correct one.
3.  **ACCOUNT ACCURACY IS PARAMOUNT:** Use the EXACT account numbers specified in the prompt (e.g., 6010, 1209, 1700, 8700, 2920). Never substitute with "similar" accounts. If the prompt specifies an account, use it. If it doesn't exist, create it.
4.  **VOUCHER BALANCING & AMOUNT FIELDS:** Every voucher posting MUST include all four amount fields (amount, amountCurrency, amountGross, amountGrossCurrency) set to the EXACT same value. Postings must sum to 0.
5.  **DATE HANDLING:** For year-end closing, ensure all voucher dates are the last day of the fiscal year (e.g., `2025-12-31`). When querying for vouchers or postings, use `dateTo` as the day after the target date (exclusive).
6.  **API EFFICIENCY:** Minimize API calls. Do not perform redundant `GET` calls to verify entities immediately after a successful `POST`. Trust the `POST` response. Use specific filters (e.g., `number=`, `dateFrom=`) instead of fetching large lists.
7.  **VOUCHER TYPES:** Do not include `voucherType` in the body unless specifically required. Let the system assign it automatically. Always use `?sendToLedger=true` as a query parameter for `POST /ledger/voucher`.
8.  **TAX PROVISION LOGIC:** If the prompt asks to "comptabiliser la provision d'impôt", and the result is 0, ensure you have documented the calculation (e.g., "Taxable profit = 0, Tax = 0 * 22% = 0") rather than just skipping the step silently.
