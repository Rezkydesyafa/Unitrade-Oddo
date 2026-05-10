# Admin Feature Gap and Roadmap

Status: Draft
Scope: Admin/back-office UniTrade

## Fitur Admin yang Sudah Ada Sebagian

| Area | Status project saat ini |
| --- | --- |
| Seller management | Ada list seller, pending seller, reported seller, approve/reject/revoke |
| Seller verification | Ada model dan view verifikasi KTM |
| Product management | Ada backend product marketplace untuk admin |
| Payment monitoring | Ada field status pembayaran di sale order |
| Delivery management | Ada backend delivery view |
| Review management | Ada backend review view |
| Chat moderation | Ada laporan chat dan action block/unblock |

## Gap Utama

| Prioritas | Gap | Dampak |
| --- | --- | --- |
| P0 | Tidak ada admin dashboard terpadu | Admin harus membuka banyak menu untuk tahu kondisi platform |
| P0 | Tidak ada task queue | Pending KTM, refund, payout, dan transaksi terlambat tidak terkumpul |
| P0 | Tidak ada fee upload management | Produk berbayar sebelum publish belum bisa diawasi |
| P0 | Tidak ada escrow ledger admin | Dana tertahan, siap cair, dan refund tidak bisa diaudit |
| P0 | Tidak ada refund/dispute dashboard | Klaim refund dengan video unboxing belum bisa diproses |
| P0 | Tidak ada manual payout workflow | Seller payout manual belum punya kontrol dan bukti |
| P1 | Laporan dan export belum lengkap | Sulit mengevaluasi GMV, transaksi, user, produk, refund |
| P1 | System settings belum lengkap | Tarif fee dan SLA masih akan rawan hardcode |
| P1 | Audit log belum lintas modul | Aksi admin sulit dilacak |
| P2 | Admin notification center belum ada | Admin bisa melewatkan pekerjaan urgent |

## Roadmap

### Fase 1: Visibility dan Control

- Admin dashboard.
- Task queue.
- User/seller management.
- Product/listing fee management.

### Fase 2: Transaction Operations

- Transaction monitoring.
- Escrow ledger.
- Refund/dispute management.
- Manual payout management.

### Fase 3: Governance

- Reports/export.
- System settings.
- Moderation/audit log.
- Admin notification center.

## Definisi Done Global

- Semua menu admin hanya bisa diakses admin UniTrade.
- Semua list punya filter status dan tanggal.
- Semua action penting meminta alasan jika berdampak ke user/seller.
- Semua action kritis tercatat di audit log.
- Semua angka uang tampil sebagai Rupiah tanpa desimal.

