# Implementation Plan: UniTrade Notification System

## Overview

Convert the feature design into a series of prompts for a code-generation LLM that will implement each step with incremental progress. Make sure that each prompt builds on the previous prompts, and ends with wiring things together. There should be no hanging or orphaned code that isn't integrated into a previous step. Focus ONLY on tasks that involve writing, modifying, or testing code.

The plan extends the existing `unitrade_notification` Odoo 17 module (which already ships a basic `unitrade.notification` model and one `mail_template_order_confirmed`). We add the dispatcher, event registry, preferences, controllers, OWL bell, QWeb center/settings pages, 12 new mail templates, security rules, config parameters, two crons, an admin retry view, caller integrations across `unitrade_account` / `unitrade_seller` / `unitrade_order` / `unitrade_payment` / `unitrade_chat` / `unitrade_review`, and the full hypothesis-based PBT suite covering all 19 correctness properties from the design.

Implementation language: **Python 3.10 + Odoo 17 ORM** for server code, **OWL 2 / JavaScript (ES module)** for the frontend bell component, **QWeb XML** for templates, **Tailwind with `tw-` prefix** for styling, and **`hypothesis`** for property-based tests.

## Tasks

- [x] 1. Set up module scaffolding, manifest, and test harness
  - [x] 1.1 Extend `__manifest__.py` and create directory skeleton
    - Update `unitrade_notification/__manifest__.py`: add `depends` on `mail`, `unitrade_seller`, `unitrade_payment`, `unitrade_chat`, `unitrade_review`; declare `data` files (security CSV, security XML, ir_config_parameter, ir_cron, mail_template, notification_templates, notification_assets, notification_admin_views); declare `assets` bundle entry for `web.assets_frontend`
    - Update root `unitrade_notification/__init__.py` to import `models` and `controllers`
    - Create empty `controllers/__init__.py`, `tests/__init__.py`, `static/src/js/`, `static/src/xml/`, `static/src/scss/`, `static/tests/` directories with placeholder files where required
    - _Requirements: 1.8_

  - [x] 1.2 Create test infrastructure (`tests/conftest.py`, `tests/strategies.py`)
    - Register hypothesis profile `'odoo'` with `max_examples=100`, `deadline=None`
    - Implement shared strategies: `event_codes()`, `critical_event_codes()`, `non_critical_event_codes()`, `payloads()`, `urls()` (mix of valid relative paths, https in/out of allowlist, malformed, `javascript:` schemes), `counts()` (0..10000)
    - Add helper to build `unitrade.notification` records via ORM under savepoint for property setUp
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 2. Implement event registry
  - [x] 2.1 Create `models/event_registry.py` with `EVENT_REGISTRY`, `CRITICAL_CATEGORIES`, and helpers
    - 18 entries covering all categories per design (account, seller, order, payment, chat, review, system)
    - Each entry: `{category, channels, template, critical}`
    - Helpers: `get_entry(code)`, `is_known(code)`, `iter_categories()`, `iter_channels_for(category)`
    - Add import to `models/__init__.py`
    - _Requirements: 1.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13, 5.14, 5.15, 7.3_

- [x] 3. Extend `unitrade.notification` model schema
  - [x] 3.1 Add new fields, indexes, sql_constraints, and category→type backward mapping in `models/notification.py`
    - Add fields: `category` (Selection 7-values, required, index), `event_code` (Char, required, index), `reference_model`, `reference_id`, `action_url`, `read_at`, `idempotency_key` (Char, index), `email_state` (Selection: not_applicable/pending/sent/failed), `email_error`, `mail_message_id` (Many2one `mail.mail`)
    - Keep existing `notification_type` for backward compatibility
    - Override `create()` to auto-map `category` → `notification_type` per design table (account/seller/review → system fallback; explicit caller value preserved)
    - Add `_sql_constraints` for `uniq_user_idempotency` on `(user_id, idempotency_key)`
    - Implement `init()` to create composite indexes `unitrade_notif_user_isread_idx` on `(user_id, is_read)` and `unitrade_notif_user_cat_date_idx` on `(user_id, category, create_date)` via `tools.create_index`
    - Set `_order = 'create_date desc, id desc'`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.7, 9.1_

  - [ ]* 3.2 Write property test for category-to-type backward mapping
    - **Property 2: Category-to-Type Backward Mapping**
    - **Validates: Requirements 1.7**

