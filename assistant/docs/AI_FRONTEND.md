# Chat AI Assistant — Facturation frontend

Status at 2026-10-08: IMPLEMENTED and verified by the focused component/API tests and TypeScript check. Latest catalog/stock/logistics card browser verification is pending. This document does not certify Phase 1 completion or production readiness. No production deployment or integration of another application is included.

## Source and integration

The frontend lives in `../facturation/facturation_frontend/`. The reusable Python package remains in this central repository; UI code belongs to the existing Facturation application.

| Source | Responsibility |
| --- | --- |
| `src/app/dashboard/layout.tsx` | One dashboard-root mount, wrapped in Suspense, behind `NEXT_PUBLIC_CHAT_AI_ASSISTANT_ENABLED === 'true'`. |
| `src/components/chat-ai/ChatAIAssistant.tsx` | Floating button, panel, trusted company selection, composer, request lifecycle, history, and navigation. |
| `src/components/chat-ai/ChatAIResults.tsx` | Explicit business-card projections and confirmation previews. |
| `src/components/chat-ai/ChatAIShortcuts.tsx` | Permission-filtered slash help, examples, and command selection. |
| `src/components/chat-ai/company-context.ts` | In-memory bridge from the active application company tab. |
| `src/components/chat-ai/api.ts` | Existing-session authenticated requests, SSE parsing, strict navigation, existing PDF downloads. |
| `src/components/chat-ai/types.ts` | Typed API messages, cards, records, navigation, and capabilities. |
| `src/components/chat-ai/chat-ai.module.sass` | Styling using existing Sass tokens and the current MUI primary color. |

The root also requires the existing access token, authenticated profile identifier, successful capabilities request, and a dashboard pathname. Login and other public routes do not mount the assistant. The backend independently requires its `CHAT_AI_ASSISTANT_ENABLED` flag and authenticates every request; hiding a frontend control is not authorization.

The panel renders through the existing MUI Portal. The workspace is keyed by authenticated user and company. Navigation within the same company preserves the draft, messages, and open panel. Switching company remounts that workspace and clears its visible state; older conversations can be reopened through that company's history. Logout and `session-expired` clear capabilities, company context, and panel state. Browser reload does not automatically reopen the last conversation.

## Approved visual integration

The UI reuses MUI, existing `TextButton`, `DarkTooltip`, `ActionModals`, `DashboardStatCard`, the application theme, and Poppins. It preserves the user-approved light-blue primary background with white floating/send icons. The earlier browser baseline measured the active primary color as `rgba(2, 116, 215, 0.5)`; the component reads the theme rather than hardcoding that color. Small text controls use the existing readable `#525256` foreground.

The FAB is 56 × 56 CSS pixels, fixed at right/bottom 24px on desktop; mobile uses right 16px and `max(16px, env(safe-area-inset-bottom))`. On logistics routes, its bottom offset becomes 96px to avoid the existing floating controls. It has an accessible name, expanded state, tooltip, focus outline, and a reduced-motion rule.

The desktop panel is 440 × 630 CSS pixels, right 24px and bottom 92px, constrained to the viewport. Logistics uses bottom 164px and the corresponding smaller maximum height. Mobile is full-width and uses `visualViewport.height`/`offsetTop`, falling back to `100dvh`, plus safe-area padding. The FAB and panel use `theme.zIndex.drawer + 1` and `+ 2`; they remain below normal MUI modal stacking. There is no separate decorative minimize control or maximize feature. Close/FAB toggle hide the panel without destroying its conversation.

The header has explicit “Nouvelle conversation” and “Historique” text controls on their own compact row. Company context is a separate row. User and assistant messages both have labeled message boxes (“Vous” and “AI Assistant”). The empty state provides practical suggestions instead of a large decorative illustration. Cards retain the existing outlined Paper appearance.

## Company and permission behavior

Company resolution accepts only a positive safe integer present in backend capabilities. Precedence is:

1. Authorized `company_id` in the current URL.
2. Authorized active company published by the application tab.
3. A company selected in the assistant when neither source is available.

A valid detail-page company is published so ordinary navigation without a company hint retains that scope. Without an authorized active company, the panel asks the user to choose one; it does not infer company authority from chat text.

