# Create employee + update

**Score:** 10/10
**Rounds:** 4
**Last run:** 4 calls, 1 errors
**Reason:** The employee was successfully created (or identified if already existing) and the mobile phone number was correctly updated to 11223344 with the Norwegian country code (ID 161), matching the requested +4711223344. All details were verified via API.

## Representative prompt

Create employee Emp84381905 Brown (emp84381905@example.com). Then update their mobile phone to +4711223344.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Handle System Validation Requirements Early:** When creating or updating entities (like employees), the API may require fields not explicitly mentioned in the task (e.g., `dateOfBirth` for employees). Always check validation messages on 422 errors and include the missing fields in the subsequent request to ensure the entity is created/updated successfully.
2. **Verify Phone Number Storage:** When updating a mobile number with a country code (e.g., +47), the API often stores the number without the prefix and uses a separate `phoneNumberMobileCountry` object. Do not attempt to force the prefix into the `phoneNumberMobile` field; verify the `phoneNumberMobileCountry` ID (e.g., 161 for Norway) instead.
3. **Minimize API Calls:** Before creating an entity, use GET with filters (e.g., `?email=`, `?organizationNumber=`) to check if it already exists to avoid duplicates and 422 errors.
4. **Use Correct HTTP Methods:** Use POST for creation and PUT for updates. Ensure the `version` field is included in PUT requests if required by the API to prevent concurrency errors.
5. **Read API Responses:** Always inspect the response body of a POST/PUT request to confirm the state of the entity and identify any fields that were automatically populated or modified by the system.
6. **Avoid Unnecessary Verification:** Once a POST or PUT request returns a 200/201 status, trust the response. Do not perform redundant GET calls unless specifically required to retrieve an ID for a subsequent step.
7. **Handle 422 Errors:** If an API call returns 422, inspect the `validationMessages` array in the response. It contains specific information about which field failed and why. Use this to correct the request body before retrying.
8. **Efficiency:** Plan all steps before making any API calls. Fewer calls = higher efficiency bonus. Use batch `/list` endpoints when creating multiple entities.