- [x] 4. Implement `unitrade.notification.preference` model
  - [x] 4.1 Create `models/notification_preference.py`
    - Fields: `user_id` (Many2one res.users, required, index, ondelete='cascade'), `category` (same 7-value Selection), `channel` (Selection in_app/email), `enabled` (Boolean default True)
    - `_sql_constraints` `uniq_user_cat_chan` on `(user_id, category, channel)`
    - Class method `_ensure_default_preferences(user_id)` that idempotently creates one row per `(category, channel)` derived from `EVENT_REGISTRY` channels
    - Class method `is_enabled(user_id, category, channel)` returning effective preference (default True when missing; enforces critical-category in_app override)
    - Add import to `models/__init__.py`
    - _Requirements: 2.1, 2.2, 2.5_

  - [ ]* 4.2 Write property test for default preference seeding idempotence
    - **Property 3: Default Preferences Seeding Idempotence**
    - **Validates: Requirements 2.2**

- [x] 5. Implement security ACL and record rules
  - [x] 5.1 Update `security/ir.model.access.csv`
    - Row for `unitrade.notification` for `base.group_user` (read=1, write=1, create=0, unlink=1) and `unitrade_seller.group_unitrade_admin` (full)
    - Row for `unitrade.notification.preference` for `base.group_user` (read=1, write=1, create=1, unlink=1) and admin (full)
    - _Requirements: 1.8, 2.1, 7.1_

  - [x] 5.2 Create `security/notification_security.xml`
    - `ir.rule` `unitrade_notification_user_rule` on `unitrade.notification` with domain `[('user_id', '=', user.id)]` for `base.group_user` (no admin in groups so admin bypasses)
    - `ir.rule` `unitrade_notification_admin_rule` on `unitrade.notification` with full domain `[(1, '=', 1)]` for `unitrade_seller.group_unitrade_admin`
    - Same pair of rules for `unitrade.notification.preference`
    - _Requirements: 7.1_

  - [ ]* 5.3 Write property test for ORM-level user isolation
    - **Property 13: User Isolation via ir.rule**
    - **Validates: Requirements 7.1**

- [x] 6. Implement dispatcher helper functions
  - [x] 6.1 Add `_build_idempotency_key`, `_validate_action_url`, `_get_email_from`, `_render_title_and_message`, `_scrub_payload` in `models/notification.py`
    - `_build_idempotency_key`: deterministic sha1 hex over `event_code|reference_model|reference_id|optional_discriminator`
    - `_validate_action_url`: returns url unchanged for `/`-prefixed paths or `https://` hosts in `unitrade.notification.allowed_url_prefixes`; returns `False` and logs warning for `javascript:`, malformed, or external hosts
    - `_get_email_from`: reads `ir.config_parameter.sudo().get_param('unitrade.notification.email_from')`, falls back to `self.env.company.email`
    - `_render_title_and_message`: pulls registry default and applies `payload['title_override']`/`payload['message_override']` when present
    - `_scrub_payload`: strips known sensitive keys (`password`, `password_reset_token`, `api_key`, `midtrans_server_key`, etc.) before rendering
    - _Requirements: 1.4, 1.5, 6.5, 7.2, 7.4, 8.1_

  - [ ]* 6.2 Write property test for action_url whitelist
    - **Property 16: Action URL Whitelist**
    - **Validates: Requirements 7.4**

  - [ ]* 6.3 Write property test for email_from resolution
    - **Property 12: Email From Resolution**
    - **Validates: Requirements 6.5, 8.1**

