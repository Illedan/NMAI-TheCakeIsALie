# Create project + close

**Score:** 10/10
**Rounds:** 5
**Last run:** 4 calls, 1 errors
**Reason:** The project was successfully created and closed with the correct name, number, and status. Verification confirmed all details, including the mandatory end date required for closing a project.

## Representative prompt

Create project 'Close81381905' (P81381905). Then close the project (set isClosed to true).

## Learnings

{
  "learnings": [
    {
      "priority": 1,
      "warning": "Closing a project requires an end date.",
      "solution": "When setting `isClosed` to `true` on a project, the `endDate` field is mandatory. Always include `endDate` in the same PUT request to avoid 422 validation errors."
    },
    {
      "priority": 2,
      "warning": "Check existence before creation.",
      "solution": "Always perform a GET request to check if an entity (e.g., project, customer) already exists before attempting to POST. This prevents unnecessary 422 errors and allows you to work with existing data."
    },
    {
      "priority": 3,
      "warning": "Minimize API calls.",
      "solution": "Verify the state of the system using the response object from the creation/update call whenever possible, rather than performing an immediate follow-up GET call, unless specific fields were not returned in the initial response."
    },
    {
      "priority": 4,
      "warning": "Read validation messages.",
      "solution": "Always read the `validationMessages` in a 422 error response carefully. They explicitly state which fields are missing or invalid, allowing for precise corrections."
    },
    {
      "priority": 5,
      "warning": "Data integrity during creation.",
      "solution": "Ensure all required fields (like `startDate` and `projectManager`) are provided during creation to avoid unnecessary update calls."
    }
  ]
}
