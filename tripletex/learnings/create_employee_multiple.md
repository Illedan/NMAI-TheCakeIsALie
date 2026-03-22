# Create employee (multiple)

**Score:** 10/10
**Rounds:** 5
**Last run:** 8 calls, 2 errors
**Reason:** All five employees were successfully created and verified with the correct names, emails, and department assignment. The verification process confirmed that every detail requested in the task was fulfilled.

## Representative prompt

Create five employees: Emp90A381905 Alpha (emp90a381905@example.com), Emp90B381905 Beta (emp90b381905@example.com), Emp90C381905 Gamma (emp90c381905@example.com), Emp90D381905 Delta (emp90d381905@example.com), Emp90E381905 Epsilon (emp90e381905@example.com).

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Verify Before Action:** Always use GET with filters (e.g., `?email=`, `?name=`) to check if an entity already exists before attempting to create it. This prevents duplicate creation and unnecessary API calls.
2. **Strict Adherence to Required Fields:** Always check the documentation for required fields (e.g., `userType` for employees, `vatType` for products). Missing fields will result in 422 errors.
3. **Error Handling:** If a 422 error occurs, read the `validationMessages` in the response body carefully to identify the specific field causing the issue before retrying. Do not retry the same failing request more than once without changing the body or parameters.
4. **Efficient Data Retrieval:** When searching for IDs (like departments), use the `?name=` or `?number=` filter in the GET request instead of fetching the entire list and parsing it manually.
5. **Minimize API Calls:** Plan all steps before making any API calls. Combine operations where possible. Use batch `/list` endpoints when creating multiple entities, but be prepared to fall back to individual requests if the batch fails.
6. **Verification:** After performing POST operations, perform a GET request to verify that the entity was created with the exact expected values. Use field filtering (e.g., `&fields=...`) to retrieve only the necessary data, reducing payload size and improving efficiency.
7. **Avoid Redundant Verification:** Trust the POST response for confirmation of creation. Only perform a GET verification if there is ambiguity or if the task explicitly requires it.
8. **Batch Endpoint Gotchas:** If a batch request (e.g., `POST /employee/list`) returns a 422 error, it may be due to a single invalid entry. If the error is not clear, proceed with individual `POST` requests to isolate the issue.
9. **Avoid Unnecessary Verification:** Do not perform exhaustive GET verification for every single field if the POST response already confirms the creation and the task does not explicitly demand a secondary verification step. Use verification only when necessary to confirm state or resolve ambiguity.
