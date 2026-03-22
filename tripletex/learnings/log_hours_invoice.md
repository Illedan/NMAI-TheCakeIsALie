# Log hours + invoice

**Score:** 10/10
**Rounds:** 6
**Last run:** 18 calls, 5 errors
**Reason:** All tasks were completed successfully: timesheet entry was logged, product was created, order was generated, and invoice was created and sent to the customer. Verification confirmed all entities exist with the correct values (15 hours, 1950 NOK/h, correct customer and project).

## Representative prompt

Log 15 hours for Samuel Williams (samuel.williams@example.org) on the activity "Analyse" in the project "Website Redesign" for Windmill Ltd (org no. 898523942). Hourly rate: 1950 NOK/h. Generate a project invoice to the customer based on the logged hours.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **Timesheet Conflict Handling:** If `POST /timesheet/entry` returns a 409 Conflict, an entry already exists for that employee/project/activity/date. Do NOT retry the POST. Instead, `GET` the existing entry for that day, then `PUT` to update the `hours` and `hourlyRate` on the existing ID.
2.  **Order Line Creation:** Order lines cannot be added via `POST /order/line`. They must be included in the initial `POST /order` body. If an order is created incorrectly, delete it and create a new one.
3.  **VAT Type Accuracy:** Always `GET /ledger/vatType?typeOfVat=OUTGOING` to find the correct `id` for sales. Using an incorrect `vatTypeId` (e.g., incoming for sales) will cause 422 errors.
4.  **Project Activity Linking:** When logging timesheets to a project, you MUST use an activity that is linked to that specific project. Use `GET /activity?projectId={id}` to find valid project-specific activities. Do not use general activities.
5.  **Minimize API Calls:** Plan the workflow to use the minimum number of calls. Use `GET` with specific filters (e.g., `organizationNumber=`, `email=`, `query=`) to find IDs efficiently. Avoid unnecessary `GET` calls after a successful `POST`.
6.  **Verification:** After completing tasks, perform targeted `GET` calls to verify that the created entities (timesheet, product, order, invoice) contain the expected values.
7.  **Error Handling:** If a request fails, read the `validationMessages` to identify the specific field or logic error before retrying. Do not retry the exact same request.
8.  **Field Names:** Always verify field names in the endpoint reference (e.g., `orderLines` instead of `orderLine`, `priceExcludingVatCurrency` instead of `priceExcludingVat`).
