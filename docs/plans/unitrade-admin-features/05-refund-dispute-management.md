# Refund Dispute Management Plan

Status: Updated after source audit
Priority: P0
Last reviewed: 2026-05-18

## Update 2026-05-18

Refund/dispute sudah diimplementasikan sebagian lewat `unitrade_dispute`. Model `unitrade.dispute` sudah punya state `draft`, `submitted`, `under_review`, `need_buyer_evidence`, `need_seller_response`, `approved`, `rejected`, `resolved`, `cancelled`; relation ke order, order line, payment intent, escrow ledger, buyer, seller; amount; admin; decision note; dan evidence. Controller sudah menyediakan buyer refund form, upload photo/video terbatas, Google Drive validation, detail page, evidence download, dan seller response.

## Progress per 2026-05-24

- [x] Group gate `_check_admin()` di action: `start_review`, `need_buyer_evidence`, `need_seller_response`, `approve_refund`, `reject_refund`, `cancel`
- [x] Audit log call `unitrade.admin.audit.log` dari setiap aksi admin (info/warning sesuai severity)
- [x] **Evidence policy enforcement** di `action_approve_refund`: reason `damaged`/`not_as_described`/`wrong_item` wajib punya minimal 1 evidence (photo/unboxing video/packing video/Google Drive URL). Reason `seller_no_handoff` boleh tanpa physical evidence.
- [x] **`admin_decision_note` wajib** sebelum approve / reject (raise UserError kalau kosong)
- [x] **SLA fields**: `buyer_response_deadline_at`, `seller_response_deadline_at`, `decision_deadline_at`, computed `is_overdue` + search filter
- [x] Default SLA dari `ir.config_parameter`: `unitrade.refund.buyer_evidence_hours=48`, `unitrade.dispute_response_hours=48`, `unitrade.refund.decision_hours=72`
- [x] Auto-set deadline saat state berubah (`submitted` → decision deadline; `need_buyer_evidence` → buyer deadline; `need_seller_response` → seller deadline)
- [x] **Mail templates**: dispute submitted, need_buyer_evidence, need_seller_response, approved, rejected (dikirim ke buyer/seller email)
- [x] Form view: tab Timeline ditambah grup SLA / Deadline + indikator overdue
- [x] Search filter "Lewat SLA"
- [x] Tree view: kolom is_overdue + deadline (optional)
- [x] Task queue admin: grup baru "Refund Lewat SLA" untuk overdue cases
- [ ] Backend smart button dari dispute ke audit log (TBD setelah `unitrade_admin` audit log model dilengkapi search view)
- [ ] Cron job untuk auto-escalate overdue (mengirim reminder ke admin) — bisa ditambah nanti

Koreksi plan:

- Jangan membuat ulang `unitrade_dispute`; harden model dan view yang sudah ada.
- Evidence policy harus ditegakkan di model/action approve, bukan hanya di form website. Minimal validasi: refund reason tertentu wajib punya `unboxing_video` attachment atau Google Drive evidence yang ditandai sebagai unboxing.
- `admin_decision_note` harus wajib sebelum approve/reject.
- Tambah SLA field: `buyer_response_deadline_at`, `seller_response_deadline_at`, `decision_deadline_at`, dan overdue indicator.
- Tambah group gate di action admin seperti `action_approve_refund`, `action_reject_refund`, `action_need_buyer_evidence`, dan `action_need_seller_response`.
- Aksi approve/reject/cancel/request evidence harus masuk audit log.
- ACL perlu ditinjau ulang agar buyer/seller hanya memakai controller yang aman, sedangkan backend decision hanya untuk admin UniTrade/CS.

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

- Pakai modul existing `unitrade_dispute`.
- Tambah validasi model untuk evidence minimum dan decision note.
- Tambah SLA/deadline field dan search filter overdue.
- Tambah group gate di Python method action admin.
- Tambah smart button dari dispute ke order, escrow ledger, payment intent, seller, buyer, dan audit log.
- Integrasi ke audit log dan admin notification center.

## Acceptance Criteria

- Refund tidak bisa approved tanpa bukti minimum.
- Video unboxing wajib untuk refund.
- Video packing/link Google Drive wajib jika pengembalian diminta.
- Admin decision wajib catatan.
- Payout tertahan selama case aktif.
- Buyer dan seller menerima notifikasi status case.
