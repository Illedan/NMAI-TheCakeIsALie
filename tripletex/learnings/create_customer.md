# Create customer

**Score:** 10/10
**Rounds:** 5
**Last run:** 1 calls, 0 errors
**Reason:** The customer was created with the exact name and email provided, and both email and invoiceEmail were correctly set. Verification confirmed all details.

## Representative prompt

Opprett en kunde med navn 'Nordiske Konsulenttjenester og Rådgivning 35395922 AS' og e-post kontor35395922@example.com

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Verify all fields immediately:** After creating an entity, perform a GET request on the specific ID to confirm that all fields (especially those that were explicitly requested, like `email` and `invoiceEmail`) were set correctly.
2. **Minimize API calls:** Only perform necessary actions. Do not fetch lists if you already have the ID of the created object.
3. **Handle 422 errors gracefully:** If a POST request fails with a 422 status, read the `validationMessages` in the response body to identify the exact field causing the issue and correct only that field in the subsequent attempt.
4. **Customer/Supplier duality:** If an entity needs to be both a customer and a supplier, set both `isCustomer: true` and `isSupplier: true` in the initial `POST /customer` call. Do not create separate entities.
5. **Always verify with specific filters:** When searching for an entity (like a customer) after creation, use query parameters (e.g., `?name=...` or `?customerNumber=...`) instead of fetching large lists. This prevents truncation issues and reduces API load.
6. **Use the correct endpoint for verification:** If an ID is returned from a POST request, use that ID directly in a GET request to verify the object's state.
7. **Ensure consistency in email fields:** When a task specifies an email, always set both `email` and `invoiceEmail` to the same value in the POST body to ensure consistency across the system.
