# Create customer + contact

**Score:** 10/10
**Rounds:** 5
**Last run:** 4 calls, 1 errors
**Reason:** The customer 'Contacts76381905 Ltd' was successfully created with the specified email and address details. Two contacts, 'John Doe' and 'Jane Smith', were correctly created and linked to the customer. Verification via GET calls confirmed all entities exist with the correct values as requested.

## Representative prompt

Create customer 'Contacts76381905 Ltd' (cont76381905@example.com). Add two contacts: 1) John Doe, john76381905@example.com. 2) Jane Smith, jane76381905@example.com.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Verify with specific filters:** Always use query parameters (e.g., `?name=`, `?email=`, `?organizationNumber=`) when searching for entities. Never rely on list responses without filters, as they are truncated and inefficient.
2. **Minimize API calls:** Combine operations where possible. Do not perform unnecessary GET calls if the POST response already provides the necessary confirmation and ID.
3. **Check for existing entities:** Before creating a new entity, search to see if it already exists to avoid duplicates.
4. **Read error messages:** If a 422 error occurs, always inspect the `validationMessages` in the response body to identify the specific field causing the issue before retrying.
5. **Use correct field names:** Ensure all required fields (e.g., `vatType` for products, `invoiceDueDate` for invoices) are included in the request body as per the API documentation.
6. **Avoid redundant POSTs:** If a POST request fails due to a missing field, do not re-submit the exact same request. Analyze the error, fix the specific field, and then retry.
7. **Address object requirements:** When creating customers, always provide both `physicalAddress` and `postalAddress` objects, even if they contain placeholder data, to satisfy API requirements.
8. **Email field consistency:** When an email is provided for a customer or supplier, set both `email` and `invoiceEmail` to the same value to ensure proper communication routing.
9. **Batch endpoint limitations:** Be aware that some `/list` endpoints (like `POST /contact/list`) may have strict validation requirements or return 422 errors if the payload is not perfectly formatted. If a batch request fails, fall back to individual `POST` requests to ensure completion.
10. **Verify with precision:** When verifying, use the specific ID returned by the creation call to confirm the entity's existence and properties, rather than listing all entities and searching through them.