- [x] 7. Implement Notification_Dispatcher core (`emit`, `broadcast`, mark/retry helpers)
  - [x] 7.1 Implement `@api.model emit(user_id, event_code, payload=None, channels=None, idempotency_discriminator=None)` in `models/notification.py`
    - Validate `event_code` against `EVENT_REGISTRY`; on miss raise `ValueError`, `_logger.warning`, no DB record
    - Build `idempotency_key`; optimistic search-then-create with savepoint; on `IntegrityError pgcode=23505` rollback and re-fetch
    - Force `category` from registry (overrides caller value)
    - Validate `action_url` via helper; record on failure logs warning but creates record with `action_url=False`
    - Check preference via `unitrade.notification.preference.is_enabled` for in_app channel; skip in_app create when disabled AND category not critical
    - On success log `_logger.info` with `user_id`, `event_code`, `result ∈ {created, skipped, duplicate}`
    - Return single recordset (existing or new)
    - _Requirements: 1.5, 1.6, 2.4, 2.5, 7.2, 7.3, 8.3, 10.1, 10.5_

  - [x] 7.2 Implement `@api.model broadcast(event_code, payload=None, user_domain=None, batch_size=None)`
    - Resolve `batch_size` from `ir.config_parameter` `unitrade.notification.broadcast_batch_size` (default 200)
    - Iterate target users in batches; per-batch try/except so a single failure does not abort the run; log `_logger.warning` with batch index on failure
    - Reuse `emit()` for each user
    - _Requirements: 5.15, 8.2_

  - [x] 7.3 Implement `_send_email_via_template`, `action_retry_email`, `mark_all_as_read`
    - `_send_email_via_template(record, template_xmlid)`: `template.send_mail(record.id, force_send=False)` inside try/except; sets `email_state='pending'` then `'sent'` after successful enqueue, captures `mail.mail` id into `mail_message_id`; on exception sets `email_state='failed'` and `email_error=traceback.format_exc()`; respects email channel preference (and skips entirely if registry channels lack `'email'`)
    - `action_retry_email`: backend button method; re-runs `_send_email_via_template` for selected records; transitions only forward (`pending`/`failed` → `sent`); never regresses `sent` to `pending`
    - `@api.model mark_all_as_read(user_id)`: bulk-update unread records of `user_id`; idempotent (second call writes nothing)
    - Wire `emit()` to call `_send_email_via_template` when registry channels include `'email'` AND email preference is enabled
    - _Requirements: 3.4, 6.6, 8.4, 9.5, 10.3_

  - [ ]* 7.4 Write property test for emit idempotency
    - **Property 1: Emit Idempotency**
    - **Validates: Requirements 1.4, 1.5, 1.6, 10.1**

  - [ ]* 7.5 Write property test for preference enforcement with critical override
    - **Property 4: Preference Enforcement With Critical Override**
    - **Validates: Requirements 2.4, 2.5, 10.5**

  - [ ]* 7.6 Write property test for sensitive payload scrubbing
    - **Property 14: Sensitive Payload Scrubbing**
    - **Validates: Requirements 7.2**

  - [ ]* 7.7 Write property test for unknown event rejection
    - **Property 15: Unknown Event Rejection**
    - **Validates: Requirements 7.3**

  - [ ]* 7.8 Write property test for emit logging
    - **Property 17: Emit Logging**
    - **Validates: Requirements 8.3**

  - [ ]* 7.9 Write property test for email lifecycle state machine
    - **Property 11: Email Lifecycle State Machine**
    - **Validates: Requirements 6.6, 8.4, 8.5**

  - [ ]* 7.10 Write property test for non-blocking email enqueue
    - **Property 19: Non-Blocking Email Enqueue**
    - **Validates: Requirements 9.5**

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Configuration parameters and cron jobs
  - [x] 9.1 Create `data/ir_config_parameter.xml` with default values
    - `unitrade.notification.email_from` (empty default)
    - `unitrade.notification.broadcast_batch_size` = `200`
    - `unitrade.notification.allowed_url_prefixes` = `'/'`
    - `unitrade.notification.retention_days` = `180`
    - _Requirements: 7.4, 8.1, 8.2, 9.4_

  - [x] 9.2 Create `data/ir_cron.xml`
    - `ir_cron_unitrade_notification_retention`: daily at 02:00, calls `unitrade.notification._gc_old_notifications()`
    - `ir_cron_unitrade_notification_review_reminder`: hourly, calls `unitrade.notification._cron_emit_review_reminders()`
    - _Requirements: 5.13, 9.4_

  - [x] 9.3 Implement `_gc_old_notifications` retention method on `unitrade.notification`
    - Reads retention threshold from `ir.config_parameter` (default 180 days)
    - Unlinks records where `is_read=True` AND `create_date < now - threshold days`
    - Uses `_logger.info` with deletion count
    - _Requirements: 9.4_

  - [x] 9.4 Implement `_cron_emit_review_reminders` method on `unitrade.notification`
    - Queries `sale.order` (or order model) with state `delivered`, `delivered_at < now - 24h`, no review by buyer
    - Calls `self.emit(buyer_id, 'review.reminder', {reference_model: 'sale.order', reference_id: order.id})` per pair
    - Uniqueness via idempotency_key (buyer_id, order_id) so reruns produce no duplicates
    - _Requirements: 5.13_

  - [ ]* 9.5 Write property test for retention cron correctness
    - **Property 18: Retention Cron Correctness**
    - **Validates: Requirements 9.4**

  - [ ]* 9.6 Write property test for review reminder uniqueness
    - **Property 10: Review Reminder Uniqueness**
    - **Validates: Requirements 5.13**

