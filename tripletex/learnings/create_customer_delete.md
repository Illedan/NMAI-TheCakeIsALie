# Create customer + delete

**Score:** 10/10
**Rounds:** 5
**Last run:** 3 calls, 1 errors
**Reason:** The customer was successfully created, deleted, and the deletion was verified with a 404 response, confirming the task was completed exactly as requested.

## Representative prompt

Create a customer 'Delete82381905 Ltd' (del82381905@example.com). Then delete that customer.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Verification is Mandatory**: Always perform a GET request after a DELETE or update operation to confirm the state change (e.g., verifying that a customer is no longer returned in search results).
2. **Use Specific Filters**: When searching for entities (GET), always use query parameters (like `?name=`) to filter results. Do not fetch large lists and scan them manually, as this is inefficient and prone to truncation.
3. **Minimize API Calls**: Combine operations where possible (e.g., setting `isCustomer:true` and `isSupplier:true` in a single POST /customer call instead of creating them separately).
4. **Handle 422 Errors**: If a request fails with a 422 status, read the `validationMessages` in the response body to identify and fix only the specific fields causing the error.
5. **Follow Required Fields**: Strictly adhere to the required fields specified in the system instructions for each endpoint (e.g., `vatType` for products, `orderLines` embedded in `order` creation).
6. **Avoid Redundant Verification**: Do not perform unnecessary GET calls if the previous operation's response (e.g., 204 No Content for a successful DELETE) is sufficient to confirm the action, unless the task explicitly requires a post-action verification.
7. **Delete Verification**: When a task requires deleting an entity, the final verification step must confirm the entity no longer exists (expecting a 404 status).
8. **Efficiency**: Plan all steps before making any API calls. Trust the POST response IDs; do not perform a GET immediately after a POST unless necessary for verification.
