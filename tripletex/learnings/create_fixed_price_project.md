# Create fixed-price project

**Score:** 10/10
**Rounds:** 7
**Last run:** 3 calls, 1 errors
**Reason:** The project was successfully created with the correct name, number, fixed price, and fixed price flag as verified by the API.

## Representative prompt

Create a fixed price project 'Fixed33395922' with number P33395922 and fixed price 150000 NOK

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Check for existence before POSTing:** Always perform a GET request to check if an entity (like a project, customer, or employee) already exists before attempting to create it. This prevents 422 "already in use" errors and unnecessary failed POST attempts.
2. **Use specific filters:** When searching for entities, use query parameters (e.g., `?number=`, `?name=`) instead of fetching lists and filtering manually. This reduces API load and avoids truncation issues.
3. **Verify with specific fields:** When verifying, use the `fields` query parameter to retrieve only the necessary data, making the response cleaner and easier to validate.
4. **Minimize API calls:** Once a task is completed and verified, stop immediately. Do not perform redundant checks or extra calls.
5. **Handle 422 errors gracefully:** If a POST fails with a 422, read the `validationMessages` carefully. Often, the error message provides a link or reason that explains the conflict (e.g., the entity already exists), which should trigger a GET to verify the existing entity instead of retrying the POST.
6. **Use correct field names:** Always refer to the endpoint reference for exact field names (e.g., `fixedprice` with lowercase 'p', not `fixedPrice`). Incorrect field names are a primary cause of 422 errors.
7. **Plan before executing:** Think through the entire workflow and identify all required dependencies (e.g., needing an employee ID for a project manager) before making the first API call.
8. **Trust the API response:** After a successful POST, use the returned ID directly. Do not perform a follow-up GET to confirm creation unless absolutely necessary for verification.
9. **Verification Strategy:** When asked to verify, only perform the minimum necessary GET calls to confirm the specific attributes requested. Do not perform exhaustive verification of every system field.
