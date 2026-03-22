# Create customer (multiple)

**Score:** 10/10
**Rounds:** 5
**Last run:** 3 calls, 0 errors
**Reason:** All three customers were created successfully with the correct names, emails, and invoice emails as requested. Verification via GET calls confirmed the existence and accuracy of all entities.

## Representative prompt

Opprett tre kunder: 'Kunde45A381905 AS' (kunde45a381905@example.com), 'Kunde45B381905 AS' (kunde45b381905@example.com), og 'Kunde45C381905 AS' (kunde45c381905@example.com)

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Use Specific Filters for GET Requests:** Never fetch large lists (e.g., `/customer`) without using query parameters like `?name=` or `?email=`. This prevents truncation issues, performance degradation, and unnecessary API calls.
2. **Verify with Precision:** After creating entities, verify them immediately using the unique identifiers (like `email` or `name`) to confirm the exact state of the created object.
3. **Minimize API Calls:** Plan the sequence of operations to achieve the goal in the fewest steps possible. For example, embed all required fields (like `invoiceEmail`) in the initial `POST` request rather than performing a `POST` followed by a `PUT`.
4. **Handle 422 Errors:** If a request fails with a 422 status, read the `validationMessages` in the response body carefully to identify the specific field causing the error before retrying.
5. **Avoid Redundant Creation:** Before creating an entity, perform a targeted GET request to check if it already exists. This prevents the creation of duplicate entities and keeps the environment clean.
6. **Customer/Supplier Roles:** When creating a customer that also needs to be a supplier, set both `isCustomer:true` and `isSupplier:true` in the initial `POST /customer` call. Do not create separate entities.
7. **Data Integrity:** Always ensure that required fields (e.g., `vatType` for products) are included in the initial creation to avoid subsequent update calls.
8. **Avoid Beta Endpoints:** Do not use endpoints marked [BETA] in the API docs (e.g., `POST /customer/list`), as they often return 403. Use individual `POST` requests instead.
9. **Avoid Unnecessary Verification:** Do not perform redundant `GET` calls to verify entities if the `POST` response already provides the full object details. Trust the `POST` response to minimize total API calls.
