# Create department

**Score:** 10/10
**Rounds:** 5
**Last run:** 2 calls, 1 errors
**Reason:** The department was successfully created with the specified name and department number, and verified via API call to confirm all details match the requirements.

## Representative prompt

Create a department named 'Dept23341875' with department number 341898

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===
1. **Verify Before Create:** Always perform a GET request to check if an entity exists before attempting to create it. This prevents 422 errors and unnecessary API calls.
2. **Handle 422 Errors Gracefully:** If a POST request returns a 422 error (e.g., "Number already in use"), do not assume failure. Immediately verify the entity's existence and properties using a GET request.
3. **Verification is Mandatory:** Always perform a GET request after a creation or when verifying existing entities to confirm they match the requested parameters exactly.
4. **Minimize API Calls:** Plan all steps before making any API calls. Fewer calls = higher efficiency. Do not perform redundant GET calls if the information is already available from a previous response.
5. **Use Specific Filters:** When searching for entities, use query parameters like `?name=` or `?departmentNumber=` to avoid fetching large lists and to ensure the search is efficient.
6. **Avoid Beta Endpoints:** Do not use endpoints marked [BETA] in the API docs as they often return 403. Use stable alternatives.
7. **Error Recovery:** If an API call returns a 422 error, check the endpoint reference for correct field names before retrying. Never retry the same failing request more than once without changing the body or parameters.
8. **Report Discrepancies:** If a verification step reveals a mismatch, report it clearly. If everything matches, confirm the success.
