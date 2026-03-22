# Create department + rename

**Score:** 10/10
**Rounds:** 5
**Last run:** 2 calls, 0 errors
**Reason:** The department was successfully created with the initial name, then updated to the new name, and both states were verified via API calls.

## Representative prompt

Opprett avdeling 'Gammel96381905'. Deretter endre navnet til 'Ny96381905'.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **VERIFY STATE AFTER MODIFICATION:** Always perform a GET call after a POST/PUT to confirm the entity exists and matches the expected state. This is critical for verification tasks.
2. **MINIMIZE API CALLS:** Plan the workflow to achieve the goal in the fewest steps possible. Avoid redundant GET calls if the POST/PUT response already provides the necessary information.
3. **ENTITY UPDATES (PUT):** When updating an entity, ensure the request body includes all required fields (like `version` and `id`) and only editable fields. Including read-only fields returned by a GET request will cause 422 errors.
4. **USE SPECIFIC IDs:** When verifying or updating, always use the specific ID of the entity (e.g., `/department/{id}`) rather than list filters to avoid ambiguity or potential issues with test data.
5. **TRUST POST RESPONSES:** For entity creation, the POST response body contains the definitive ID and initial state. Do not perform an immediate GET call unless the task explicitly requires verification of the created object.
6. **ERROR RECOVERY:** If an API call returns a 422 error, check the endpoint reference for correct field names before retrying. Never retry the same failing request more than once without changing the body or parameters.
7. **ANTI-LOOP RULE:** If you have made the same API call (same method + path + params) more than twice and received the same result, stop immediately. Re-evaluate the request or conclude the task cannot be completed.
8. **DATE HANDLING:** Always use today's date (2026-03-22) unless the task specifies a different date. For date ranges, ensure `dateTo` is exclusive (e.g., use the next day for a single-day query).
