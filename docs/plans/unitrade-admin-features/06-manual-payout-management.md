# Manual Payout Management Plan

Status: Draft
Priority: P0

## Tujuan

Admin dapat mencairkan dana seller secara manual dengan kontrol, bukti transfer, dan audit log.

## Scope MVP

- Daftar dana seller siap payout.
- Detail seller dan rekening.
- Detail ledger yang masuk payout.
- Buat payout batch/manual.
- Upload bukti transfer.
- Tandai payout paid.
- Riwayat payout.

## Data yang Ditampilkan

- Seller.
- Bank.
- Nomor rekening.
- Nama pemilik rekening.
- Total dana siap cair.
- Dana tertahan.
- Dana dispute.
- Jumlah transaksi completed.
- Last payout date.

## Status Payout

- Draft.
- Ready.
- Paid.
- Cancelled.

## Perubahan Odoo

- Tambah data rekening di `unitrade.seller`.
- Model `unitrade.seller.payout`.
- Hubungkan payout ke `unitrade.escrow.ledger`.
- Tambah admin action untuk mark paid.
- Simpan bukti transfer sebagai attachment.

## Acceptance Criteria

- Admin tidak bisa payout ledger yang masih dispute.
- Admin tidak bisa membayar ledger yang sudah paid.
- Mark paid wajib payment reference atau bukti transfer.
- Seller menerima notifikasi setelah payout paid.
- Semua payout tercatat di audit log.

