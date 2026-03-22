# Import customers from file

**Score:** 10/10
**Rounds:** 5
**Last run:** 3 calls, 0 errors
**Reason:** All three customers from the CSV were successfully created with the correct details (name, email, invoiceEmail, and phone number) as verified by the subsequent GET calls.

## Representative prompt

Import the customers from the attached CSV file. Create each one in Tripletex.

## Learnings

{
  "learnings": [
    "Always perform a GET request with a unique identifier (e.g., ?name=...) before creating any entity to prevent duplicates.",
    "Use specific filters in GET requests (e.g., ?name=...) instead of fetching large lists to avoid truncation and unnecessary API calls.",
    "Verify entity creation by checking the response of the POST request directly; avoid redundant follow-up GET calls.",
    "When a task specifies an address, always set both physicalAddress and postalAddress with the same values.",
    "When an email is provided, always set both email and invoiceEmail to the same value.",
    "If a request returns a 422 error, inspect the validationMessages in the response body to identify and fix only the specific field causing the issue.",
    "Use batch /list endpoints only when you are certain the entities do not already exist, as they fail if any item in the batch causes a conflict.",
    "Minimize total API calls by planning the workflow steps before execution; fewer calls improve efficiency and reduce the risk of errors.",
    "Avoid unnecessary verification calls after a successful POST; trust the API response if it contains the created entity's ID and details.",
    "When verifying work, use specific search parameters (e.g., name=) rather than broad list requests to avoid pagination issues and ensure accurate confirmation."
  ]
}