`companyDocumentsWrapperList.tsx` validates explicit `requestedCompanyId` and URL hints against the actual company list. Its explicit prop takes precedence. Each pathname/hint is applied once, so a later manual tab change is not pinned back to the old company. Manual tab changes publish the new company immediately and update the URL with `history.replaceState`, preserving other query parameters and the hash. Outgoing wrapper cleanup does not erase a company published by the next page.

Capability flags reuse `core.permissions` on the backend. Current native helpers permit Caissier edit/delete/print, Commercial edit/print, Comptable print, and Lecture reads. These are application rules, not a separate assistant role hierarchy. Financial reads follow existing company access. Account lookup additionally requires current staff access. The backend also supports native superuser stock access without membership; that company capability has mutation/print flags disabled, and business tools still require membership.

The frontend gates mutation and PDF buttons by capabilities, but every backend tool, PDF endpoint, preview, and confirmation performs its own access checks. Catalog and operations modules below are deliberately read-only in this adapter even when the user can modify them in their normal forms.

## Cards and actions

| Resources | Rendered content and available actions |
| --- | --- |
| Invoice, quote, pro forma, credit note, delivery note | Document number, permitted client/date/status/amount fields; Voir, and permitted Modifier/Supprimer/PDF. |
| Client | Permitted identity; Voir, and permitted Modifier/Supprimer. |
| Article | Reference, designation, product/service label, archive marker, separate purchase/sale prices and currencies; Voir only. |
| Payment | Related invoice number, client, date, native status, amount/currency; Voir only. |
| User | Name, email, admin/active labels; Voir only. |
| Stock balance | Reference/product/location, mapped stock state, Physique, Réservé, Disponible, Entrant, Projeté, Minimum; Voir only. |
| Stock movement | Product/location, mapped movement type, Quantité and Stock après mouvement; Voir only. |
| Stock receipt | Reference, mapped status, dossier, supplier, validation date, supplied receipt lines; Voir only. |
| Stock inventory | Reference/location, mapped status, validation date, supplied expected/counted quantities; Voir only. |
| Logistics dossier | Reference, workflow stage, global status, supplier, expected/actual dates, supplied article/client/quantity/received lines; Voir only. |
| Financial summary | Existing dashboard metric label, verified amount/count, currency, and reporting period. |

Business data is projected from explicit fields; extra backend keys are not iterated into the interface. Stock enum labels reuse `src/utils/rawData.ts`. Monetary display uses the existing `formatNumberWithSpaces`; stock quantities use three decimals. Dates use the existing chat date formatter. At most ten supplied operational detail lines render, with a notice when more lines exist. No detail lines are invented when a search only supplies a summary.

Result navigation uses structured targets checked by `safeNavigation`, not links extracted from model prose. It requires the exact approved path, application, company, resource, and valid identifier. Account routes are global and omit the company query, while their target still carries the authorized conversation company. Searches do not redirect automatically: the user chooses Voir or Ouvrir la page.

Modifier on a selected result opens a validated existing edit-form navigation card. A bounded edit proposed in the conversation instead produces a preview. Supprimer produces a preview and requires the separate confirmation modal. The current resource-field combinations are:

| Resources | Preview labels, using the same translation keys as their forms |
| --- | --- |
| Invoice, pro forma | Remarque; Termes de paiement; Date d'échéance |
| Quote, delivery note | Remarque; Date d'échéance |
| Credit note | Remarque |
| Client | Raison sociale; Nom; Prénom; Adresse |

French/English form labels come from `useLanguage()`. There is no raw-field-name fallback. An unknown resource-field combination hides its values, displays a safe explanation, and disables confirmation. Backend authorization remains authoritative. These labels describe the bounded adapter, not permission to edit every field or a promise that every field is visible for every company: native forms conditionally show due dates for Nectar and remarks for other companies; client identity fields depend on client type.

A successful confirmation refreshes existing RTK Query caches. Deletion returns to the correct resource list if the workspace and route are still current. A completed write still invalidates caches when the user has changed workspace, but it does not overwrite the new workspace's messages or navigation.

## Back-to-list correction

Detail header buttons now navigate to verified list routes instead of `router.back()`. This prevents an AI-opened detail from returning to an unrelated previous page. The shared document wrapper covers quote, invoice, pro forma, credit note, and delivery note, including its error fallback. Standalone client, article, payment, logistics, stock balance/movement/receipt/inventory, user, and company details use their existing list constants. Company-owned list destinations retain `company_id`; native user/company administration stays global. Form cancel behavior was not changed by this correction.

