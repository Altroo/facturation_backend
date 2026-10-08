# Edit and deletion attribution

Status: IMPLEMENTED and verified in the isolated PostgreSQL tests on 2026-10-08. Not deployed.

The authenticated requester prepares a bounded action preview. The confirmation endpoint requires the same authenticated user and rechecks the company's existing edit/delete permission, record ownership, expiration and document fingerprint. Neither a model argument nor a browser-supplied identity can determine the actor.

On success, existing django-simple-history records receive `_history_user = request.user` and the confirmation identifier as the change reason. Updates keep normal before/after history. Deleted invoices retain their deletion history.

A separate `chat_ai.AuditEvent` preserves the actor's numeric identifier and label, company, operation, target identifier, changed field names, confirmation identifier, originating chat request identifier, timestamp and source. It does not copy the complete conversation or financial record into the audit log. Both the business operation and its success audit are committed in the same database transaction.

The request identifier links to `Message.request_id` while that conversation exists. Chat retention and conversation deletion do not delete successful write audit entries. If the user account is later deleted, the nullable user relation clears but the actor snapshot remains. The originating message text follows chat retention; the durable record retains its identifier, not its private content.

The restricted Django admin displays these audit entries read-only. Successful mutation audits are excluded from automatic read-audit cleanup. Operators must back up the database and its existing historical tables; the application does not claim protection against a database administrator modifying stored rows.

Verified tests cover edit attribution, deletion attribution, original-request linkage, cross-user confirmation denial, permission revocation, stale/expired previews, single-use confirmation, protected invoice deletion, and audit retention after conversation and account deletion.
