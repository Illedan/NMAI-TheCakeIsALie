# Create internal project

**Score:** 10/10
**Rounds:** 25
**Last run:** 3 calls, 1 errors
**Reason:** The project was successfully created with the specified name, number, and internal status, and all details were verified via API call.

## Representative prompt

Opprett et internt prosjekt med navn 'Intern27341875' og prosjektnummer P27341875

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **Verify Before Action:** Always `GET` an entity by its unique identifier (number, email, or organization number) before attempting to `POST` it. If it exists, verify its properties against the task requirements. Only `POST` if it does not exist.
2.  **Minimize API Calls:** Do not perform redundant `GET` calls after a successful `POST`. Trust the API response. Use `fields` parameters in `GET` requests to fetch only the necessary data, reducing payload size and processing time.
3.  **Unique Constraint Conflicts:** Project, customer, and product numbers are globally unique. If a requested number is already in use, the API returns a 422 error. If the entity exists with the correct number and name, use it. If the number is taken by a different entity, you must use a different number or the system-generated one.
4.  **Internal Projects:** For tasks specifying an "internt prosjekt" (internal project), you MUST set `isInternal: true` in the `POST` body. Verify this field during the check/verification phase.
5.  **Validation Errors (422):** Inspect the `validationMessages` in 422 responses. Do not retry the same request without fixing the specific field mentioned (e.g., a duplicate number or missing required field).
6.  **Avoid Beta Endpoints:** Do not use endpoints marked [BETA] (like `POST /customer/list`) as they often return 403 Forbidden. Use individual `POST` calls instead.
7.  **Entity Linking:** When creating projects, ensure you have a valid `projectManager` ID from a `GET /employee` call. Use the first active employee if none is specified.
8.  **Handling Duplicate Names:** Searching by name (e.g., `GET /project?name=...`) may return multiple entities if the name is not unique. Always inspect the results to find the one matching the specific `number` requested in the task.
