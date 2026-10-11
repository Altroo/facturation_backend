# Contracts integration discovery

Application identifier: `contrat`. Native repositories: `contracts_backend` and `contracts_frontend`. This adapter reuses the centralized Chat AI Assistant package and the shared model; it does not add another model download or inference service.

## Verified architecture

The backend uses Django, Django REST Framework, PostgreSQL, Simple JWT/dj-rest-auth, Celery and django-simple-history. Existing account, contract, project, PDF and Word views remain authoritative. The frontend uses Next.js, React, MUI and Redux Toolkit. The authenticated root is `src/app/dashboard/layout.tsx`; native pages cover contract and user lists, details and forms. There is no standalone project detail page and no persistent active-company tab.

`Contract` contains a company enum, category, company/category-scoped business reference, client or subcontractor description, dates, status, currency, native financial properties and an optional `st_projet` relation. `Project` contains its company, description, address, owner, permit and predefined flag. Users have native read/print/create/edit/delete flags; staff bypass those checks. User administration is staff-only.

The two native company values are `casa_di_lusso` and `blueline_works`. There is no user-company membership relation. The assistant asks which company the conversation concerns and applies that scope to every contract/project operation. This narrows existing access; it does not invent a new role hierarchy. Assistant adapter IDs 1/2 map to the native enum in trusted backend code.

## Business operations and limits

Contract and project search uses native model/filter metadata with bounded name, reference, client, subcontractor, project, status, category, currency and date filters. Contract amounts reuse the existing HT/TVA/TTC properties. A payment schedule is not a payment ledger. The application has no verified collected-revenue/profit reporting service, so the assistant offers no invented financial-summary tool.

PDF/Word downloads delegate to the existing generators after fresh read/print/company checks. Native contract/project edit and delete views remain responsible for writes; the assistant proposes only approved prose/contact/date fields and requires a separate exact-target confirmation. Financial fields, roles, permissions, company changes and arbitrary code/query execution are not exposed. Creation opens the native form with a validated selected-company hint.

Native project deletion detaches contracts. The assistant retains the predefined-project guard, describes the detachment, and refuses deletion when another company's contracts are linked. The native serializer permits a mismatched contract/project relation; the assistant suppresses that related data and refuses PDF/Word rendering that could include the other company's project details. Related rows are locked during document generation and confirmation checks.

## Integration boundaries

- Versioned `/api/ai/v1/` endpoints use existing authenticated identity.
- Tools: `search_records`, `get_record`, `navigate`, `knowledge`, `previous_results`, `contract_document`, `prepare_change`.
- Each tool rechecks native flags, object scope, bounded arguments and permitted output fields. Users cannot supply a trusted role or company through model arguments.
- Conversations belong to one user/company and use fresh authorization stamps. Stored results, knowledge versions and pending actions are revalidated when reopened.
- Inline project selection is bound to its originating page and retry request; new page context takes precedence.
- Native history and durable confirmation audit identify the instructing user. Audits omit business payloads.
- Eight approved EN/FR knowledge documents use permission/scope filtering before lexical ranking; no separate vector service is introduced for this small collection.
- The canonical MUI chat interface is copied from the central source manifest; existing icons, fonts and local SVG robot require no second design library.

## Constraints and verification status

The feature defaults to disabled. Local synthetic PostgreSQL and dummy logins provide integration evidence; no production records enter fixtures or training. The current production model has not been replaced, and Contracts has not been trained or activated in production. Model acceptance, shared-model regressions and deployment verification remain separate gates. See [Contracts progress](AI_CONTRACTS_PROGRESS.md).
