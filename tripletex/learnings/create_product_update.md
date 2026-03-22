# Create product + update

**Score:** 9/10
**Rounds:** 5
**Last run:** 7 calls, 2 errors
**Reason:** The product was successfully created and updated to the final price of 1500 kr. The only deviation was appending '-UNIQUE' to the product number because the requested number 'P85381905' was already taken in the sandbox environment, which is the correct procedure according to the provided instructions to avoid errors.

## Representative prompt

Opprett produkt 'Oppdater85381905' (P85381905) med pris 1000 kr eks. mva. Oppdater deretter prisen til 1500 kr eks. mva.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Handle Existing Entities Gracefully:** If a `POST` request fails because a unique identifier (like `number`) is already in use, do NOT retry the same `POST` request. Instead, perform a `GET` search to find the existing entity, then use `PUT` to update it if necessary, or use a unique suffix if the task requires creating a *new* entity.
2. **Product Search Strategy:** Do NOT use `GET /product?number=XXXX` if it consistently returns 422 errors. Use `GET /product?fields=id,number,name,priceExcludingVatCurrency,version,vatType(id)` and filter the results locally or use pagination (`from`/`count`) to find the specific product.
3. **Minimize API Calls:** Plan the workflow to avoid redundant `GET` calls. Use the data returned from `POST` or `PUT` responses to verify the state of the entity instead of performing a follow-up `GET` request unless absolutely necessary for verification.
4. **VAT Type Validation:** Always verify available VAT types using `GET /ledger/vatType?fields=id,name,percentage` to ensure the ID is valid for the current context before attempting a `POST`.
5. **Verification:** Perform a final `GET` request only once at the end of the task to confirm that all fields (name, number, price, etc.) match the requirements before declaring the task done.
6. **Avoid Redundant Calls:** Do not repeat the exact same request if it fails with a 422 error. Analyze the validation messages or try a simplified payload to isolate the cause of the error.
