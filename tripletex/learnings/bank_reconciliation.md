# Bank reconciliation

**Score:** 10/10
**Rounds:** 11
**Last run:** 4 calls, 0 errors
**Reason:** All bank statement transactions from the provided CSV were successfully reconciled against the ledger. Each entry was verified against the corresponding voucher in Tripletex, confirming that all inpayments, outpayments, tax deductions, and bank fees were correctly recorded with the accurate dates and amounts.

## Representative prompt

Avstem bankutskrifta (vedlagt CSV) mot opne fakturaer i Tripletex. Match innbetalingar til kundefakturaer og utbetalingar til leverandorfakturaer. Handter delbetalingar korrekt.

## Learnings

```json
{
  "learnings": [
    "BANK RECONCILIATION: Always perform a comprehensive GET /ledger/voucher search for the entire date range of the bank statement BEFORE creating any new vouchers. This prevents duplicate entries for transactions that may have already been recorded.",
    "VOUCHER BALANCING: When creating vouchers, ensure the total debits equal total credits. Every posting must include all four amount fields (amount, amountCurrency, amountGross, amountGrossCurrency) set to the exact same value to avoid system errors.",
    "API EFFICIENCY: Plan the entire workflow before executing. Use list endpoints for bulk operations, but avoid [BETA] endpoints. Trust the response of a POST call and avoid unnecessary GET calls to verify what you just created.",
    "DATE ACCURACY: Always use the specific date from the source document (e.g., bank statement date, invoice date) for all date fields in vouchers or payments, rather than defaulting to today's date.",
    "ERROR HANDLING: If a request returns a 422 or 400 error, carefully read the validationMessages. Fix the specific field mentioned and do not retry the same failing request more than once.",
    "SEARCH STRATEGY: If a specific search (e.g., by number or date range) returns no results, immediately broaden the search using wider parameters or querying by name/organization number. Do not repeat the same failing search."
  ]
}
```
