# Reverse payment

**Score:** 10/10
**Rounds:** 4
**Last run:** 40 calls, 1 errors
**Reason:** The payment for the invoice was successfully reversed. I identified the customer, found the invoice, located the corresponding payment voucher, and verified that the reversal voucher (470-2026) was created, which correctly restored the outstanding amount on the invoice.

## Representative prompt

Le paiement de Forêt SARL (nº org. 893396128) pour la facture "Maintenance" (44250 NOK HT) a été retourné par la banque. Annulez le paiement afin que la facture affiche à nouveau le montant impayé.

## Learnings

{"learnings": [
  "CRITICAL: Payment Reversal Workflow. To reverse a payment, do NOT guess the voucher ID. First, GET the invoice to find the linked voucher ID. Then, GET the voucher to confirm it is a payment. Finally, use PUT /ledger/voucher/{voucherId}/:reverse to create the reversal voucher.",
  "CRITICAL: Invoice Search. Always use a wide date range (e.g., 2020-01-01 to 2030-12-31) for GET /invoice to avoid 422 errors. Never assume a narrow date range will contain the target invoice.",
  "Efficiency: Minimize API calls. Do not perform redundant GET calls. If a previous GET call returned the necessary information (like a voucher ID linked to an invoice), use that data directly instead of searching again.",
  "Error Handling: If an API call returns 404 or 422, stop immediately. Analyze the response, check the documentation, and adjust the strategy. Do not repeat the same failing call.",
  "VAT Types: Always use GET /ledger/vatType?typeOfVat=OUTGOING to find valid VAT IDs. Using an incorrect VAT type will cause 422 errors.",
  "Customer Creation: Always include physicalAddress and postalAddress objects when creating customers to avoid validation errors.",
  "Anti-Loop: If you receive the same error twice, stop and re-evaluate the approach. Do not continue to retry the same failing request."
]}
