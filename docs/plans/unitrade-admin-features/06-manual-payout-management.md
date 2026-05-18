# Manual Payout Management Plan

Status: Updated after source audit
Priority: P0
Last reviewed: 2026-05-18

## Update 2026-05-18

Payout sudah ada sebagian di level data, tetapi belum cukup untuk MVP payout manual. `unitrade.seller` sudah menyimpan tujuan payout (`x_payout_channel_code`, `x_payout_account_number`, `x_payout_account_name`, `x_payout_ready`, `x_payout_note`). `unitrade.escrow.ledger` sudah punya `amount_seller`, `state = releasable/released`, `payout_reference`, `payout_status`, `payout_requested_at`, `payout_completed_at`, `payout_failure_reason`, dan action mark released manual. Xendit payout action masih tersembunyi sebagai legacy.

Gap yang harus ditutup:

- Belum ada model batch payout manual.
- Belum ada upload bukti transfer.
- Belum ada guard yang jelas untuk mencegah ledger dibayar dua kali dalam batch berbeda.
- Belum ada review queue payout siap cair.
- Belum ada audit event untuk create payout, mark paid, cancel payout, dan remove ledger.

Rekomendasi MVP tetap membuat model `unitrade.seller.payout`, tetapi gunakan `unitrade.escrow.ledger` sebagai sumber dana. Jangan langsung mengaktifkan Xendit payout legacy sebelum rekonsiliasi manual stabil.

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

- Pakai data payout existing di `unitrade.seller`; tambahkan field hanya jika perlu verifikasi rekening.
- Model `unitrade.seller.payout`.
- Hubungkan payout ke `unitrade.escrow.ledger`.
- Tambah admin action untuk mark paid.
- Simpan bukti transfer sebagai attachment.
- Tambah unique/constraint agar ledger yang sudah masuk payout paid tidak bisa dipakai ulang.
- Tambah audit log dan admin notification untuk payout ready/paid/failed.

## Acceptance Criteria

- Admin tidak bisa payout ledger yang masih dispute.
- Admin tidak bisa membayar ledger yang sudah paid.
- Mark paid wajib payment reference atau bukti transfer.
- Seller menerima notifikasi setelah payout paid.
- Semua payout tercatat di audit log.
