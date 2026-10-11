# Gestion Magasin assistant discovery

Status: source discovery completed for the implemented adapter; see [actual implementation and remaining gates](AI_GESTION_MAGASIN_PROGRESS.md). Model training/acceptance is incomplete. Exact application identifier: `gestion_magasin`. The shared Qwen3.5-0.8B model and Colibri runtime will be reused; no new model download or parallel training job is planned.

## Verified architecture and application modules

Django/DRF, PostgreSQL, JWT/dj-rest-auth, Redis, Celery, Channels and django-simple-history. The existing `ai_assistant` package is text assistance, not the new business chat adapter. Native backend modules are `account`, `store`, `catalog`, `stock`, `sales`, `finance`, `attendance`, `reporting`, notifications and websockets. Next.js 16/React 19 uses MUI, Redux Toolkit and the existing `magasinApi` client. The authenticated root is `src/app/dashboard/layout.tsx`.

Verified entities include Store/StoreMembership/Role; Product/Category/ProductUnit/ProductStockTrackingItem; StockBalance/StockMovement/StockAddRequest/StockTransfer/Purchase/InventorySession and their lines; Customer/PaymentMode/Promotion/Sale and their lines; Expense/ExpenseCategory; Employee/AttendanceRecord. Operational records have native history. Product catalogue records are global; stock balances and most business transactions belong to a store.

Frontend routes include dashboard, article, stock, store-stock, stock-transfers, purchases, inventory, stores, sales, pos, caise, promotions, expenses, pointage and users. Detail/edit pages exist for the corresponding primary records. Do not invent a customer detail route: no standalone customer page was found in the route inventory. Keep the existing `caise` spelling in navigation.

## Native security and scope

`store/permissions.py` defines the existing roles: direction, responsable, vendeur and lecture. Active StoreMembership plus active Store controls access. Native WRITE_ROLES are direction/responsable/vendeur; MANAGEMENT_ROLES are direction/responsable. Staff has native store bypasses. Reuse these helpers, not a replacement role hierarchy.

Account flags include read/print/create/edit/delete plus promotion creation and wholesale-sale permissions. Endpoint enforcement varies by operation; the adapter must respect the actual action checks and permitted fields. User administration and activity history remain administrator-only.

The frontend contains additional enforced module gates. `Protected` defaults to `is_staff` (`src/components/layouts/protected/protected.tsx`), so omitted `permission` does not mean ordinary read access. The backend adapter preserves these existing restrictions even where a native API endpoint checks only authentication/store membership.

| Native screen or action | Verified frontend gate | Backend constraint to retain |
| --- | --- | --- |
| Dashboard reports, store-stock, purchase lists/details/forms, transfer lists/details, store administration | Staff-only | Fresh staff check plus selected-store scope; membership alone is insufficient for assistant reports |
| Promotion lists/details | Staff-only | Do not expose promotion administration through ordinary record searches |
| Article, stock, inventory, sale, expense and attendance lists/details | Read flag or staff, subject to route restrictions below | Native authorized query for that resource plus validated active scope |
| Article/stock/attendance edit forms | Edit flag or staff | Native management-role checks for that store, with the attendance exception below |
| Inventory and expense forms, including edit mode | Create flag or staff | Preserve the actual form gate when offering navigation; direct confirmed mutations require the existing action checks |
| Promotion form | Promotion-creation flag or staff | Native management/store and promotion rules still apply |
| POS | Create flag or selected-store vendeur | Selected-store vendeur can print its receipt without the generic print flag; wholesale mode is unavailable for that selected role |

`src/utils/vendeurAccess.ts` defines a vendeur-only account from active memberships outside global stock: at least one membership and every such role is vendeur. `src/contexts/initEffects.tsx` redirects this account to `/dashboard/caise` from disallowed routes. Only that POS route, profile/password settings and changelog are allowed. This is an enforced native route restriction, not just a hidden menu. Assistant navigation, suggestions, knowledge and financial tools must not bypass it. Mixed-role users still require the native role check for the specific action/store. The POS accesses catalogue products for scanning; that does not authorize company-wide reports or unrelated record lists.

