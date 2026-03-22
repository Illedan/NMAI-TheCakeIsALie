# Create private customer

**Score:** 10/10
**Rounds:** 5
**Last run:** 1 calls, 0 errors
**Reason:** The customer was created with all specified fields (name, email, invoiceEmail, isCustomer, isPrivateIndividual) correctly set, and verified via a subsequent GET call.

## Representative prompt

Opprett en privatkunde med navn 'Privat16341875' og e-post privat16341875@example.com

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Verify with specific filters:** When searching for an entity (customer, product, etc.) to verify creation, always use query parameters (e.g., `?email=...` or `?name=...`) instead of fetching a full list. This prevents unnecessary data transfer and avoids hitting truncation limits.
2. **Check for existing entities first:** Before creating a new entity, perform a `GET` request with a filter to ensure it doesn't already exist. This prevents duplicate entries.
3. **Minimize API calls:** Combine operations where possible (e.g., setting both `email` and `invoiceEmail` in a single `POST /customer` call).
4. **Handle 422 errors gracefully:** If a `POST` request returns a 422 error, carefully read the `validationMessages` in the response body to identify the specific field causing the issue before retrying.
5. **Verify all requirements:** After performing an action, perform a `GET` request to confirm that all requested fields (e.g., name, email, flags) were correctly set in the system.
6. **Avoid unnecessary verification calls:** While verification is important, do not perform redundant `GET` calls if the `POST` response already provides the necessary confirmation of the created object's state. Only verify if there is ambiguity or if the task explicitly requires a multi-step verification process.
7. **Use the correct fields for customer creation:** When creating a customer, ensure `isCustomer: true` is set. If the customer is a private individual, set `isPrivateIndividual: true`.
