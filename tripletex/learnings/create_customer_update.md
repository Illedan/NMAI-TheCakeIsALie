# Create customer + update

**Score:** 10/10
**Rounds:** 5
**Last run:** 2 calls, 0 errors
**Reason:** The customer was successfully created with the initial email, then updated to the new email, and both states were verified via API calls to confirm the final values match the requirements.

## Representative prompt

Create customer 'Update86381905 Ltd' (old86381905@example.com). Then update the email to new86381905@example.com.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Minimize API Calls:** Combine operations where possible (e.g., setting both `email` and `invoiceEmail` in a single `POST` or `PUT` call). Avoid redundant `GET` calls if the previous response already provides the necessary information.
2. **Verify State Efficiently:** After a `POST` or `PUT`, use the response body to confirm the state. Only perform a `GET` if the `POST`/`PUT` response is incomplete or if the task explicitly requires a multi-step verification process.
3. **Handle Versioning:** When performing a `PUT` request, ensure the `version` field from the most recent `GET` or `POST` response is included in the body to avoid concurrency conflicts.
4. **Use Specific Filters:** Always use `?name=` or `?email=` when performing `GET` requests on lists to avoid fetching large datasets and to ensure the target entity is found immediately.
5. **Avoid Beta Endpoints:** Do not use endpoints marked [BETA] in the API docs (e.g., `POST /customer/list`). Use individual `POST` calls instead.
6. **Maintain Data Integrity:** When updating entities, ensure all mandatory fields (like `dateOfBirth` for employees) are included in the `PUT` body to prevent accidental data loss or validation errors.
7. **Check Response Data:** Always inspect the `value` object returned by the API to confirm the current state of the entity before proceeding to the next step.