- [x] 10. Email templates
  - [x] 10.1 Extend `data/mail_template.xml` with 12 new `mail.template` records
    - `mail_template_account_welcome`, `mail_template_account_password_reset`, `mail_template_seller_application_received`, `mail_template_seller_approved`, `mail_template_seller_rejected`, `mail_template_order_new_for_seller`, `mail_template_order_shipped`, `mail_template_order_cancelled`, `mail_template_payment_success`, `mail_template_payment_pending`, `mail_template_payment_failed`, `mail_template_payment_expired`, `mail_template_system_announcement`
    - Preserve existing `mail_template_order_confirmed`
    - All templates share UniTrade brand header, dynamic body, and footer link to `/my/notifications/settings`
    - `email_from` rendered via `${object._get_email_from()}` expression to honor `ir.config_parameter`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 10.2 Write smoke test for mail template xmlids and footer presence
    - Asserts every `EVENT_REGISTRY[code]['template']` resolves via `env.ref`
    - Greps each template body for `/my/notifications/settings` link
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 11. Implement HTTP controllers (`controllers/main.py`)
  - [x] 11.1 Implement `/my/notifications` GET (notification center page)
    - `@http.route('/my/notifications', type='http', auth='user', website=True)`
    - Resolves `request.env.user`; redirect public users to `/web/login`
    - Reads query params `page` (int, default 1) and `category` (default `'all'`)
    - Builds domain `[('user_id', '=', user.id)]` plus optional category filter, ordered `create_date desc, id desc`, paginates 20 per page
    - Renders QWeb `unitrade_notification.notification_center_page`
    - _Requirements: 3.1, 3.2_

  - [x] 11.2 Implement `/my/notifications/unread_count` and `/my/notifications/recent` JSON endpoints
    - `unread_count`: `@http.route(..., type='json', auth='user')`; returns `{'count': search_count([user_id, is_read=False])}`
    - `recent`: returns top 5 latest as JSON `[{id, title, message, action_url, is_read, create_date, category}, ...]`
    - Both log access at `_logger.debug`
    - _Requirements: 4.1, 4.4, 4.6_

  - [x] 11.3 Implement `/my/notifications/<int:nid>/read`, `/my/notifications/read_all`, `/my/notifications/<int:nid>/delete`
    - All `type='json'`, `auth='user'`, `methods=['POST']`
    - Per-record routes browse + ownership check (raise `werkzeug.exceptions.Forbidden` if `record.user_id.id != user.id` and user not in admin group); log warning on mismatch
    - `read` calls `record.action_mark_read()`
    - `read_all` calls `unitrade.notification.mark_all_as_read(user.id)`
    - `delete` calls `record.unlink()`
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 7.1_

  - [-] 11.4 Implement `/my/notifications/settings` GET and POST
    - GET: triggers `unitrade.notification.preference._ensure_default_preferences(user.id)` first, then renders QWeb `unitrade_notification.notification_settings_page` with all preference rows grouped by category
    - POST: parses form fields keyed `pref_<id>_enabled`, writes to corresponding preference records (after ownership check), renders success flash
    - _Requirements: 2.2, 2.3_

  - [ ]* 11.5 Write property test for list query invariants
    - **Property 5: List Query Invariants**
    - **Validates: Requirements 3.1, 3.2, 4.1, 4.4, 9.1, 10.2**

  - [ ]* 11.6 Write property test for mark-as-read invariants
    - **Property 6: Mark-as-Read Invariants**
    - **Validates: Requirements 3.3, 3.4, 10.3**

  - [ ]* 11.7 Write property test for deletion ownership and consistency
    - **Property 7: Deletion Ownership and Consistency**
    - **Validates: Requirements 3.5, 3.6, 10.4**

  - [ ]* 11.8 Write `HttpCase` examples for settings save and dropdown click-through
    - Authenticated user submits settings POST and verifies persistence
    - Authenticated user GETs `/my/notifications/recent`, asserts shape and order
    - Logged-in user clicks dropdown item → redirected to `action_url` after read mark
    - _Requirements: 2.3, 4.5_

