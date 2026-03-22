# Create dimension + post voucher

**Score:** 10/10
**Rounds:** 5
**Last run:** 5 calls, 0 errors
**Reason:** All tasks were completed as requested: custom accounting dimension 'Kostsenter' was verified/used, values 'IT' and 'Innkjøp' were confirmed, and the voucher was correctly posted to account 7000 with the 'IT' dimension value linked via freeAccountingDimension3, including all required amount fields.

## Representative prompt

Erstellen Sie eine benutzerdefinierte Buchhaltungsdimension "Kostsenter" mit den Werten "IT" und "Innkjøp". Buchen Sie dann einen Beleg auf Konto 7000 über 19450 NOK, verknüpft mit dem Dimensionswert "IT".

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **CRITICAL: Voucher Postings**: Every posting MUST include all four amount fields (amount, amountCurrency, amountGross, amountGrossCurrency) set to the exact same value. Postings must balance (debits = credits). Use `sendToLedger=true` as a query parameter, NOT in the body.
2.  **CRITICAL: Dimension Management**: Before creating a custom accounting dimension, ALWAYS check existing ones via `GET /ledger/accountingDimensionName`. If the requested dimension already exists, use it. If values are missing, use `POST /ledger/accountingDimensionValue` to add them. If all 3 slots are full, you MUST rename an existing one using `PUT /ledger/accountingDimensionName/{index}` to the requested name.
3.  **CRITICAL: Dimension Linking**: When linking a dimension value to a posting, use the correct `freeAccountingDimension1/2/3` field corresponding to the `dimensionIndex` (1, 2, or 3).
4.  **Efficiency**: Plan all steps before executing. Use `GET` to verify IDs once, then use them directly in subsequent `POST`/`PUT` calls. Avoid redundant `GET` calls after a successful `POST`.
5.  **Error Recovery**: If a request fails with 422, check the validation messages and the endpoint reference. Do not retry the same failing request more than once; adjust the body or parameters based on the error.
6.  **Voucher Types**: Do not specify `voucherType` unless absolutely necessary; let the system assign it automatically to avoid "systemgenererte" errors.
7.  **Anti-Loop**: If an API call returns the same result twice, stop and re-evaluate the approach. Do not repeat the same failing call.