## Conversation, streaming, and shortcuts

The composer accepts up to 4,000 characters, supports multiline input, Enter to send, Shift+Enter for a newline, and IME composition. Mobile input uses 16px text. User language is not selected in the UI: the model instruction follows the current message language, including switches between messages. The current surrounding chat chrome is predominantly French; response-language behavior is not proof of full UI localization.

The client uses authenticated fetch POST streaming. Only `message.delta` becomes provisional response text; `message.completed` installs the final message/cards. A stream without completion raises an incomplete-response error. Errors offer retry with the same request UUID and original invoice/language context even after a same-company route change. The server uses that identifier to avoid duplicating a completed turn.

The stop button aborts the current fetch and invalidates its request generation. Late events and stale history responses cannot replace the current conversation. New conversation, company changes, and unmount likewise discard stale UI delivery. Closing the panel alone preserves the mounted workspace and does not itself cancel inference. Already confirmed writes are not aborted, because cancellation cannot undo a business operation.

The message list follows new content only while the reader is within 64px of the bottom. Scrolling up stops forced movement. A new message or opening a conversation resumes following. History has first-message titles, secondary timestamps, an active-conversation marker, and deletion bound to the exact row. Deleting another history item preserves the current conversation. History is user/company scoped, and reopening refreshes authorized business cards rather than trusting a saved private-data snapshot.

Slash assistance lists `/voir`, `/factures`, `/clients`, `/impayees`, `/paiements`, `/bilan`, `/pdf`, `/modifier`, and `/supprimer`, filtered by the applicable mutation/print flags. Each entry explains its purpose and example. A slash prefix selects intent; descriptions can include client, product, and period without an internal record ID. The help drawer appears only while typing the command prefix, disappears after a space/prose, shrinks within 35% of the panel, and leaves the composer fixed. The backend returns usage for bare commands; `/factures`, `/clients`, `/impayees`, and `/paiements` can also return their bounded default results. `/aide` and `/help` return text help.

## Verification and remaining limits

On 2026-10-08, the focused run passed **100/100 tests** across `ChatAIAssistant.test.tsx` and `api.test.ts`; TypeScript passed:

```sh
NEXT_PUBLIC_DOMAIN_URL_PREFIX='' ./node_modules/.bin/jest --runInBand --no-cache --coverage=false src/components/chat-ai/api.test.ts src/components/chat-ai/ChatAIAssistant.test.tsx
NEXT_PUBLIC_DOMAIN_URL_PREFIX='' ./node_modules/.bin/tsc --noEmit --incremental false
```

Coverage includes safe module routes, human PDF filenames, exact resource actions, read-only card restrictions, field-label rendering, rejected unknown confirmation fields/values, ten-line bounds, history races, company changes, cancellation, streaming scroll behavior, and existing write cache invalidation. The earlier shared wrapper regression run passed 39 tests, including all five document back routes, company hint precedence, unauthorized hints, and manual tab switching.

Recorded browser baselines before the latest module-card expansion include the 440 × 630 desktop panel and 390 × 844 mobile viewport, no horizontal overflow, and zero measured composer-placeholder vertical offset. Screenshots are under `training/evaluations/`, including `chat-desktop-review.png`, `chat-mobile-review.png`, and `placeholder-centered-mobile.png`. These measurements are not a physical-device keyboard test.

Latest catalog/stock/logistics visual checks remain pending with the main browser session. The delegated reviewer could not access MCP Playwright because its profile was already owned; it did not alter or close any tab. Physical mobile keyboard, comprehensive screen-reader behavior, and all modal/overlay combinations have not been certified. An earlier resize/HMR session left the application's existing Drawer `aria-hidden` state stale; a mobile reload cleared it, which is not a general accessibility pass. Model quality and multilingual acceptance remain separate requirements. The frontend has no feedback control despite the available feedback endpoint, and no dedicated shortcut for every newly readable module.

Verified label update: edit commands accept visible form labels (for example **Termes de paiement**); confirmations/cards use existing translations. Nectar article prices use **Prix H.T.**, matching the actual form. Final frontend suite: 184 tests across nine suites; type check and production build passed.