- [x] 12. Implement Notification_Center, dropdown partial, and settings QWeb templates
  - [x] 12.1 Create `views/notification_templates.xml` with three templates
    - `unitrade_notification.notification_center_page` (server-rendered, `t-call="website.layout"`): tab/dropdown filter, paginated list, mark-read and delete buttons (form-encoded POSTs to JSON endpoints), "Mark all as read" button, pagination controls
    - `unitrade_notification.notification_dropdown` (partial reused by bell): top 5 items rendered as anchor tags
    - `unitrade_notification.notification_settings_page` (server-rendered): grid of (category × channel) checkboxes with submit button; honors critical-category lock for in_app
    - All markup uses `tw-` Tailwind classes per workspace convention; respects `unitrade_theme` palette and tipografi
    - _Requirements: 3.1, 3.2, 3.7, 4.4, 6.4_

- [x] 13. Implement OWL Notification_Bell frontend
  - [x] 13.1 Implement `static/src/js/notification_service.js`
    - Exports `notificationService` with `fetchUnreadCount()`, `fetchRecent()`, `markRead(id)`, `markAllRead()`
    - Uses `rpc.query` (or `services.rpc`) against `/my/notifications/*` endpoints; surfaces errors via `_logger`-equivalent `console.warn`
    - Polling timer abstraction: `startPolling(callback, intervalMs=60000)`, `stopPolling()`
    - _Requirements: 4.6_

  - [x] 13.2 Implement `static/src/js/notification_bell.js` OWL component
    - Component class `NotificationBell` (Owl 2 syntax) with `setup()` mounting service, fetching count on mount, dropdown toggle state
    - Badge text helper that returns `''` when count==0, `String(count)` for 1..99, `'99+'` for >99 (Property 8)
    - `onClickItem(notif)` calls `markRead(id)` then `window.location = notif.action_url || '/my/notifications'`
    - `setInterval(60_000)` polling cleared in `onWillUnmount`
    - Mounted into navbar via `registry.category('public_components')` registration
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 13.3 Implement `static/src/xml/notification_bell.xml` OWL template
    - Bell icon + badge span (`tw-` classes; `tw-hidden` when count is 0); dropdown panel listing notifications with action_url links and "Lihat semua" / "Pengaturan" footer links
    - _Requirements: 3.7, 4.2, 4.3, 4.4_

  - [x] 13.4 Create `views/notification_assets.xml` registering bundle entries
    - `<template id="assets_frontend" inherit_id="web.assets_frontend">` adding `notification_service.js`, `notification_bell.js`, `notification_bell.xml`, `notification.scss`
    - _Requirements: 4.1_

  - [ ]* 13.5 Write QUnit (or pure-JS unit) test for bell badge rendering
    - **Property 8: Bell Badge Rendering**
    - **Validates: Requirements 4.2, 4.3**

- [x] 14. Admin backend views with retry button
  - [x] 14.1 Create `views/notification_admin_views.xml`
    - Action `unitrade_notification.action_failed_emails` opening list view of `unitrade.notification` filtered by `email_state='failed'`
    - Form view exposing `email_state`, `email_error`, `mail_message_id`, and a header button bound to `action_retry_email`
    - Menu under admin group only (`unitrade_seller.group_unitrade_admin` or `base.group_system`)
    - _Requirements: 8.5_

- [x] 15. Wire callers (per-event emits) into existing modules
  - [x] 15.1 Wire account events in `unitrade_account` (or auth_signup hook)
    - `account.welcome` after successful signup activation
    - `account.password_reset` after `/web/reset_password` confirmation
    - Use idempotency_discriminator equal to user creation timestamp / token id to keep keys stable
    - _Requirements: 5.1, 5.2_

  - [x] 15.2 Wire seller events in `unitrade_seller` workflows
    - `seller.application_received` on application submit
    - `seller.approved` on admin approval
    - `seller.rejected` on admin rejection (carry rejection reason in payload)
    - _Requirements: 5.3, 5.4, 5.5_

  - [x] 15.3 Wire order events in `unitrade_order` (sale.order state transitions)
    - `order.new_for_seller` on order creation, one emit per distinct seller in line items
    - `order.confirmed` on order confirmation (buyer)
    - `order.shipped` on shipped state transition (buyer; include resi if present)
    - `order.delivered` on delivered transition (both buyer and seller)
    - `order.cancelled` on cancel transition (carry reason)
    - _Requirements: 5.6, 5.7, 5.8, 5.9, 5.10_

  - [x] 15.4 Wire payment events in `unitrade_payment` Midtrans webhook handler
    - Map Midtrans status to event_code: `success`→`payment.success`, `pending`→`payment.pending`, `failed`/`deny`→`payment.failed`, `expire`→`payment.expired`
    - Emit to buyer; on `payment.success` also emit in_app to seller
    - _Requirements: 5.11_

  - [x] 15.5 Wire chat events in `unitrade_chat` with 10-minute grouping window
    - On new message, if recipient not currently viewing the chat, emit `chat.new_message`
    - Compute idempotency_discriminator as `floor(now_epoch / 600)` (10-minute bucket) joined with `chat_id`, so re-emits within window collapse to existing record
    - _Requirements: 5.12_

  - [x] 15.6 Wire review events in `unitrade_review`
    - `review.new_for_seller` when buyer publishes review
    - (Note: `review.reminder` is emitted by cron in 9.4)
    - _Requirements: 5.14_

  - [x] 15.7 Wire `system.announcement` admin trigger
    - Server action / model method on the announcement publish flow that calls `unitrade.notification.broadcast('system.announcement', payload, user_domain=[('active','=',True),('share','=',False)])`
    - Honors `unitrade.notification.broadcast_batch_size`
    - _Requirements: 5.15, 8.2_

  - [ ]* 15.8 Write property test for chat grouping window
    - **Property 9: Chat Grouping Window**
    - **Validates: Requirements 5.12**

  - [ ]* 15.9 Write per-event integration unit tests with mocked dispatcher
    - One `test_event_<code>` per Requirements 5.1–5.15: patches `unitrade.notification.emit`, exercises the caller-side hook, asserts call args (`user_id`, `event_code`, key payload fields)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13, 5.14, 5.15_

