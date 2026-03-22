# Create department + assign project

**Score:** 9/10
**Rounds:** 25
**Last run:** 5 calls, 2 errors
**Reason:** The department and project were successfully created and linked. The project number 'P47381905' was requested, but since it was already in use, the system assigned a unique number '919830' instead, which is the correct behavior according to the anti-loop and system-generated identifier rules.

## Representative prompt

Create department 'Dev47381905' and a project 'Proj47381905' (number P47381905) assigned to that department

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **Handle System-Generated Identifiers**: If a requested identifier (like a project number) is rejected because it is already in use, do not force it. Accept the system-generated identifier and report the discrepancy. Do not attempt to retry with the same number.
2.  **Verify Before Creation**: Always perform a GET request with a filter before attempting to create an entity. This prevents duplicate creation errors (422/409) and identifies if the task is already completed.
3.  **Minimize API Calls**: Plan all steps before making any API calls. Use IDs from POST responses directly — never GET after POST just to confirm. Fewer calls = higher efficiency bonus.
4.  **Avoid Beta Endpoints**: Do not use endpoints marked [BETA] in the API docs (e.g., `POST /customer/list`), as they frequently return 403 errors. Use standard individual endpoints instead.
5.  **Strict Field Adherence**: Distinguish clearly between `name` and `number`. Ensure the `number` field is set correctly for projects and products, as it is often a unique identifier in Tripletex.
6.  **Error Recovery**: If an API call returns a 422 error, analyze the `validationMessages` to fix the request body. Never retry the same failing request more than once without modification.
7.  **Entity Linking**: When linking entities (e.g., project to department), ensure the ID used in the POST body matches the ID returned by the GET request for the parent entity.
8.  **Combine Existence Check and Verification**: When performing an initial GET to check if an entity exists, use the `fields` parameter to retrieve all details required by the task. This allows you to verify the entity's state in a single call and avoid redundant follow-up GET requests.
