# Record travel/expense

**Score:** 10/10
**Rounds:** 5
**Last run:** 9 calls, 0 errors
**Reason:** The travel expense report was successfully created for Elias Hoffmann with all required details: title, travel dates, purpose, destination, and departure city. Both expense items (flight 6300 NOK, taxi 250 NOK) were added with correct categories and payment types. The per diem compensation was correctly calculated for 5 days at 800 NOK/day (total 4000 NOK) using the valid 2026 domestic rate category for overnight stays. All entities were verified via GET calls.

## Representative prompt

Erfassen Sie eine Reisekostenabrechnung für Elias Hoffmann (elias.hoffmann@example.org) für "Kundenbesuch Trondheim". Die Reise dauerte 5 Tage mit Tagegeld (Tagessatz 800 NOK). Auslagen: Flugticket 6300 NOK und Taxi 250 NOK.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Travel Expense Workflow**: Always include `travelDetails` (departureDate, returnDate, destination, purpose, departureFrom) in the initial `POST /travelExpense` call. Without it, the system creates an "Employee Expense" (ansattutlegg) instead of a "Travel Report" (reiseregning), which prevents adding per diem compensation.
2. **Per Diem Rate Categories**: Rate categories are date-sensitive. Always use `GET /travelExpense/rateCategory` and filter for the current year (e.g., 2026) to find a valid `id`. Never assume an ID from previous years or generic searches.
3. **Voucher Postings**: Every posting in `POST /ledger/voucher` MUST include all four amount fields (`amount`, `amountCurrency`, `amountGross`, `amountGrossCurrency`) set to the exact same value. Postings must be balanced (sum to 0).
4. **API Efficiency**: Plan the entire workflow before executing. Use `GET` calls sparingly; trust the `POST` response for IDs. Avoid redundant `GET` calls after a successful `POST`.
5. **Error Handling**: If a `POST` returns 422, check the `validationMessages` immediately. Do not retry the same request without fixing the body based on the error.
6. **Data Verification**: Always perform a final `GET` to verify that all created entities (costs, per diem, travel details) match the task requirements exactly.
7. **Cost Categories**: Use `GET /travelExpense/costCategory?showOnTravelExpenses=true` to find the correct category IDs for travel-related expenses (e.g., "Fly", "Taxi"). Do not guess IDs.