- [ ] 16. Final smoke and integration tests
  - [ ]* 16.1 Write module install smoke test
    - Asserts schema fields present on `unitrade.notification` (Req 1.1–1.3)
    - Asserts ACL CSV rows present and ir.rule loaded for both models (Req 1.8, 2.1, 7.1)
    - Asserts composite indexes exist in `pg_indexes` (Req 9.1)
    - Asserts manifest depends resolve and crons registered
    - _Requirements: 1.1, 1.2, 1.3, 1.8, 2.1, 7.1, 9.1_

  - [ ]* 16.2 Write smoke test for bell polling configuration
    - Asserts `notification_bell.js` references `60000` ms polling interval (Req 4.6)
    - _Requirements: 4.6_

  - [ ]* 16.3 Write example test for `broadcast()` honoring batch size from `ir.config_parameter`
    - Sets parameter to small value, broadcasts to N users, asserts batched emission count and that single batch failure does not abort others
    - _Requirements: 8.2_

- [ ] 17. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP. Property tests cover the 19 universal correctness invariants of the dispatcher and surrounding subsystems; example/HttpCase tests cover the 15 per-event Requirement 5 scenarios.
- Each task references specific requirement clause numbers (e.g., `1.4`, `5.12`) and, where applicable, the design property number, to preserve traceability.
- Checkpoints (tasks 8 and 17) are integration pause points — they must not be coded and are excluded from the dependency graph below.
- File-conflict awareness drives the wave plan: `models/notification.py` is touched by 3.1 → 6.1 → 7.1 → 7.2 → 7.3 → 9.3 → 9.4 (sequential waves); `controllers/main.py` is touched by 11.1 → 11.2 → 11.3 → 11.4 (sequential waves); `models/__init__.py` is touched by 2.1 then 4.1 (different waves).
- All Tailwind classes use the `tw-` prefix; all credentials are read from `ir.config_parameter`; every model has `ir.model.access.csv` rows and `__init__.py` imports per workspace AGENTS.md rules.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["3.1", "5.1", "5.2", "9.1", "9.2", "10.1", "13.1", "13.3", "13.4", "14.1"] },
    { "id": 3, "tasks": ["3.2", "4.1", "6.1", "11.1", "12.1", "13.2"] },
    { "id": 4, "tasks": ["4.2", "5.3", "6.2", "6.3", "7.1", "11.2", "13.5"] },
    { "id": 5, "tasks": ["7.2", "7.4", "7.6", "7.7", "11.3"] },
    { "id": 6, "tasks": ["7.3", "7.5", "7.8", "11.4"] },
    { "id": 7, "tasks": ["7.9", "7.10", "9.3", "10.2", "11.5", "11.6", "11.7", "11.8"] },
    { "id": 8, "tasks": ["9.4", "9.5"] },
    { "id": 9, "tasks": ["15.1", "15.2", "15.3", "15.4", "15.5", "15.6", "15.7"] },
    { "id": 10, "tasks": ["9.6", "15.8", "15.9", "16.1", "16.2", "16.3"] }
  ]
}
```
