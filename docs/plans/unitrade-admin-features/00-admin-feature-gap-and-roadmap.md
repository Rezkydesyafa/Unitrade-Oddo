# Admin Feature Gap and Roadmap

Status: Updated after source audit
Last reviewed: 2026-05-24
Scope: Admin/back-office UniTrade

## Progress Fase 0 (per 2026-05-18)

- [x] Modul `unitrade_admin` dibuat sebagai layer orkestrasi
- [x] `unitrade.admin.audit.log` ada beserta helper `log_action`
- [x] ACL `unitrade_payment` diganti dari `sales_team.group_sale_manager` ke `unitrade_seller.group_unitrade_admin`
- [x] ACL `unitrade_dispute` ditambah row `unitrade_seller.group_unitrade_admin`
- [x] Menu `unitrade_payment` dipindah dari `sale.sale_menu_root` ke `unitrade_seller.menu_unitrade_root` dengan grup filter (`base.group_system,unitrade_seller.group_unitrade_admin`)
- [x] Menu Voucher, Refund/Dispute, dan Audit Log konsisten di bawah root UniTrade dan punya `groups` filter
- [x] Group gate di method `unitrade.dispute`: `action_start_review`, `action_need_buyer_evidence`, `action_need_seller_response`, `action_approve_refund`, `action_reject_refund`, `action_cancel`
- [x] Group gate di method `unitrade.escrow.ledger`: `action_mark_releasable`, `action_mark_released`, `action_create_xendit_payout`
- [x] Group gate di method `unitrade.seller`: `action_verify`, `action_reject`, `action_revoke_seller_verification`
- [x] Group gate di method `unitrade.seller.verification`: `action_approve`, `action_reject`
- [x] Audit log call dari setiap method admin di atas (lookup runtime via `self.env.registry`, no-op kalau `unitrade_admin` belum terinstall)
- [x] Audit log call dari `res.users.action_unitrade_block` dan `action_unitrade_unblock`
- [x] Audit log call dari `res.config.settings.set_values()` (deteksi field UniTrade yang berubah, redact secret)
- [x] Helper `unitrade_seller/models/unitrade_audit.py` (`log_admin_action`) sebagai bridge ke `unitrade_admin`

## Update 2026-05-24

- [x] Admin Notification Center MVP selesai: persistent admin inbox berbasis `unitrade.notification`, unread/read, priority, dedupe, topbar badge, halaman `/unitrade/admin/notifications`, backend menu, dan sync dari task queue.
- [ ] Sisa notification center: event hook langsung dari source record, lifecycle resolved task, dan assignment/ownership admin jika workflow CS dibagi.

## Ringkasan Audit Project Saat Ini

| Area | Status project saat ini | Koreksi plan |
| --- | --- | --- |
| Seller management | Ada list seller, pending seller, reported seller, approve/reject/revoke/reset, OCR result, payout destination | Jangan buat ulang. Tambah user management terpadu, global block, dan audit log |
| Seller verification | Ada `unitrade.seller.verification` dengan `manual_review` dan backend view | Task queue harus mengambil pending/manual review dari model ini dan `unitrade.seller` |
| Product management | Ada backend product marketplace, seller product website flow, stock field, publish/unpublish | Perlu status listing/fee eksplisit dan riwayat payment listing fee |
| Listing fee | Ada `unitrade.payment.intent` `intent_type = listing_fee`, publish after paid, fee config sederhana | Plan tier persentase lama belum sesuai source. Putuskan tetap fixed fee config atau migrate ke tier model |
| Payment monitoring | Ada payment intent, payment event, sale order payment fields, Midtrans, Xendit legacy | Perlu menu/admin role konsisten, search escrow, smart buttons, dan transaction issue flag |
| Escrow ledger | Ada `unitrade.escrow.ledger` dengan held/releasable/released/disputed/refunded/cancelled dan bukti serah terima | Bukan gap model lagi. Gap-nya adalah operation dashboard, payout control, audit, dan reports |
| Refund/dispute | Ada `unitrade.dispute`, `unitrade.dispute.evidence`, backend view, buyer form, seller response | Perlu validasi evidence sebelum approve, SLA, decision note wajib, group gate, dan audit |
| Payout | Ada rekening/channel payout di seller dan field payout di escrow ledger | Belum ada batch/manual payout model dengan bukti transfer dan double-payment guard |
| Notification | Ada `unitrade.notification` user-centric + admin inbox MVP | Sisa event hook langsung, resolved lifecycle, dan assignment/ownership jika dibutuhkan |
| Audit | Ada `unitrade.security.activity` untuk aktivitas akun | Belum ada audit log admin lintas modul |

