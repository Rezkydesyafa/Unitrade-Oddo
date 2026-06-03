# Refund Dispute Evidence Plan

Status: Draft
Priority: P1

## Tujuan

Refund hanya berlaku untuk checkout website. Buyer wajib menyertakan video unboxing. Jika barang harus dikembalikan, buyer wajib menyertakan video packing dan link folder Google Drive.

## Status Saat Ini

- Review order sudah ada.
- Report chat/seller sudah ada.
- Belum ada refund/dispute order.
- Belum ada upload video unboxing.
- Belum ada flow CS refund.

## Scope MVP

- Buyer mengajukan refund dari detail pesanan.
- Form refund wajib video unboxing.
- Form menerima foto pendukung.
- CS dapat meminta video packing dan link Google Drive.
- Seller dapat diminta memberi respons.
- CS approve/reject refund.
- Refund aktif menahan payout.

## Data Model

Model baru:

- `unitrade.dispute`
  - `dispute_type`: refund
  - `order_id`
  - `order_line_id`
  - `buyer_id`
  - `seller_id`
  - `reason`
  - `requested_amount`
  - `approved_amount`
  - `state`
  - `admin_decision_note`
  - `deadline_buyer_response_at`
  - `deadline_seller_response_at`

- `unitrade.dispute.evidence`
  - `dispute_id`
  - `evidence_type`: unboxing_video, packing_video, photo, google_drive_url, seller_response
  - `attachment_id`
  - `url`
  - `note`

## Status Dispute

- `submitted`
- `under_review`
- `need_buyer_evidence`
- `need_seller_response`
- `approved`
- `rejected`
- `resolved`

## Kebijakan Evidence

- Video unboxing wajib untuk klaim refund.
- Video unboxing harus memperlihatkan paket sebelum dibuka.
- Video tidak boleh terpotong atau diedit.
- Jika pengembalian wajib, video packing wajib.
- Link Google Drive wajib dapat diakses CS.
- CS dapat menolak klaim jika bukti tidak lengkap.

## Acceptance Criteria

- Buyer tidak bisa submit refund tanpa video unboxing.
- Buyer bisa submit link Google Drive saat diminta pengembalian.
- Dispute aktif menahan payout seller.
- CS bisa approve/reject refund.
- Seller melihat dispute terkait ordernya.
- Semua evidence tersimpan dan bisa diaudit.

## Urutan Implementasi

1. Buat modul `unitrade_dispute`.
2. Buat model dispute dan evidence.
3. Buat form refund buyer.
4. Tambah upload attachment/video.
5. Tambah dashboard CS.
6. Tambah seller response view.
7. Hubungkan status dispute ke escrow/payout.
8. Tambah legal policy refund.

