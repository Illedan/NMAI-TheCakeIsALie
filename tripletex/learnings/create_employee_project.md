# Create employee + project

**Score:** 8/10
**Rounds:** 29
**Last run:** 9 calls, 4 errors
**Reason:** The employee and project were successfully created as requested. The employee was added as a participant to the project. However, the employee could not be set as the project manager due to sandbox permission limitations, which is a known constraint documented in the system instructions.

## Representative prompt

Opprett en ansatt Emp95381905 Svendsen (emp95381905@example.com). Opprett et prosjekt 'PM95381905' (P95381905) der denne ansatte er prosjektleder.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **SANDBOX PERMISSION LIMITATIONS**: New employees created via API often lack the necessary "Project Manager" role/permission in the sandbox environment. If `POST /project` or `PUT /project` fails with "Oppgitt prosjektleder har ikke fått tilgang", do not retry more than twice. If it fails, acknowledge the limitation in the final report and add the employee as a project participant with administrative access instead of assigning them as the project manager.
2. **CHECK BEFORE CREATE**: Always `GET` by unique identifiers (email for employees, number for projects) before attempting `POST`. If the entity exists, use the existing ID and `PUT` to update if necessary.
3. **MINIMIZE API CALLS**: Do not perform redundant `GET` calls after a successful `POST` or `PUT` unless verification is explicitly required by the task. Trust the API response.
4. **ERROR HANDLING**: If a `422` error occurs, inspect the `validationMessages` field in the response. It contains the specific reason for failure (e.g., "email already exists"). Use this to adjust the next request rather than blindly retrying.
5. **PROJECT NUMBER COLLISIONS**: If `POST /project` fails because the number is already in use, `GET /project?number=XXX` to find the existing project ID and use it instead of failing.
6. **EMPLOYEE USER TYPE**: When creating employees for project management tasks, always set `userType: "STANDARD"`. "NO_ACCESS" will prevent them from being assigned as project managers.
7. **VERIFICATION**: When asked to verify, perform only the necessary `GET` calls to confirm the state of the requested entities. Do not perform exhaustive checks on unrelated data.
