# Cancel Window and Appeal Plan

Status: Draft
Priority: P1

## Tujuan

Buyer dapat membatalkan pesanan langsung maksimal 20 menit setelah checkout. Setelah 20 menit, atau jika seller sudah mengonfirmasi serah barang, pembatalan harus melalui banding.

## Status Saat Ini

- Halaman pesanan user ada.
- Belum ada tombol cancel langsung.
- Belum ada banding cancel.
- Belum ada status dispute order.

## Aturan Produk

- Cancel langsung hanya berlaku sampai 20 menit setelah checkout.
- Cancel langsung hanya berlaku jika seller belum mengonfirmasi serah barang.
- Setelah 20 menit, buyer harus mengajukan banding.
- Jika dispute aktif, payout seller tertahan.

## Data Model

Tambahan field di `sale.order`:

- `x_cancel_deadline_at`
- `x_cancelled_by`
- `x_cancelled_at`
- `x_cancel_reason`
- `x_dispute_id`

Model dispute dapat digunakan untuk banding:

- `unitrade.dispute`
  - `dispute_type`: cancel_appeal, refund
  - `order_id`
  - `buyer_id`
  - `seller_id`
  - `reason`
  - `state`

## UI Buyer

- Detail pesanan menampilkan countdown cancel jika masih <= 20 menit.
- Tombol `Batalkan Pesanan` muncul jika eligible.
- Jika tidak eligible, tampilkan tombol `Ajukan Banding`.
- Form banding meminta alasan dan bukti pendukung.

## UI Admin/CS

- Daftar banding masuk.
- Detail banding.
- Approve cancel.
- Reject cancel.
- Minta bukti tambahan.

## Acceptance Criteria

- Buyer bisa cancel langsung sebelum deadline.
- Buyer tidak bisa cancel langsung setelah 20 menit.
- Buyer tidak bisa cancel langsung jika seller sudah mengonfirmasi serah barang.
- Setelah 20 menit, buyer diarahkan ke form banding.
- Banding aktif menahan payout dan auto complete.
- Admin dapat approve/reject banding.

## Urutan Implementasi

1. Tambah cancel deadline saat payment checkout sukses.
2. Tambah eligibility helper di `sale.order`.
3. Tambah tombol cancel di halaman pesanan.
4. Tambah endpoint cancel langsung.
5. Tambah form banding.
6. Tambah dashboard CS untuk banding.
7. Hubungkan dispute aktif ke escrow/payout hold.
