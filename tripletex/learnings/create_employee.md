# Create employee

**Score:** 10/10
**Rounds:** 6
**Last run:** 10 calls, 5 errors
**Reason:** All employee details, employment terms, salary, occupation code, and working hours were successfully created and verified against the contract. The system correctly handled the existing employee record and confirmed all configurations.

## Representative prompt

Voce recebeu um contrato de trabalho (ver PDF anexo). Crie o funcionario no Tripletex com todos os detalhes do contrato: numero de identidade nacional, data de nascimento, departamento, codigo de ocupacao, salario, percentagem de emprego e data de inicio.

## Learnings

=== LEARNINGS FROM PREVIOUS RUNS ===

1.  **Check for Existing Entities First:** Before creating any entity (Employee, Customer, Supplier, etc.), always perform a `GET` search to see if it already exists. If it does, use the existing ID or update the record via `PUT` instead of creating a duplicate, which causes 422/409 errors.
2.  **Employment Configuration:** For new employees, always set `division` (fetched via `GET /division`) and `remunerationType: "MONTHLY_WAGE"` in `POST /employee/employment/details`. If working hours are specified, you MUST call both `POST /employee/employment/details` (with `shiftDurationHours`) AND `POST /employee/standardTime` (with `hoursPerDay`) to satisfy system validation.
3.  **Occupation Code Precision:** When searching for STYRK codes, use the exact code provided in the contract (e.g., "2511") as a query parameter in `GET /employee/employment/occupationCode?code=XXXX`. **CRITICAL:** Always select the **FIRST** result returned by the API that matches the code. Do not allow the system to default to a different ID if multiple matches exist.
4.  **Validate Input Data Before Action:** Always inspect the provided files/documents thoroughly for all required fields (e.g., national identity number, salary, occupation code) before attempting to create entities. If data is missing, do not invent values; report the limitation clearly.
5.  **Minimize API Calls:** Plan all steps before making any API calls. Avoid redundant `GET` calls to verify entities immediately after a successful `POST` unless necessary for debugging or retrieving a generated ID. Trust the `POST` response body.
6.  **Date Formatting:** Ensure all dates are in `YYYY-MM-DD` format. Tripletex API is strict; incorrect date formats will result in 422 errors.
7.  **Avoid Beta Endpoints:** Do not use endpoints marked [BETA] in the API docs (e.g., `POST /customer/list`), as they often return 403. Use individual creation endpoints instead.
8.  **Handle 422 Errors:** If a `POST` request fails with a 422, carefully read the `validationMessages` in the response. Do not retry the same request; adjust the body based on the specific field error reported.
