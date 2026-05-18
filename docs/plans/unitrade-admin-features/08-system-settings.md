# System Settings Plan

Status: Updated after source audit
Priority: P1
Last reviewed: 2026-05-18

## Update 2026-05-18

Runtime config sudah tersebar di beberapa XML data dan `ir.config_parameter`, tetapi belum ada UI admin khusus. Settings yang harus diekspos mengikuti source sekarang:

| Key | Nilai source/default | Keterangan |
| --- | ---: | --- |
| `unitrade.seller.listing_fee.threshold` | 1000000 | Ambang fixed listing fee |
| `unitrade.seller.listing_fee.low_amount` | 2000 | Fee produk di bawah/sama threshold |
| `unitrade.seller.listing_fee.high_amount` | 5000 | Fee produk di atas threshold |
| `unitrade.seller.posting_admin_fee` | 0 | Admin fee tambahan posting produk |
| `unitrade.order.cancel_window_minutes` | 30 | Window cancel langsung, berbeda dari asumsi lama 10 menit |
| `unitrade.midtrans.payment_expiry_minutes` | 30 | Expiry payment Midtrans |
| `unitrade.xendit.payment_expiry_minutes` | 30 | Expiry payment Xendit legacy |
| `unitrade.escrow.auto_confirm_receipt_hours` | 48 default code | Auto confirm buyer receipt, berbeda dari asumsi lama 24 jam |
| `unitrade.refund.max_upload_mb` | 25 | Batas upload evidence refund umum |

Koreksi plan:

- Jangan menulis default 10 menit/24 jam sebagai fakta project. Tuliskan sebagai opsi product decision jika ingin diubah.
- Credential/payment key tetap di `ir.config_parameter`, tetapi UI harus membedakan secret value, operational setting, dan public copy/policy.
- Perubahan critical settings harus masuk audit log.

## Tujuan

Admin dapat mengatur konfigurasi utama platform tanpa edit kode.

## Setting yang Dibutuhkan

Fee upload produk:

- Threshold harga.
- Low/high fixed fee atau tier persentase jika product decision berubah.
- Posting admin fee.
- Aktif/nonaktif fee.

Checkout dan escrow:

- Cancel window: source saat ini 30 menit.
- Auto confirm buyer receipt setelah seller upload bukti: source saat ini 48 jam default code.
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
- Xendit secret key jika legacy payment/payout masih dipakai.
- Mapbox token.
- GoSend credential jika nanti aktif.

## Perubahan Odoo

- Extend `res.config.settings`.
- Simpan value di `ir.config_parameter`.
- Buat menu `UniTrade > Pengaturan Sistem`.
- Tambah access hanya untuk admin.

## Acceptance Criteria

- Admin dapat mengubah config fee upload produk dari UI.
- Admin dapat mengubah cancel window dan auto complete window.
- Credential tidak hardcoded.
- Setting punya default value aman.
- Perubahan setting tercatat di audit log jika kritis.
