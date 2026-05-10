# Moderation and Audit Log Plan

Status: Draft
Priority: P1

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

## Acceptance Criteria

- Semua action kritis membuat audit log.
- Audit log hanya bisa dibaca admin.
- Audit log tidak bisa diedit user biasa.
- Admin bisa filter audit berdasarkan admin, action, target, tanggal.
- Moderation queue menampilkan kasus yang belum selesai.

