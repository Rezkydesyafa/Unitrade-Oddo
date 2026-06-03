# Manual Seller Payout Plan

Status: Draft
Priority: P2

## Tujuan

Payout seller dilakukan manual oleh admin pada MVP. Ini mengurangi risiko finansial sampai checkout, escrow, dan refund stabil.

## Status Saat Ini

- Seller dashboard menampilkan revenue.
- Belum ada rekening seller.
- Belum ada saldo tertahan/siap cair.
- Belum ada payout request/admin payout.

## Scope MVP

- Seller mengisi rekening bank.
- Sistem menghitung dana tertahan dan dana siap cair.
- Admin melihat daftar payout yang perlu dibayar.
- Admin menandai payout sudah dibayar manual.
- Sistem menyimpan bukti payout dan audit log.

## Data Model

Tambahan field di `unitrade.seller`:

- `x_bank_name`
- `x_bank_account_number`
- `x_bank_account_holder`
- `x_bank_verified`

Model baru:

- `unitrade.seller.payout`
  - `seller_id`
  - `amount`
  - `state`: draft, ready, paid, cancelled
  - `ledger_ids`
  - `bank_name`
  - `bank_account_number`
  - `bank_account_holder`
  - `paid_at`
  - `paid_by`
  - `payment_reference`
  - `proof_attachment_id`

## UI Seller

- Form rekening bank.
- Ringkasan saldo:
  - dana tertahan
  - siap dicairkan
  - sudah dicairkan
  - tertahan karena dispute
- Daftar riwayat payout.

## UI Admin

- Daftar payout siap dibayar.
- Detail rekening seller.
- Tombol `Tandai Sudah Dibayar`.
- Upload bukti transfer.
- Filter payout paid/pending.

## Acceptance Criteria

- Seller tidak bisa payout tanpa rekening.
- Order completed tanpa dispute masuk saldo siap cair.
- Order dispute/refund tidak masuk saldo siap cair.
- Admin bisa menandai payout paid.
- Ledger terkait payout tidak bisa dibayar dua kali.
- Seller melihat riwayat payout.

## Urutan Implementasi

1. Tambah data rekening seller.
2. Tambah escrow ledger state `releasable`.
3. Buat model payout.
4. Buat admin payout view.
5. Tambah seller payout summary.
6. Tambah audit log.
7. Test payout manual dan double-payment prevention.

