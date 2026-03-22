# Create department + assign employee

**Score:** 10/10
**Rounds:** 5
**Last run:** 7 calls, 2 errors
**Reason:** The department 'Team74381905' was created, and both employees were successfully updated to be associated with this specific department ID (979685). Verification confirms that both employees exist with the correct department assignment.

## Representative prompt

Opprett avdeling 'Team74381905'. Opprett to ansatte i denne avdelingen: Emp74A381905 Olsen (emp74a381905@example.com) og Emp74B381905 Hansen (emp74b381905@example.com).

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Check for Existing Entities First**: Always perform a GET search using filters (e.g., `?email=`, `?name=`) BEFORE attempting to create any entity. If the entity exists, use the existing ID instead of creating a duplicate, which avoids 422 errors.
2. **Verify Before Action**: When a POST fails due to a conflict (e.g., "already exists"), immediately GET the existing entity to retrieve its current state (including `version` and `id`) before attempting a PUT update.
3. **Handle 422 Errors Proactively**: If a request fails with a 422 status, read the `validationMessages` in the response body to identify and fix specific field errors (like missing `dateOfBirth` or duplicate email) before retrying.
4. **Minimize API Calls**: Plan the entire workflow before starting. Use batch endpoints where available and avoid redundant GET calls after a successful POST if the response already contains the necessary information.
5. **Department/Employee Workflow**: When creating employees in a specific department, first create the department to obtain its ID, then use that ID in the `department` object of the employee POST request.
6. **Use Filters**: When searching for entities, always use query parameters (e.g., `?name=`, `?email=`) to avoid fetching large lists and to ensure accurate results.
7. **Avoid Beta Endpoints**: Do not use endpoints marked [BETA] in the API docs, as they often return 403 errors. Use standard endpoints instead.
8. **Verification is Mandatory**: After any creation or update, perform a targeted GET call to verify that the entity exists and has the correct attributes.
9. **Check Response Bodies**: Always inspect the response of a POST request to confirm the ID and other fields, which are often needed for subsequent steps.
10. **Avoid Redundant Creation**: If a search returns multiple results (e.g., multiple departments with the same name), verify which one is the intended target before proceeding, rather than blindly creating a new one.
11. **Update, Don't Recreate**: If an entity already exists but has the wrong attributes (e.g., wrong department), use PUT to update it rather than attempting to POST a new one, which will fail due to uniqueness constraints.
