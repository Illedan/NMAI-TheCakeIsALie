# Ledger analysis + create projects

**Score:** 10/10
**Rounds:** 6
**Last run:** 13 calls, 5 errors
**Reason:** The ledger analysis correctly identified the top cost accounts with the largest increase from January to February 2026. Projects and activities were successfully created for each of these accounts, and verification confirmed their existence in the system.

## Representative prompt

Totalkostnadene økte betydelig fra januar til februar 2026. Analyser hovedboken og finn de tre kostnadskontoene med størst økning i beløp. Opprett et internt prosjekt for hver av de tre kontoene med kontoens namn. Opprett også en aktivitet for hvert prosjekt.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Avoid Infinite Loops:** If an API call (method + path + params) returns the same result twice, or if you find yourself repeating the same POST request, STOP immediately. Do not repeat it. Analyze the response, check the documentation, or try a different endpoint/approach.
2. **Verify Before Action:** Always check if an entity (e.g., project, activity, customer) already exists using a `GET` request before attempting to `POST` a new one. If it exists, use the existing ID.
3. **Correct Linking Workflow:** When linking entities (e.g., `project` to `activity`), ensure you are using the correct endpoint and structure. Do not assume a `POST` to a resource is the correct way to link; check the documentation for specific association endpoints (e.g., `/project/projectActivity`).
4. **Complete All Subtasks:** When a task requires processing multiple items (e.g., "find the top 3 accounts"), you MUST process ALL of them. Plan the full workflow to iterate through all identified items before finishing.
5. **Data Aggregation Logic:** When analyzing ledger changes, do not rely on a single `GET /ledger/posting` call. Fetch data for the two periods separately, aggregate the amounts per account in your own logic, and then calculate the difference.
6. **Correct Field Filtering:** When using the `fields` parameter, do not use dot notation (e.g., `account.number`). Use parentheses for nested objects (e.g., `account(number,name)`). Ensure the requested fields exist in the model.
7. **Minimize API Calls:** Plan all steps before making any API calls. Use batch `/list` endpoints when creating multiple entities. Fewer calls = higher efficiency bonus.
8. **Always Use Today's Date:** Use today's date unless the task specifies a different date.
9. **Handle 422 Errors:** If a POST request returns a 422 error, carefully read the `validationMessages` to identify the specific field causing the issue and correct it in the next attempt.
10. **Check API Method Validity:** Before calling a GET endpoint, verify if it supports the intended parameters or if it is a collection endpoint. For example, `GET /project/projectActivity` is not a valid way to list all activities for a project; use `GET /project/{id}/projectActivity` or check the specific resource endpoint.
11. **Avoid Redundant POSTs:** Do not attempt to create an entity if a `GET` request confirms it already exists. If a `POST` fails due to "Name already in use", immediately perform a `GET` to find the existing ID and use it instead of retrying the `POST`.
