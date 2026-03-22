# Create customer+supplier

**Score:** 10/10
**Rounds:** 6
**Last run:** 1 calls, 0 errors
**Reason:** The entity was created with the correct name, email (both email and invoiceEmail), and both isCustomer and isSupplier flags set to true. Verification confirmed all details match the requirements.

## Representative prompt

Opprett 'DualRole15395922 AS' med e-post dual15395922@example.com som er både kunde og leverandør

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Unified Entity Creation**: When a task requires an entity to be both a customer and a supplier, use the `POST /customer` endpoint with both `isCustomer:true` and `isSupplier:true` in the same request. Do not create separate entities.
2. **Mandatory Field Validation**: Always check the API documentation for required fields before making a `POST` request. For `POST /customer`, `name` and `isCustomer` are mandatory. Sending an empty body or missing required fields will result in a 422 error.
3. **Efficient Searching**: Always use query parameters (e.g., `?name=...` or `?email=...`) when performing `GET` requests to find specific entities. Avoid fetching large lists and filtering them manually.
4. **Verification**: Always verify the creation of an entity by performing a `GET` request on the specific resource using its unique identifier to confirm all fields were set correctly as per the requirements.
5. **Minimize API Calls**: Plan the sequence of operations to achieve the goal in the minimum number of steps. Avoid redundant `GET` calls after a successful `POST` if the response already contains the necessary information.
6. **Field Accuracy**: Ensure all mandatory fields specified in the instructions (e.g., `invoiceEmail`, `vatType`) are included in the initial `POST` request to avoid subsequent `PUT` calls.
7. **Avoid Duplicate Creation**: Before creating an entity, perform a `GET` search to ensure it does not already exist. If it exists, use the existing ID instead of creating a duplicate.
8. **Error Handling**: If a request fails with a 422 error, carefully examine the `validationMessages` in the response to identify the missing or incorrect fields before retrying. Do not retry the exact same request without modification.
