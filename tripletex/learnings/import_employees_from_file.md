# Import employees from file

**Score:** 10/10
**Rounds:** 5
**Last run:** 4 calls, 3 errors
**Reason:** The employees were successfully imported and verified. Although the initial POST attempts returned validation errors indicating the employees already existed in the system, the subsequent GET verification confirmed that both employees were present with the correct details as specified in the CSV.

## Representative prompt

Import employees from the attached CSV. Create them all in Tripletex.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Pre-emptive Verification (GET before POST)**: Always perform a GET request (e.g., by email, number, or name) before attempting to create an entity. If the entity already exists, use the existing ID instead of attempting a duplicate creation, which triggers 422 errors.
2. **Handle 422 errors by reading validationMessages**: If a POST fails, the response body contains specific `validationMessages`. Read these to identify exactly which field caused the failure and fix only that field in the subsequent retry.
3. **Minimize API calls**: Combine operations where possible and avoid redundant GET calls if the information is already available in the response of a previous operation.
4. **Use specific filters for GET requests**: Never fetch entire lists. Use `?name=`, `?email=`, or `?query=` parameters to retrieve only the relevant entity, minimizing API overhead and avoiding truncation issues.
5. **Avoid Beta Endpoints**: Do not use endpoints marked [BETA] in the API docs (e.g., `POST /customer/list`), as they often return 403. Use individual creation endpoints instead.
6. **Complete the full workflow for entities**: Creating an entity (e.g., `/employee`) is often only the first step. Always check if related endpoints (e.g., `/employee/employment` for start date, or setting `userType`) are required to fulfill the task requirements.
7. **Verify with GET after POST**: Always perform a GET request on the created entity to confirm all fields (including those not explicitly set in the POST) match the requirements.
8. **Batching**: Use batch `/list` endpoints only when creating multiple entities and when the endpoint is confirmed to be stable. If a batch request fails, fall back to individual requests immediately.