## Gap Utama Setelah Audit

| Prioritas | Gap | Dampak |
| --- | --- | --- |
| P0 | ACL/menu admin belum konsisten memakai `unitrade_seller.group_unitrade_admin` | Admin UniTrade bisa kehilangan akses ke modul payment/dispute, atau akses diberikan terlalu luas ke role Odoo lain |
| P0 | Public action kritis belum semuanya punya group gate di method | Tombol view tersembunyi belum cukup karena method publik bisa dipanggil via RPC |
| P0 | Tidak ada admin dashboard terpadu | Admin harus membuka banyak menu untuk tahu kondisi platform |
| P0 | Tidak ada task queue lintas modul | Pending KTM, listing fee, refund, payout, dan transaksi terlambat tidak terkumpul |
| P0 | Product/listing fee belum punya status operasional eksplisit | Admin sulit membedakan draft, fee pending, paid, waived, rejected, dan expired |
| P0 | Refund/dispute approval belum cukup ketat | Refund bisa diproses tanpa checklist evidence, SLA, dan catatan keputusan yang kuat |
| P0 | Manual payout workflow belum ada | Seller payout manual belum punya batch, bukti transfer, guard double-payment, dan audit |
| P1 | Laporan dan export belum lengkap | Sulit mengevaluasi GMV, transaksi, user, produk, refund, payout |
| P1 | System settings UI belum ada | Runtime config masih tersebar di XML/system parameters |
| P1 | Audit log belum lintas modul | Aksi admin sulit dilacak |
| P2 | Admin notification center baru MVP | Perlu event hook langsung dan lifecycle resolved agar tidak hanya sinkron dari task queue |

## Roadmap

### Fase 0: Admin Foundation dan Security Convergence

- Buat modul `unitrade_admin` sebagai layer orkestrasi.
- Satukan menu admin payment/dispute/report/settings di bawah root `UniTrade`.
- Update action/menu/model ACL agar admin UniTrade memakai `unitrade_seller.group_unitrade_admin`.
- Tambah `unitrade.admin.audit.log` dan helper pencatatan action kritis.
- Tambah group gate di method action kritis: refund approve/reject, payout release, waive fee, revoke seller, block user, dan settings update.

### Fase 1: Visibility dan Control

- Admin dashboard.
- Task queue.
- User/seller management.
- Product/listing fee management.

### Fase 2: Transaction Operations

- Transaction monitoring yang menggabungkan sale order, payment intent, payment event, escrow ledger, dispute.
- Escrow operation queue.
- Refund/dispute management hardening.
- Manual payout management.

### Fase 3: Governance

- Reports/export.
- System settings.
- Moderation/audit log.
- Admin notification center.

## Definisi Done Global

- Semua menu admin hanya bisa diakses admin UniTrade.
- Semua action kritis punya pengecekan group di Python method, bukan hanya di XML button.
- Semua list punya filter status dan tanggal.
- Semua action penting meminta alasan jika berdampak ke user/seller/uang.
- Semua action kritis tercatat di audit log.
- Semua angka uang tampil sebagai Rupiah tanpa desimal.
- Setting operasional bisa diubah dari UI admin dan tersimpan di `ir.config_parameter`.
- Dashboard/task/report menggunakan model existing; tidak menduplikasi ledger/payment/dispute.
