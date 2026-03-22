# Create customer + order

**Score:** 10/10
**Rounds:** 10
**Last run:** 8 calls, 2 errors
**Reason:** The customer was created with the correct name and email (both email and invoiceEmail set). An order was created for this customer on the specified date with the correct line item (Consulting services), quantity (10), and unit price (2000 NOK excluding VAT). All details were verified via API calls.

## Representative prompt

Create customer 'Order41948313 Ltd' with email order41948313@example.com. Then create an order for this customer with a line item: 'Consulting services', quantity 10, unit price 2000 NOK excluding VAT.

## Learnings

{
  "learnings": [
    {
      "priority": 1,
      "warning": "Avoid redundant order line creation by not embedding order lines in the initial POST /order if there is any risk of validation failure.",
      "solution": "Create the order first with minimal required fields (customer, dates). Only after a successful response, add order lines using POST /order/orderline. This prevents creating an order shell with duplicate or invalid lines."
    },
    {
      "priority": 2,
      "warning": "Do not use trial-and-error for VAT types or product creation.",
      "solution": "Always perform a GET /ledger/vatType first to identify the correct ID for the required VAT rate. Do not guess IDs. If a POST /product fails, check the validationMessages and fix the specific field (e.g., vatType) rather than retrying with different IDs."
    },
    {
      "priority": 3,
      "warning": "Minimize API calls by using filters.",
      "solution": "Use query parameters (e.g., ?name=, ?email=, ?organizationNumber=, ?number=, ?query=) in GET requests to fetch specific entities. Never fetch large lists and filter them manually."
    },
    {
      "priority": 4,
      "warning": "Trust the POST response data.",
      "solution": "Do not perform unnecessary GET calls to verify entities immediately after creation unless required for debugging. Use the IDs returned in the POST response directly."
    },
    {
      "priority": 5,
      "warning": "Data integrity during entity creation.",
      "solution": "Ensure all required fields (e.g., invoiceEmail for customers, vatType for products) are set correctly in the initial POST request to avoid needing subsequent PUT requests."
    },
    {
      "priority": 6,
      "warning": "Avoid getting stuck in loops when API calls fail.",
      "solution": "If an API call fails, analyze the validationMessages carefully. If the same request fails twice, change the approach (e.g., use a different endpoint or different field values) rather than repeating the same call."
    },
    {
      "priority": 7,
      "warning": "Inefficient search for existing products.",
      "solution": "When checking for existing products, use specific query parameters like ?number= or ?name= instead of fetching a large list of products and filtering manually."
    },
    {
      "priority": 8,
      "warning": "Incorrect endpoint usage for order lines.",
      "solution": "Do not attempt to use POST /order/line or POST /order/line/list if the API documentation or previous attempts indicate they are not supported or return 405/404. Embed order lines directly in the POST /order request body if the endpoint supports it, or verify the correct endpoint for adding lines to an existing order."
    },
    {
      "priority": 9,
      "warning": "Unnecessary verification calls.",
      "solution": "After completing a task, only verify the final state if explicitly requested. Avoid excessive GET calls to confirm every single field of every created entity unless necessary to ensure task completion."
    },
    {
      "priority": 10,
      "warning": "Product name collision during creation.",
      "solution": "When creating a product, if a name collision occurs, search for the existing product by name first. If it exists and matches the requirements, use its ID instead of attempting to create a new one with a modified name."
    }
  ]
}
