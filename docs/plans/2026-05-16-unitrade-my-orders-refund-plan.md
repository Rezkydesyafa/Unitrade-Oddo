# Plan Fitur Refund di Halaman Pesanan Saya

Status: Draft
Priority: P0
Tanggal: 2026-05-16

## Ringkasan

Fitur refund dibuat sebagai jalur resmi buyer untuk mengajukan pengembalian dana dari halaman **Pesanan Saya**. Refund hanya berlaku untuk transaksi yang checkout dan dibayar melalui UniTrade. Transaksi chat atau transaksi luar website tidak dilindungi refund.

Flow pembayaran tetap memakai Midtrans sebagai payment gateway, sedangkan refund MVP ditangani sebagai **dispute internal UniTrade**. Dana buyer yang sudah masuk tetap dicatat di escrow ledger. Saat refund diajukan, payout seller ditahan sampai admin/CS memutuskan refund diterima atau ditolak.

## Prinsip Flow

```text
Buyer bayar via Midtrans
        |
Webhook Midtrans paid valid
        |
Order = Di Proses
Escrow ledger = Held
        |
Buyer ajukan refund dari Pesanan Saya
        |
Refund case = Submitted / Under Review
Escrow ledger = Disputed
Payout seller tertahan
        |
Admin/CS review bukti buyer dan seller
        |
Approve refund -> order refunded, escrow refunded
Reject refund -> order kembali Di Proses, escrow held
```

## Scope MVP

- Tambah tombol **Ajukan Refund** di card/detail **Pesanan Saya**.
- Refund hanya tersedia untuk order yang sudah paid dan belum selesai.
- Refund tidak tersedia untuk order **Belum dibayar**. Untuk order belum dibayar, buyer memakai tombol **Batalkan** selama 30 menit.
- Buyer wajib memilih alasan refund.
- Buyer wajib upload bukti minimal satu foto/video.
- Untuk alasan barang tidak sesuai atau rusak, video unboxing wajib.
- Seller dapat melihat refund case di dashboard penjual dan mengirim respons/bukti.
- Admin/CS dapat approve atau reject refund.
- Refund aktif menahan payout seller.
- Refund decision tersimpan untuk audit.

## Eligibility Refund

Refund bisa diajukan jika semua kondisi ini terpenuhi:

- `sale.order.x_payment_status == 'paid'`
- `sale.order.x_unitrade_order_state == 'processing'`
- `sale.order.x_escrow_state in ('held', 'disputed')`
- Order belum `completed`, `cancelled`, atau `refunded`
- Belum ada refund case aktif untuk order/seller yang sama
- Seller belum menerima payout

Refund tidak ditampilkan jika:

- Order masih `payment_pending` atau `Belum dibayar`
- Payment expired, failed, atau cancelled
- Buyer sudah klik **Barang Diterima** dan order sudah selesai
- Ledger sudah `released`

Catatan: setelah order completed, refund MVP tidak dibuka dari UI buyer. Jika perlu pengecualian, admin bisa membuat case manual dari backend.

## UI Pesanan Saya

Pada card order:

- Status `Belum dibayar`
  - Tampilkan tombol **Batalkan** jika masih dalam window 30 menit.
  - Jangan tampilkan tombol refund.

- Status `Di Proses`
  - Tampilkan **Ajukan Refund** jika eligible.
  - Jika refund case aktif, tampilkan badge **Refund Diproses** dan tombol **Lihat Refund**.
  - Tombol **Konfirmasi Barang** tetap mengikuti aturan sekarang: aktif setelah seller upload bukti.

- Status `Selesai`
  - Jangan tampilkan refund pada MVP.
  - Tampilkan **Beri Ulasan** dan **Beli Lagi** seperti flow yang sudah ada.

Detail order internal perlu menambah panel ringkas:

- Status refund.
- Alasan refund.
- Waktu pengajuan.
- Bukti yang sudah diunggah.
- Catatan keputusan admin jika sudah ada.

## Form Refund Buyer

Form muncul sebagai modal atau halaman detail:

- Alasan refund:
  - Seller tidak menyerahkan barang.
  - Barang tidak sesuai deskripsi.
  - Barang rusak/tidak berfungsi.
  - Salah barang.
  - Lainnya.
- Catatan buyer.
- Requested amount, default full subtotal seller.
- Upload bukti:
  - Foto barang.
  - Video unboxing jika alasan barang tidak sesuai/rusak/salah barang.
  - Link Google Drive opsional untuk file besar.

Validasi:

- Catatan minimal 20 karakter.
- Minimal satu bukti wajib.
- Video unboxing wajib untuk kategori alasan tertentu.
- File size mengikuti limit konfigurasi `unitrade.refund.max_upload_mb`.

## Data Model

Buat modul baru `unitrade_dispute` agar refund tidak menumpuk di `unitrade_payment`.

Model `unitrade.dispute`:

- `name`
- `dispute_type`: `refund`
- `state`: `draft`, `submitted`, `under_review`, `need_buyer_evidence`, `need_seller_response`, `approved`, `rejected`, `resolved`, `cancelled`
- `order_id`
- `order_line_id`
- `payment_intent_id`
- `escrow_ledger_id`
- `buyer_id`
- `seller_id`
- `reason_code`
- `reason_note`
- `requested_amount`
- `approved_amount`
- `currency_id`
- `admin_id`
- `admin_decision_note`
- `submitted_at`
- `review_started_at`
- `approved_at`
- `rejected_at`
- `resolved_at`

Model `unitrade.dispute.evidence`:

