# Create project + update

**Score:** 10/10
**Rounds:** 5
**Last run:** 5 calls, 2 errors
**Reason:** The project was successfully created and updated to the final description 'Phase 2 - Implementation' as requested. Verification confirmed all details match the task requirements.

## Representative prompt

Create project 'Desc89381905' (P89381905) with description 'Phase 1'. Then update the description to 'Phase 2 - Implementation'.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Check for Existence Before Creation:** Always perform a GET request (e.g., `GET /project?query=...`) before attempting to POST a new entity. If the entity already exists, use the existing ID instead of attempting to create a duplicate, which will trigger a 422 error.
2. **Verify Before Updating:** Always perform a GET request to confirm the current state of an entity before attempting a PUT update, ensuring the correct ID and current version are used.
3. **Minimize API Calls:** Combine information gathering where possible. For example, when creating a project, ensure all required fields (like project manager ID) are retrieved in a single initial search rather than multiple calls.
4. **Use Filters:** Always use query parameters (e.g., `?name=`, `?email=`, `?organizationNumber=`, `?number=`, `?query=`) in GET requests to avoid fetching large lists and to ensure the API returns only the relevant entity.
5. **Data Integrity:** When performing a PUT request, ensure the body contains all required fields (as retrieved from the GET request), not just the field being updated, to prevent accidental clearing of existing data.
6. **Check Field Requirements:** Before POSTing, verify the schema. For example, `projectNumber` is often system-generated and should not be included in the POST body if the API returns a 422 error for it.
7. **Verification:** Always perform a final GET request to verify that the state of the system matches the requested outcome before declaring the task "DONE".
8. **Handle 422 Errors Gracefully:** If a POST request fails due to a "number already in use" error, immediately perform a GET request to find the existing entity's ID and proceed with a PUT update if necessary, rather than retrying the POST.
9. **Avoid Redundant POSTs:** If a POST fails due to a validation error (e.g., "already in use"), do not retry the same POST. Immediately switch to a GET to retrieve the existing entity and then use PUT to update it.
