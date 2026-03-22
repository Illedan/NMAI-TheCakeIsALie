# Recent Test Failures Analysis

Generated from last 15 competition logs.

## Files used by the agent

- `tripletex/src/agent.ts` — System prompt, Gemini executor, structural blocks, validation
- `tripletex/src/tripletex-client.ts` — HTTP client, pre-call validation, auto-fixes
- `tripletex/src/server.ts` — Express server, /solve endpoint
- `tripletex/src/api-docs.ts` — Swagger doc indexer
- `tripletex/src/types.ts` — TypeScript types
- `tripletex/.env` — Model: gemini-3-flash-preview

## Log Analysis

### `2026-03-22T05-06-07-853Z.json`

- **Calls:** 21
- **API Errors:** 2
- **Prompt:** Execute the complete project lifecycle for 'System Upgrade Windmill' (Windmill Ltd, org no. 978714609): 1) The project has a budget of 336750 NOK. 2) Log time: Grace Walker (project manager, grace.wal

**Errors:**
```
  422 POST /ledger/voucher | Validering feilet.
  422 POST /invoice | Validering feilet.
```

**Successful actions:**
```
  OK: POST /project
  OK: POST /timesheet/entry/list
  OK: PUT /ledger/account/488354633
  OK: POST /ledger/account
  OK: POST /ledger/voucher
  OK: POST /product
  OK: POST /order
  OK: PUT /ledger/account/488354552
  OK: POST /invoice
```

### `2026-03-22T05-07-11-424Z.json`

- **Calls:** 1
- **API Errors:** 0
- **Prompt:** Registre el proveedor Dorada SL con número de organización 853166553. Correo electrónico: faktura@doradasl.no.

**Successful actions:**
```
  OK: POST /supplier
```

### `2026-03-22T05-07-52-927Z.json`

- **Calls:** 9
- **API Errors:** 1
- **Prompt:** Totalkostnadene auka monaleg frå januar til februar 2026. Analyser hovudboka og finn dei tre kostnadskontoane med størst auke i beløp. Opprett eit internt prosjekt for kvar av dei tre kontoane med kon

**Errors:**
```
  400 POST /project/projectActivity/list | HTTP 405 Method Not Allowed
```

**Successful actions:**
```
  OK: POST /activity/list
  OK: POST /project/list
  OK: POST /project/projectActivity
  OK: POST /project/projectActivity
  OK: POST /project/projectActivity
```

### `2026-03-22T05-08-25-453Z.json`

- **Calls:** 36
- **API Errors:** 1
- **Prompt:** Sie haben einen Arbeitsvertrag erhalten (siehe beigefugte PDF). Erstellen Sie den Mitarbeiter in Tripletex mit allen Details aus dem Vertrag: Personalnummer, Geburtsdatum, Abteilung, Berufsschluessel,

**Errors:**
```
  404 GET /query_api_docs | Object not found
```

**Successful actions:**
```
  OK: POST /department
  OK: POST /division
  OK: POST /employee
  OK: POST /employee/employment
```

### `2026-03-22T05-18-48-244Z.json`

- **Calls:** 18
- **API Errors:** 3
- **Prompt:** Gleichen Sie den Kontoauszug (beigefuegte CSV) mit den offenen Rechnungen in Tripletex ab. Ordnen Sie eingehende Zahlungen Kundenrechnungen und ausgehende Zahlungen Lieferantenrechnungen zu. Behandeln

**Errors:**
```
  422 GET /supplierInvoice | Validation failed
  400 GET /invoice/paymentType | Illegal field in fields filter: name. name does not match a field in the model: PaymentTypeDTO
  400 GET /ledger/paymentTypeOut | Illegal field in fields filter: name. name does not match a field in the model: PaymentTypeOutDTO
```

**Successful actions:**
```
  OK: PUT /invoice/2147595053/:payment
  OK: PUT /invoice/2147595070/:payment
  OK: PUT /invoice/2147595080/:payment
  OK: PUT /invoice/2147595093/:payment
  OK: PUT /invoice/2147595110/:payment
  OK: POST /ledger/voucher
  OK: POST /ledger/voucher
  OK: POST /ledger/voucher
  OK: POST /ledger/voucher
  OK: POST /ledger/voucher
```

### `2026-03-22T05-18-55-098Z.json`

- **Calls:** 29
- **API Errors:** 29
- **Prompt:** Register a travel expense for Charles Harris (charles.harris@example.org) for "Client visit Oslo". The trip lasted 5 days with per diem (daily rate 800 NOK). Expenses: flight ticket 2300 NOK and taxi 

**Errors:**
```
  403 GET /employee | 
  403 GET /employee | 
  403 GET /travelExpense/costCategory | 
  403 GET /employee | 
  403 GET /department | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
  403 GET /employee | 
```

### `2026-03-22T05-20-21-875Z.json`

- **Calls:** 12
- **API Errors:** 0
- **Prompt:** Vi trenger Flybillett fra denne kvitteringen bokfort pa avdeling Kundeservice. Bruk riktig utgiftskonto basert pa kjopet, og sorg for korrekt MVA-behandling.

**Successful actions:**
```
  OK: POST /travelExpense
  OK: PUT /ledger/account/488714896
  OK: POST /travelExpense/cost
  OK: POST /ledger/voucher
  OK: PUT /travelExpense/:deliver
  OK: PUT /travelExpense/:approve
  OK: PUT /travelExpense/:createVouchers
```

### `2026-03-22T05-22-11-491Z.json`

- **Calls:** 10
- **API Errors:** 0
- **Prompt:** Gjer forenkla årsoppgjer for 2025: 1) Rekn ut og bokfør årlege avskrivingar for tre eigedelar: Programvare (307350 kr, 10 år lineært, konto 1250), IT-utstyr (475300 kr, 9 år, konto 1210), Kjøretøy (28

**Successful actions:**
```
  OK: POST /ledger/account
  OK: POST /ledger/account
  OK: POST /ledger/voucher
  OK: POST /ledger/voucher
  OK: POST /ledger/voucher
  OK: POST /ledger/voucher
  OK: POST /ledger/voucher
```

### `2026-03-22T05-23-10-381Z.json`

- **Calls:** 7
- **API Errors:** 0
- **Prompt:** Nous avons envoyé une facture de 11660 EUR à Montagne SARL (nº org. 959783748) lorsque le taux de change était de 10.98 NOK/EUR. Le client a maintenant payé, mais le taux est de 11.65 NOK/EUR. Enregis

**Successful actions:**
```
  OK: PUT /invoice/2147677210/:payment
  OK: POST /ledger/voucher
```

### `2026-03-22T05-27-58-820Z.json`

- **Calls:** 17
- **API Errors:** 0
- **Prompt:** Legen Sie einen Festpreis von 415050 NOK für das Projekt "ERP-Implementierung" für Sonnental GmbH (Org.-Nr. 896608479) fest. Projektleiter ist Mia Meyer (mia.meyer@example.org). Stellen Sie dem Kunden

**Successful actions:**
```
  OK: PUT /ledger/account/488938063
  OK: POST /project
  OK: POST /product
  OK: POST /order
  OK: POST /invoice
  OK: POST /travelExpense
  OK: POST /travelExpense/cost
  OK: PUT /travelExpense/:deliver
  OK: PUT /travelExpense/:approve
  OK: PUT /travelExpense/:createVouchers
```

### `2026-03-22T05-28-48-713Z.json`

- **Calls:** 1
- **API Errors:** 0
- **Prompt:** Opprett kunden Fjordkraft AS med organisasjonsnummer 843216285. Adressen er Fjordveien 129, 2317 Hamar. E-post: post@fjordkraft.no.

**Successful actions:**
```
  OK: POST /customer
```

### `2026-03-22T05-29-22-879Z.json`

- **Calls:** 9
- **API Errors:** 0
- **Prompt:** Créez une commande pour le client Cascade SARL (nº org. 804781943) avec les produits Développement système (1393) à 13950 NOK et Rapport d'analyse (5377) à 22000 NOK. Convertissez la commande en factu

**Successful actions:**
```
  OK: POST /order
  OK: POST /invoice
  OK: PUT /invoice/2147677347/:payment
```

### `2026-03-22T05-29-55-571Z.json`

- **Calls:** 1
- **API Errors:** 0
- **Prompt:** Registre el proveedor Costa Brava SL con número de organización 936616224. Correo electrónico: faktura@costabravasl.no.

**Successful actions:**
```
  OK: POST /supplier
```

### `2026-03-22T05-30-21-751Z.json`

- **Calls:** 30
- **API Errors:** 7
- **Prompt:** Register a travel expense for Charlotte Williams (charlotte.williams@example.org) for "Client visit Bodø". The trip lasted 3 days with per diem (daily rate 800 NOK). Expenses: flight ticket 6200 NOK a

**Errors:**
```
  422 POST /travelExpense/perDiemCompensation | Validering feilet.
  404   | 
  404   | 
  404   | 
  404   | 
  422 POST /ledger/voucher | Validering feilet.
  422 PUT /ledger/account/489003744 | Request mapping failed
```

**Successful actions:**
```
  OK: POST /travelExpense
  OK: POST /travelExpense/cost
  OK: POST /travelExpense/cost
  OK: POST /travelExpense/perDiemCompensation
  OK: PUT /travelExpense/:deliver
  OK: PUT /travelExpense/:approve
  OK: PUT /travelExpense/:createVouchers
  OK: PUT /ledger/account/489003744
  OK: POST /ledger/voucher
```

### `2026-03-22T05-32-14-124Z.json`

- **Calls:** 13
- **API Errors:** 0
- **Prompt:** Enregistrez 9 heures pour Chloé Moreau (chloe.moreau@example.org) sur l'activité "Utvikling" du projet "Mise à niveau système" pour Étoile SARL (nº org. 832109428). Taux horaire : 1900 NOK/h. Générez 

**Successful actions:**
```
  OK: POST /project/hourlyRates
  OK: POST /timesheet/entry
  OK: PUT /ledger/account/489057092
  OK: POST /product
  OK: POST /order
  OK: POST /invoice
```

