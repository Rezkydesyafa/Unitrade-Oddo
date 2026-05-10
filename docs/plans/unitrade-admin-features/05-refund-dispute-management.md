# Refund Dispute Management Plan

Status: Draft
Priority: P0

## Tujuan

Admin/CS dapat memproses refund dan banding berdasarkan bukti: video unboxing, video packing, link Google Drive, chat, dan bukti seller.

## Scope MVP

- Daftar refund/dispute.
- Detail case.
- Bukti buyer.
- Bukti seller.
- Link Google Drive.
- Status review.
- Minta bukti tambahan.
- Approve/reject refund.
- Catatan keputusan admin.
- Hold escrow/payout selama case aktif.

## Status Case

- Submitted.
- Under review.
- Need buyer evidence.
- Need seller response.
- Approved.
- Rejected.
- Resolved.

## Data yang Ditampilkan

- ID case.
- Order.
- Buyer.
- Seller.
- Produk.
- Alasan.
- Requested amount.
- Evidence status.
- SLA response.
- Admin assignee.
- Keputusan.

## Action Admin

- Assign ke CS.
- Mulai review.
- Minta bukti buyer.
- Minta respons seller.
- Approve refund.
- Reject refund.
- Tutup case.

## Perubahan Odoo

- Modul baru `unitrade_dispute`.
- Model `unitrade.dispute`.
- Model `unitrade.dispute.evidence`.
- Backend views untuk CS/admin.
- Integrasi ke escrow agar payout tertahan.

## Acceptance Criteria

- Refund tidak bisa approved tanpa bukti minimum.
- Video unboxing wajib untuk refund.
- Video packing/link Google Drive wajib jika pengembalian diminta.
- Admin decision wajib catatan.
- Payout tertahan selama case aktif.
- Buyer dan seller menerima notifikasi status case.