- `dispute_id`
- `submitted_by_id`
- `evidence_type`: `buyer_photo`, `unboxing_video`, `packing_video`, `seller_response`, `google_drive_url`, `other`
- `attachment_id`
- `url`
- `note`
- `created_at`

Tambahan pada `sale.order`:

- `x_refund_dispute_id`
- `x_refund_state`
- `x_refunded_at`

Tambahan pada `unitrade.escrow.ledger`:

- Gunakan state existing `disputed` dan `refunded`.
- Tambah relasi optional `refund_dispute_id`.

## Backend Flow

Endpoint buyer:

- `POST /unitrade/order/<order_id>/refund`
  - Membuat refund case.
  - Validasi ownership buyer.
  - Validasi refund eligibility.
  - Upload evidence ke `ir.attachment`.
  - Set ledger `disputed`.
  - Set order `x_escrow_state = disputed`.

- `GET /unitrade/order/<order_id>/refund/<dispute_id>`
  - Menampilkan detail refund case untuk buyer.

Endpoint seller:

- `POST /seller/refund/<dispute_id>/respond`
  - Seller upload bukti respons.
  - Validasi seller adalah pemilik ledger/order line.

Backend admin:

- Menu **Refund & Dispute**.
- Action **Start Review**.
- Action **Request Buyer Evidence**.
- Action **Request Seller Response**.
- Action **Approve Refund**.
- Action **Reject Refund**.

## Keputusan Admin

Approve refund:

- `unitrade.dispute.state = approved/resolved`
- `sale.order.x_payment_status = refunded`
- `sale.order.x_unitrade_order_state = refunded` jika field state ditambah
- `sale.order.x_escrow_state = refunded`
- `unitrade.escrow.ledger.state = refunded`
- Payment intent `state = refunded`
- Payout seller tetap tidak dibuat.

Reject refund:

- `unitrade.dispute.state = rejected/resolved`
- `unitrade.escrow.ledger.state = held`
- `sale.order.x_escrow_state = held`
- Order kembali tampil **Di Proses**.
- Buyer masih bisa konfirmasi barang jika seller sudah upload bukti.

Catatan Midtrans:

- MVP tidak langsung call API refund Midtrans dari buyer.
- Admin melakukan refund manual terlebih dahulu atau integrasi Midtrans refund/disbursement di fase berikutnya.
- Jika integrasi Midtrans refund ditambahkan, admin action approve refund harus idempotent dan menyimpan response gateway.

## Notifikasi

Event yang perlu notifikasi:

- Buyer mengajukan refund.
- Seller mendapat refund case baru.
- Admin meminta bukti tambahan.
- Seller mengirim respons.
- Refund diterima.
- Refund ditolak.

Channel MVP:

- Notification center internal jika sudah tersedia.
- Email template opsional.

## Security

- Buyer hanya bisa membuat dan melihat refund untuk order miliknya.
- Seller hanya bisa melihat dispute yang terkait seller ledger/order line miliknya.
- Admin/CS bisa melihat semua case.
- Evidence attachment wajib memakai access token atau record rule.
- Jangan gunakan `sudo()` untuk akses evidence publik kecuali setelah validasi role.

## Acceptance Criteria

- Buyer melihat tombol **Ajukan Refund** hanya pada order paid/processing yang eligible.
- Buyer tidak melihat refund di order belum dibayar.
- Buyer tidak bisa submit refund tanpa bukti.
- Video unboxing wajib untuk alasan barang rusak/tidak sesuai/salah barang.
- Submit refund mengubah escrow ledger menjadi `disputed`.
- Refund aktif menahan payout seller.
- Seller dapat memberi respons dan upload bukti.
- Admin dapat approve/reject refund.
- Approve refund membuat order/ledger/payment intent masuk status refunded.
- Reject refund mengembalikan order ke status Di Proses.
- Duplicate submit refund untuk order/seller yang sama ditolak.

## Test Plan

- Order belum dibayar: tombol refund tidak muncul, tombol cancel 30 menit tetap muncul.
- Order paid/processing: tombol refund muncul.
- Submit refund tanpa evidence: ditolak.
- Submit refund alasan rusak tanpa video unboxing: ditolak.
- Submit refund valid: case dibuat, ledger menjadi disputed.
- Seller respond dengan bukti: evidence tersimpan.
- Admin approve: ledger refunded, payout tertahan, order tidak bisa diselesaikan.
- Admin reject: ledger held, order tetap processing.
- Buyer lain tidak bisa membuka refund case.
- Seller lain tidak bisa membuka refund case.
- Duplicate refund case aktif ditolak.

## Urutan Implementasi

1. Buat modul `unitrade_dispute`.
2. Tambah model `unitrade.dispute` dan `unitrade.dispute.evidence`.
3. Tambah ACL dan record rules.
4. Tambah helper refund eligibility di `sale.order` atau service layer.
5. Tambah tombol dan modal/form refund di **Pesanan Saya**.
6. Tambah endpoint buyer refund.
7. Tambah dashboard/admin views refund.
8. Tambah seller response di dashboard penjual.
9. Hubungkan refund state ke escrow ledger dan payout blocking.
10. Tambah notifikasi dan email dasar.
11. Tambah test controller, security, dan state transition.

## Out of Scope MVP

- Refund otomatis langsung via Midtrans API.
- Refund parsial multi-item kompleks.
- Auto SLA decision.
- Integrasi Google Drive API. MVP cukup simpan link Google Drive.
- Refund setelah order completed dari UI buyer.
