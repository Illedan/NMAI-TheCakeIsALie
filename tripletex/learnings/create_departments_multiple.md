# Create departments (multiple)

**Score:** 10/10
**Rounds:** 15
**Last run:** 3 calls, 0 errors
**Reason:** All three requested departments ('Økonomi', 'Innkjøp', 'Regnskap') were successfully created via POST requests, and their existence was verified using GET calls.

## Representative prompt

Crie três departamentos no Tripletex: "Økonomi", "Innkjøp" e "Regnskap".

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===
- **POST Responses are Complete:** POST requests return the full created object, including its ID and all fields. Do not perform follow-up GET requests to verify creation unless specifically instructed by the user. This is the most efficient way to retrieve the ID of a newly created entity.
- **Efficient GET Requests:** Always use filters like `?name=`, `?email=`, or direct ID access (`/entity/{id}`) and include `?fields=*`. GET lists are truncated to 20 items; never fetch a full list to scan it manually.
- **Mandatory Fields for POST:**
    - `/department`: `name`
    - `/project`: `name`, `projectManager({"id":N})`, `startDate`
    - `/product`: `name`, `vatType({"id":N})`
    - `/customer`: `name`, `isCustomer:true`
    - `/employee`: `firstName`, `lastName`, `email`, `userType`, `department({"id":N})`
- **Invoicing Workflow:**
    1. Verify/update bank account: `GET /ledger/account?isBankAccount=true` then `PUT` to set `bankAccountNumber` if missing.
    2. Create Order: Embed `orderLines` directly in the `POST /order` body.
    3. Create Invoice: Use `POST /invoice` with the `sendToCustomer=true` query parameter.
    4. Date Logic: `deliveryDate` should match `orderDate`. `invoiceDueDate` should be `invoiceDate` + 14 days.
- **Dual Customer/Supplier Role:** To make an entity both, set `isCustomer:true` AND `isSupplier:true` in a single `POST /customer` call. Do not create two separate records.
- **Never Send Null Bodies:** Always include a valid JSON body in POST and PUT requests. Sending a request with a null or empty body will result in a 422 Validation Error.
- **On 422 Errors:** Read `validationMessages` carefully and fix only the reported fields. Do not guess or change unrelated fields.
- **Handling Duplicate Names:** Tripletex allows multiple entities (like Departments or Products) to have the same name. When filtering GET requests by `name`, you may see many results from previous runs. Always trust the ID returned by your specific POST call rather than searching for the name later.
- **Minimize Verification Calls:** Do not perform redundant GET calls to verify work that was already confirmed by the successful POST response. Only verify if the task explicitly requires a multi-step audit or if the initial POST failed.
