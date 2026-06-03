# Moderation and Audit Log Plan

Status: Updated after source audit
Priority: P1
Last reviewed: 2026-05-18

## Update 2026-05-18

Moderation sudah ada sebagian, tetapi audit log admin belum ada. `unitrade.chat.report` punya review/block/unblock flow untuk chat. `unitrade.seller` punya reported seller state dan action review/resolved/revoke. `unitrade.security.activity` sudah mencatat aktivitas akun seperti register, OTP, login, password change, dan deactivate, tetapi model itu bukan audit log admin lintas modul.

Koreksi plan:

- `unitrade.security.activity` tetap untuk user security history.
- Buat model baru `unitrade.admin.audit.log` untuk action admin lintas seller/product/payment/dispute/payout/settings/report.
- Semua method action kritis harus memanggil audit helper dari Python, bukan hanya mengandalkan chatter.
- Moderation queue harus menggabungkan chat report, seller report, product report nanti, refund dispute, dan user block review.
- Public action yang berdampak ke trust/financial harus punya group gate di method. Ini bagian dari moderation hardening, bukan hanya security XML.

## Tujuan

Admin dapat memoderasi laporan user/seller/chat/produk, dan semua aksi penting admin tercatat untuk audit.

## Status Saat Ini

- Chat report moderation sudah ada sebagian.
- Seller reported view sudah ada.
- Belum ada audit log umum lintas modul.
- Belum ada moderation queue terpadu.

## Scope MVP

- Moderation queue lintas laporan.
- Link ke chat report, seller report, product report, dispute.
- Action block/unblock user.
- Action revoke seller.
- Action hide product.
- Audit log untuk semua action kritis.

## Audit Event

- Approve/reject seller.
- Block/unblock user.
- Revoke seller.
- Reject product.
- Waive listing fee.
- Mark transaction problem.
- Approve/reject refund.
- Mark payout paid.
- Change critical setting.

## Data Model

Model baru:

- `unitrade.admin.audit.log`
  - `admin_user_id`
  - `action_type`
  - `target_model`
  - `target_id`
  - `reason`
  - `old_value_json`
  - `new_value_json`
  - `ip_address`
  - `create_date`

Tambahan field yang disarankan:

- `reason_required`: boolean atau validasi helper per action.
- `request_uid`: user asli jika action memakai `sudo()`.
- `source`: backend, website, cron, webhook, shell.
- `amount`: Monetary opsional untuk payout/refund/fee.
- `currency_id`: currency untuk amount.
- `metadata_json`: payload ringkas tanpa credential/raw sensitive data.

## Acceptance Criteria

- Semua action kritis membuat audit log.
- Audit log hanya bisa dibaca admin.
- Audit log tidak bisa diedit user biasa.
- Admin bisa filter audit berdasarkan admin, action, target, tanggal.
- Moderation queue menampilkan kasus yang belum selesai.
