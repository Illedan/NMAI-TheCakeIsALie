# Create department + delete

**Score:** 10/10
**Rounds:** 5
**Last run:** 3 calls, 1 errors
**Reason:** The department was successfully created, deleted, and the deletion was verified with a 404 response, confirming the task was fully completed.

## Representative prompt

Opprett avdeling 'Slett83381905'. Deretter slett den.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Verify Deletions:** Always perform a follow-up GET request after a DELETE operation to confirm the entity no longer exists. This is critical for tasks requiring cleanup.
2. **Minimize API Calls:** Plan the workflow to achieve the goal with the fewest possible calls. Avoid redundant GET requests after a successful POST if the response already contains the necessary information (like the new ID).
3. **Check Required Fields:** Before any POST/PUT, consult the endpoint reference to ensure all mandatory fields are included. Missing fields (like `dateOfBirth` for employees or `startDate` for projects) are the most common cause of 422 errors.
4. **Use Specific Filters:** When searching for entities, use query parameters (e.g., `?name=`, `?organizationNumber=`) instead of fetching large lists. This improves performance and reduces the risk of hitting API limits.
5. **Handle 403 Errors:** If an endpoint returns 403, it likely indicates a module is not activated or the user lacks permission. Do not retry the same call; look for an alternative endpoint or approach.
6. **Maintain State:** When a task involves creating and then deleting an entity, perform the deletion immediately after creation and verify the deletion in a single final step to minimize API overhead.
7. **Trust the POST Response:** When an entity is created, the API response contains the object's state. Use this data directly rather than performing a subsequent GET call to "verify" the creation.
