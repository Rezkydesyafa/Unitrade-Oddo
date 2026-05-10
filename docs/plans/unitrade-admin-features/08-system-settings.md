# System Settings Plan

Status: Draft
Priority: P1

## Tujuan

Admin dapat mengatur konfigurasi utama platform tanpa edit kode.

## Setting yang Dibutuhkan

Fee upload produk:

- Tier harga.
- Persentase fee.
- Pembulatan fee.
- Aktif/nonaktif fee.

Checkout dan escrow:

- Cancel window: default 10 menit.
- Auto complete setelah seller upload bukti: default 24 jam.
- Batas waktu refund request.
- Batas waktu respons buyer/seller pada dispute.

Payout:

- Mode payout: manual.
- Minimum payout jika diperlukan.
- Instruksi rekening/payout.

Legal/policy:

- Link syarat transaksi luar website.
- Link kebijakan refund.
- Template copy label proteksi.

Integrasi:

- Midtrans server/client key.
- Mapbox token.
- GoSend credential jika nanti aktif.

## Perubahan Odoo

- Extend `res.config.settings`.
- Simpan value di `ir.config_parameter`.
- Buat menu `UniTrade > Pengaturan Sistem`.
- Tambah access hanya untuk admin.

## Acceptance Criteria

- Admin dapat mengubah tier fee dari UI.
- Admin dapat mengubah cancel window dan auto complete window.
- Credential tidak hardcoded.
- Setting punya default value aman.
- Perubahan setting tercatat di audit log jika kritis.