`pointage_only` is a critical exception. `account/middleware.py` explicitly blocks non-attendance API paths for these accounts, while store helper functions intentionally grant access to active stores for attendance. It is unsafe to interpret those helper results as general financial/catalogue access. The assistant entry point for these accounts explicitly retains an attendance-only capability set and be tested through the real middleware. Only `/api/ai/v1/` is added to the middleware allowlist; the adapter independently enforces attendance-only capabilities.

Attendance has another explicit native scope rule: the special attendance store with code `mbr-south` expands attendance **list** queries and removes the store filter. Outside that scope, native employee queries filter active unlinked commercial-advisor records. Attendance **detail/mutation** uses `_attendance_base_queryset`, which retains ordinary membership scope. A visible list item therefore does not automatically grant its detail/edit action. `AttendanceRecordSerializer.validate` maps an MBR-South submission to the employee's real store; revalidate that resolved store at execution. The existing pointage-only frontend grants delete regardless of its generic delete flag. Preserve this attendance-specific behavior without extending it to other modules.

Stock-add requests also have an owner/direction boundary. `_stock_add_request_queryset` allows ordinary members only their own requests; direction can see other requests in its stores. Approval/rejection specifically requires direction, not any management role. Reuse these native rules before returning records, counts or actions.

The native ProductSerializer's stock methods query the supplied store hint directly. Its endpoint's catalogue visibility is global, but that does not make arbitrary `store_id` serializer context trustworthy. The assistant must validate the selected store before supplying context or reading stock fields; do not blindly forward model/browser store hints to the serializer. Preserve the actual `StockBalance.effective_min_stock` semantics, including an explicit zero threshold.

The existing store tabs use the membership API, route `store_id`, and a local selected-store preference. Native tab changes do not always update the URL. Assistant integration therefore needs a trusted backend scope plus explicit frontend tab-change synchronization; local storage or URL values alone cannot authorize a store. Global-stock pages and attendance scope require their existing special handling.

## Authoritative business calculations and actions

`stock/services.py` owns locked stock movement, sales/returns, validated transfers, purchase receipt and inventory validation. `sales/services.py` owns sale creation and voiding. An assistant must call native operations and preserve their effects, validation and history; changing raw balances or deleting a confirmed sale directly would be incorrect.

`reporting/views.py` and ReportingScopeFilter provide existing scoped reports. Confirmed sales, received purchases, expenses, native stock valuation and sales-line margins are separately calculated. The dashboard `net_total` is sales minus expenses minus received purchases; it must not be presented as audited accounting profit. `today_cash_total` uses today's paid sale amounts regardless of the requested report period, and its query does not restrict payment mode to physical cash. Labels must explain the actual metric. Global catalogue counts/expiration counts must not be represented as store-only stock counts. The report endpoint currently returns several broader fields together; any assistant adapter must return a bounded selected result rather than forwarding the full payload.

Sale PDF generation exists only for wholesale sales and requires the native print flag or staff; it supports French/English. A POS receipt is a different capability. Sale voiding calls `void_sale` and restores stock, whereas native ordinary sale deletion directly deletes the row; do not equate the two or silently select one for the other. Product deletion can cascade stock balances and tracking rows (other financial relationships are protected), so a reviewed proposal must account for dependencies before it can be exposed. Sale/customer relations must be checked before returning related names or documents; direct native serializers can accept changes to relationships.

Sale PDF generation is an existing native capability. Transfers/inventories/purchases have separate state-changing confirmation endpoints; these must not be confused with read-only navigation or ordinary descriptive edits.

## Implementation gates

1. Finish native endpoint/serializer/filter and frontend page permission mapping before creating tools.
2. Define bounded, permission-aware record search/navigation for real modules, including descriptive queries and bare slash usage.
3. Reuse the shared MUI chat/robot, active store behavior, English/French suggestions and conversation isolation.
4. Integrate native financial reports with accurate labels, period semantics and store scope.
5. Add only tested native mutations behind exact confirmation and actor-attributed history; preserve catalogue/global and related-record boundaries.
6. Generate approved synthetic EN/FR data from registered capabilities, freeze held-out cases before baseline, retain prior application curricula, and train only after the preceding run/evaluation finishes.
7. Test real JWT middleware, role/flag combinations, membership revocation, attendance-only access, global-stock access, malicious records, confirmation retries and cross-store history before release.

No production data has been extracted for training. Subsequent local source changes and disposable-database checks are recorded in the progress document. Production deployment and model activation are separate gates.
