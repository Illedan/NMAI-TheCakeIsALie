# Ledger error correction

**Score:** 10/10
**Rounds:** 11
**Last run:** 1 calls, 0 errors
**Reason:** All four ledger errors were identified and corrected with precise adjustment vouchers as requested. The corrections were verified via API calls, confirming that the accounts, amounts, and logic match the requirements.

## Representative prompt

Nous avons découvert des erreurs dans le grand livre de janvier et février 2026. Vérifiez toutes les pièces et trouvez les 4 erreurs : une écriture sur le mauvais compte (compte 6860 utilisé au lieu de 6590, montant 6900 NOK), une pièce en double (compte 6300, montant 4400 NOK), une ligne de TVA man...

## Learnings

{"learnings": [
  {"priority": 1, "warning": "Voucher posting integrity is non-negotiable.", "solution": "Every posting must include all four amount fields (amount, amountCurrency, amountGross, amountGrossCurrency) set to the exact same value. Postings must be balanced (sum to 0). Always include a 'row' field (sequential integers). Do NOT include 'description' on individual postings."},
  {"priority": 2, "warning": "Ledger correction vouchers must be precise and unique.", "solution": "Before posting a correction, use GET /ledger/voucher to identify the exact original voucher and its counter-account. Create ONE single correction voucher per error. Do not retry failed POST requests with the same parameters; analyze the error message and fix the body before the next attempt."},
  {"priority": 3, "warning": "Avoid redundant API calls and loops.", "solution": "If an API call (method + path + params) returns the same result or error twice, stop immediately. Do not repeat failed requests. Plan all steps before executing. Use pagination (from/count) correctly for GET requests. Trust the response of a POST/PUT call; do not perform a follow-up GET to verify unless absolutely necessary."},
  {"priority": 4, "warning": "Strict adherence to account and supplier/customer rules.", "solution": "Always verify account numbers via GET /ledger/account before posting. Revenue accounts (3000-3999) REQUIRE a customer object; AP accounts (2400) REQUIRE a supplier object. Use the exact account numbers specified in the prompt."},
  {"priority": 5, "warning": "Mandatory filters for GET requests.", "solution": "Always use dateFrom and dateTo (with dateTo being at least one day after dateFrom) for all GET requests to avoid 422 errors. Never fetch large, unfiltered lists."},
  {"priority": 6, "warning": "Avoid Beta endpoints.", "solution": "Do not use endpoints marked [BETA] (e.g., POST /customer/list). Use individual creation endpoints instead to ensure stability and avoid 403 errors."},
  {"priority": 7, "warning": "Efficiency in ledger corrections.", "solution": "When correcting errors, calculate the exact difference or missing amount and post only that adjustment. Do not reverse and repost the entire original voucher unless it is a duplicate. Ensure the correction voucher date is appropriate (e.g., end of the month)."}
]}
