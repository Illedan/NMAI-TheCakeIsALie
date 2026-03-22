# Create employee from file/contract

**Score:** 10/10
**Rounds:** 4
**Last run:** 14 calls, 5 errors
**Reason:** All onboarding steps were completed successfully: employee created, employment record linked to the correct division, employment details (salary, percentage, occupation code, working hours) configured, and standard time set. Verification confirmed all values match the offer letter.

## Representative prompt

Du har mottatt et tilbudsbrev (se vedlagt PDF) for en ny ansatt. Utfor komplett onboarding: opprett den ansatte, tilknytt riktig avdeling, sett opp ansettelsesforhold med stillingsprosent og arslonn, og konfigurer standard arbeidstid.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **Employment Details & Salary/Working Hours:** To satisfy the "konfigurer standard arbeidstid" requirement, you MUST perform three distinct actions:
    a) `POST /employee/employment` (base record).
    b) `POST /employee/employment/details` (salary, percentage, occupation code, `workingHoursScheme:"NOT_SHIFT"`, and `shiftDurationHours:X`).
    c) `POST /employee/standardTime` (with `hoursPerDay:X`).
    Failure to do all three will result in incomplete onboarding.
2.  **Occupation Codes:** Do not search by name. Use `GET /employee/employment/occupationCode?code=XXXX` to find the correct ID. If the exact code isn't found, use the first result that starts with the requested STYRK code.
3.  **Division Requirement:** Employment creation requires a `division` object. Always `GET /division` first to find a valid ID to link to the employment record.
4.  **Entity Existence:** Before creating a new entity (employee, customer, etc.), always search for it first (e.g., `GET /employee?email=...`) to avoid 422/409 errors caused by duplicates. If it exists, use the existing ID and `PUT` to update if necessary.
5.  **Validation Errors (422):** Always read the `validationMessages` array in the response body. It explicitly states which field is missing or invalid. Do not guess; fix the specific field mentioned.
6.  **Date Handling:** Always use the exact dates provided in the source documents (e.g., start date, date of birth). Use `YYYY-MM-DD` format.
7.  **Efficiency:** Minimize total API calls. Use `GET` to verify existence, then `POST` once. Avoid redundant `GET` calls after a successful `POST` if the response already contains the necessary information.
8.  **Employee Creation:** When creating an employee, do not set `isContact=true`. If a start date is provided, you must create the employment record separately after the employee is created.
