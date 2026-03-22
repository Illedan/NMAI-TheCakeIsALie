# Import products from file

**Score:** 10/10
**Rounds:** 13
**Last run:** 14 calls, 4 errors
**Reason:** All products from the CSV were successfully imported into Tripletex with the correct names, numbers, prices, and VAT settings. Verification via API calls confirmed that the entities exist and match the input data exactly.

## Representative prompt

Importer produktene fra den vedlagte CSV-filen. Opprett alle i Tripletex.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Use Specific Search Filters:** Never use `query` for exact matches when a specific filter parameter (e.g., `number=`, `organizationNumber=`) exists. Using `query` often returns broad, irrelevant results and makes it harder to identify if an entity already exists.
2. **Avoid Unnecessary GET Calls:** Do not perform `GET` calls to verify data immediately after a successful `POST` unless strictly required for the next step. Trust the `POST` response, which contains the created entity's ID and details.
3. **Handle 422 Errors Proactively:** If a `POST` fails with a "number already in use" error, do not attempt to create it again. Immediately perform a `GET` search to find the existing entity and use `PUT` if updates are required.
4. **Respect API Limits:** List responses are capped (usually at 100). If an entity is not found in the first page, use `from` and `count` to iterate, but avoid excessive pagination. Use specific filters to narrow the search instead.
5. **VAT Type Accuracy:** Always fetch valid VAT types using `GET /ledger/vatType` once at the start of a task. Never guess IDs. For revenue accounts (3000-3999), always use the locked `vatType` associated with that specific account.
6. **Minimize API Calls:** Plan the entire workflow before executing. Combine operations where possible (e.g., using batch endpoints) and avoid redundant lookups.
7. **Avoid Beta Endpoints:** Do not use endpoints marked [BETA] in the API documentation, as they are unstable and often return 403 errors.
8. **File Handling:** Parse CSV/PDF data directly from the prompt and map them to the required API fields accurately.
9. **Error Recovery:** If a request fails, analyze the `validationMessages` in the response. Do not retry the exact same request; adjust the body or parameters based on the error message.
