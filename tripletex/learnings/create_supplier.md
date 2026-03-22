# Create supplier

**Score:** 10/10
**Rounds:** 7
**Last run:** 1 calls, 0 errors
**Reason:** The task was to register a supplier. Upon verification, the supplier was already present in the system with the correct details (name, organization number, and email). No further action was required, and the verification confirmed all details were correct.

## Representative prompt

Registrer leverandøren Vestfjord AS med organisasjonsnummer 914908787. E-post: faktura@vestfjord.no.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1. **Verify Existence Before Action:** Always perform a GET search (e.g., by organizationNumber, email, or name) before attempting to POST a new entity. If the entity already exists, use the existing ID instead of creating a duplicate.
2. **Minimize API Calls:** Do not perform unnecessary GET calls after a successful POST if the response already contains the necessary information (like the new ID).
3. **Use Specific Endpoints:** Always use the correct endpoint for the entity type (e.g., use `/supplier` for suppliers, not `/customer` with `isSupplier=true`).
4. **Handle Duplicates Gracefully:** If a search returns multiple results for the same criteria, identify if one is the correct one or if the system already contains the requested data, and report accordingly rather than blindly creating more duplicates.
5. **Follow the "Anti-Loop" Rule:** If an API call fails or returns unexpected results, do not repeat it more than twice. Analyze the response and adjust the request body or parameters.
6. **Verify All Details:** When verifying, ensure every field requested in the task (email, organizationNumber, etc.) is checked against the API response.
7. **Efficiency:** Plan all steps before making any API calls. Fewer calls = higher efficiency bonus. Trust the POST response for IDs and avoid redundant GET calls.
