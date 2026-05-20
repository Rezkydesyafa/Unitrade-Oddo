# Requirements Document — UniTrade Notification System

## Introduction

Fitur ini menyempurnakan modul `unitrade_notification` yang sudah ada di marketplace UniTrade (Odoo 17, target mahasiswa  Yogyakarta). Saat ini modul tersebut hanya punya model dasar `unitrade.notification` dengan lima tipe (order, payment, delivery, chat, system), satu mail template untuk konfirmasi pesanan, dan belum punya notification center, preferensi user, atau cakupan event yang lengkap.

Sistem yang akan dibangun menyediakan satu pusat notifikasi sederhana (in-app + email) untuk event penting di UniTrade: akun, seller, pesanan, pembayaran, chat, review, dan pengumuman sistem. User dapat membaca, menandai dibaca, menghapus, memfilter, dan mengatur preferensi on/off per kategori. UI mengikuti konvensi UniTrade (Tailwind CSS prefix `tw-`, OWL/QWeb, palet warna `unitrade_theme`).

Scope sengaja dijaga ringkas: dua channel (in-app & email), preferensi sederhana per kategori, polling badge counter (tanpa bus.bus dulu), dan template email untuk event yang belum tercover.

## Glossary

- **Notification_System**: Modul `unitrade_notification` (model `unitrade.notification`, dispatcher, UI center, preferensi).
- **Notification_Record**: Satu baris `unitrade.notification` untuk satu user pada satu event.
- **Notification_Category**: Kategori event: `account`, `seller`, `order`, `payment`, `chat`, `review`, `system`.
- **Notification_Event_Code**: String stabil pengidentifikasi event (mis. `order.confirmed`, `payment.success`).
- **Notification_Channel**: `in_app` atau `email`.
- **Notification_Preference**: Record `unitrade.notification.preference` per (`user_id`, `category`, `channel`) dengan `enabled` boolean.
- **Notification_Dispatcher**: Method `emit(user_id, event_code, payload)` pada `unitrade.notification` yang membuat record dan mengirim email sesuai preferensi.
- **Notification_Center**: Halaman `/my/notifications` berisi daftar notifikasi user.
- **Notification_Bell**: Komponen ikon lonceng di navbar dengan badge unread.
- **Idempotency_Key**: Kunci unik per (`user_id`, `event_code`, `reference_model`, `reference_id`) untuk mencegah duplikasi.
- **Unread_Counter**: Jumlah `Notification_Record` user dengan `is_read=False`.
- **Buyer**: User terdaftar yang membeli.
- **Seller**: User dengan status seller terverifikasi.
- **Admin**: User di grup `unitrade_seller.group_unitrade_admin`.

## Requirements

### Requirement 1: Model Notifikasi Inti

**User Story:** Sebagai sistem UniTrade, saya butuh struktur data notifikasi yang lengkap, sehingga setiap event penting dapat dicatat dan ditampilkan ke user tanpa duplikasi.

#### Acceptance Criteria

1. THE Notification_System SHALL memperluas model `unitrade.notification` dengan field minimal: `user_id`, `title`, `message`, `category`, `event_code`, `reference_model`, `reference_id`, `action_url`, `is_read`, `read_at`, `idempotency_key`, `email_state`, `create_date`.
2. THE Notification_System SHALL menyediakan field `category` Selection berisi: `account`, `seller`, `order`, `payment`, `chat`, `review`, `system`.
3. THE Notification_System SHALL menyediakan field `email_state` Selection bernilai salah satu dari `not_applicable`, `pending`, `sent`, `failed`.
4. THE Notification_System SHALL membuat unique index pada (`user_id`, `idempotency_key`) untuk mencegah duplikasi.
5. WHEN modul lain memanggil `unitrade.notification.emit(user_id, event_code, payload)`, THE Notification_Dispatcher SHALL membuat satu `Notification_Record` jika `idempotency_key` belum ada untuk user tersebut.
6. IF `idempotency_key` sudah ada untuk user tersebut, THEN THE Notification_Dispatcher SHALL mengembalikan record yang sudah ada tanpa membuat record baru.
7. THE Notification_System SHALL mempertahankan field lama `notification_type` untuk backward compatibility, dengan auto-mapping dari `category` saat record dibuat.
8. THE Notification_System SHALL mendaftarkan akses pada `security/ir.model.access.csv` untuk grup `base.group_user` (read/write own) dan `unitrade_seller.group_unitrade_admin` (full).

### Requirement 2: Preferensi Notifikasi User

**User Story:** Sebagai user UniTrade, saya ingin bisa mematikan kategori notifikasi yang tidak relevan, sehingga saya tidak terganggu.

#### Acceptance Criteria

1. THE Notification_System SHALL menyediakan model `unitrade.notification.preference` dengan field `user_id`, `category`, `channel`, `enabled`.
2. WHEN user pertama kali membuka halaman pengaturan notifikasi, THE Notification_System SHALL membuat preferensi default `enabled=True` untuk semua pasangan (`category`, `channel`) yang didukung.
3. WHEN user mengubah preferensi pada `/my/notifications/settings` dan menyimpan, THE Notification_System SHALL menyimpan perubahan dan menampilkan konfirmasi sukses.
4. WHEN `Notification_Dispatcher` akan membuat record in-app atau mengirim email, THE Notification_Dispatcher SHALL memeriksa preferensi (`user_id`, `category`, `channel`) dan hanya melanjutkan jika `enabled=True`.
5. WHERE event_code termasuk dalam kategori transaksional kritis (`order`, `payment`, `account`), THE Notification_System SHALL tetap mengirim notifikasi in-app meskipun preferensi user dimatikan.

### Requirement 3: Notification Center

**User Story:** Sebagai user, saya ingin melihat semua notifikasi saya di satu halaman dengan filter dan aksi sederhana.

#### Acceptance Criteria

1. WHEN user terautentikasi membuka rute `/my/notifications`, THE Notification_System SHALL menampilkan daftar `Notification_Record` milik user diurutkan `create_date` desc dengan paginasi 20 item per halaman.
2. THE Notification_Center SHALL menyediakan filter kategori (All, Akun, Seller, Pesanan, Pembayaran, Chat, Review, Sistem) menggunakan tab atau dropdown.
3. WHEN user menekan tombol mark as read pada satu notifikasi, THE Notification_System SHALL men-set `is_read=True` dan `read_at=now()` pada record tersebut.
4. WHEN user menekan tombol "Tandai semua dibaca", THE Notification_System SHALL men-set `is_read=True` pada semua record user yang masih unread.
5. WHEN user menekan tombol hapus pada satu notifikasi, THE Notification_System SHALL menghapus record hanya jika `user_id` cocok dengan user yang login.
6. IF user mencoba mengakses atau memodifikasi `Notification_Record` milik user lain, THEN THE Notification_System SHALL mengembalikan response 403 Forbidden.
7. THE Notification_Center SHALL menggunakan kelas Tailwind dengan prefix `tw-` dan mengikuti palet warna serta tipografi `unitrade_theme`.

### Requirement 4: Notification Bell di Navbar

**User Story:** Sebagai user, saya ingin melihat indikator notifikasi belum dibaca di navbar, sehingga saya tahu ada update tanpa membuka halaman khusus.

#### Acceptance Criteria

1. WHEN user terautentikasi memuat halaman dengan navbar UniTrade, THE Notification_Bell SHALL menampilkan ikon lonceng dengan badge angka `Unread_Counter`.
2. WHILE `Unread_Counter` lebih dari 99, THE Notification_Bell SHALL menampilkan teks `99+` pada badge.
3. WHILE `Unread_Counter` sama dengan 0, THE Notification_Bell SHALL menyembunyikan badge.
4. WHEN user mengklik `Notification_Bell`, THE Notification_System SHALL menampilkan dropdown dengan 5 notifikasi terbaru dan link "Lihat semua" ke `/my/notifications` dan link "Pengaturan".
5. WHEN user mengklik salah satu item di dropdown, THE Notification_System SHALL menandai item tersebut sebagai dibaca dan mengarahkan ke `action_url` jika tersedia.
6. THE Notification_Bell SHALL melakukan polling endpoint `/my/notifications/unread_count` setiap 60 detik untuk memperbarui badge.

### Requirement 5: Coverage Event Notifikasi

**User Story:** Sebagai user, saya ingin menerima notifikasi untuk event penting di alur belanja, jualan, dan akun, sehingga saya tidak ketinggalan informasi.

#### Acceptance Criteria

1. WHEN registrasi user berhasil dan akun aktif, THE Notification_System SHALL mengirim in-app dan email dengan event_code `account.welcome`.
2. WHEN user menyelesaikan reset password, THE Notification_System SHALL mengirim email konfirmasi dengan event_code `account.password_reset`.
3. WHEN user mengirim pengajuan seller, THE Notification_System SHALL mengirim in-app dan email dengan event_code `seller.application_received`.
4. WHEN admin menyetujui pengajuan seller, THE Notification_System SHALL mengirim in-app dan email dengan event_code `seller.approved`.
5. WHEN admin menolak pengajuan seller, THE Notification_System SHALL mengirim in-app dan email dengan event_code `seller.rejected` berisi alasan penolakan.
6. WHEN pesanan baru dibuat dengan minimal satu item dari seller, THE Notification_System SHALL mengirim in-app dan email ke setiap seller terkait dengan event_code `order.new_for_seller`.
7. WHEN pesanan dikonfirmasi, THE Notification_System SHALL mengirim in-app dan email ke buyer dengan event_code `order.confirmed`.
8. WHEN status pesanan berubah ke `shipped`, THE Notification_System SHALL mengirim in-app dan email ke buyer dengan event_code `order.shipped` berisi nomor resi (jika ada).
9. WHEN status pesanan berubah ke `delivered`, THE Notification_System SHALL mengirim in-app ke buyer dan seller dengan event_code `order.delivered`.
10. WHEN pesanan dibatalkan, THE Notification_System SHALL mengirim in-app dan email ke pihak terkait dengan event_code `order.cancelled` berisi alasan pembatalan.
11. WHEN webhook Midtrans dengan status `success`, `pending`, `failed`, atau `expired` diproses, THE Notification_System SHALL mengirim in-app dan email ke buyer dengan event_code `payment.success`, `payment.pending`, `payment.failed`, atau `payment.expired` berurutan, serta in-app ke seller pada `payment.success`.
12. WHEN pesan baru dikirim ke chat dan penerima sedang tidak membuka chat tersebut, THE Notification_System SHALL mengirim in-app dengan event_code `chat.new_message`, dengan grouping per (`chat_id`, `recipient_id`) jendela 10 menit untuk menghindari spam.
13. WHEN status pesanan berubah ke `delivered` dan setelah 24 jam buyer belum membuat review, THE Notification_System SHALL mengirim satu reminder in-app dengan event_code `review.reminder` per pasangan (`buyer_id`, `pesanan_id`).
14. WHEN review baru dipublish untuk produk seller, THE Notification_System SHALL mengirim in-app ke seller dengan event_code `review.new_for_seller`.
15. WHEN admin mempublish pengumuman platform, THE Notification_System SHALL membuat `Notification_Record` in-app dengan event_code `system.announcement` untuk semua user aktif yang preferensinya `enabled=True`.

### Requirement 6: Email Templates

**User Story:** Sebagai sistem, saya butuh template email konsisten untuk event yang menggunakan channel email, sehingga komunikasi profesional dan dapat diaudit.

#### Acceptance Criteria

1. THE Notification_System SHALL menyediakan satu `mail.template` aktif untuk setiap event_code yang menggunakan channel email.
2. THE Notification_System SHALL menambahkan mail template untuk event_code yang belum tercover saat ini, minimal: `account.welcome`, `account.password_reset`, `seller.application_received`, `seller.approved`, `seller.rejected`, `order.new_for_seller`, `order.shipped`, `order.cancelled`, `payment.success`, `payment.pending`, `payment.failed`, `payment.expired`, `system.announcement`.
3. THE Notification_System SHALL mempertahankan dan memakai template eksisting `mail_template_order_confirmed` untuk event_code `order.confirmed`.
4. THE Notification_System SHALL menggunakan layout email konsisten: header brand UniTrade, body dinamis, footer dengan link ke `/my/notifications/settings`.
5. WHERE konfigurasi `ir.config_parameter` `unitrade.notification.email_from` tersedia, THE Notification_System SHALL memakai nilai tersebut sebagai `email_from`, jika tidak tersedia memakai `company_id.email`.
6. THE Notification_System SHALL men-set `email_state='sent'` setelah email berhasil dikirim ke `mail.mail`, dan `email_state='failed'` jika gagal.

### Requirement 7: Security & Akses

**User Story:** Sebagai pemilik akun, saya ingin notifikasi saya hanya dapat diakses oleh saya dan tidak membocorkan data sensitif.

#### Acceptance Criteria

1. THE Notification_System SHALL menerapkan `ir.rule` (record rule) yang membatasi `read` dan `write` `Notification_Record` hanya pada record dengan `user_id == env.user.id`, kecuali user adalah admin.
2. THE Notification_System SHALL melarang penyertaan kata sandi, token reset penuh, atau API key dalam body email maupun in-app message.
3. IF `Notification_Dispatcher` menerima `event_code` yang tidak terdaftar di registry internal, THEN THE Notification_Dispatcher SHALL menolak emisi dan mencatat warning via `_logger`.
4. THE Notification_System SHALL memvalidasi `action_url` agar hanya mengarah ke path internal UniTrade (relative URL atau domain yang dikonfigurasi).

### Requirement 8: Konfigurasi & Logging

**User Story:** Sebagai admin/developer, saya ingin sistem dapat dikonfigurasi tanpa ubah kode dan kegagalan dapat ditelusuri.

#### Acceptance Criteria

1. THE Notification_System SHALL membaca parameter `unitrade.notification.email_from` dari `ir.config_parameter` untuk alamat pengirim email.
2. THE Notification_System SHALL membaca parameter `unitrade.notification.broadcast_batch_size` (default 200) untuk emisi `system.announcement` ke banyak user.
3. THE Notification_System SHALL mencatat melalui `_logger` setiap emisi pada level INFO berisi `user_id`, `event_code`, dan hasil (created/skipped/duplicate).
4. IF emisi gagal pada channel email, THEN THE Notification_System SHALL mencatat WARNING dengan stacktrace dan men-set `email_state='failed'`.
5. THE Notification_System SHALL menyediakan view admin sederhana untuk melihat record dengan `email_state='failed'` dan tombol retry per record.

### Requirement 9: Performance & Retention

**User Story:** Sebagai user, saya ingin halaman notifikasi cepat dimuat. Sebagai operator, saya ingin database tidak menggembung.

#### Acceptance Criteria

1. THE Notification_System SHALL membuat indeks pada (`user_id`, `is_read`) dan (`user_id`, `category`, `create_date`).
2. WHEN user memuat `/my/notifications`, THE Notification_System SHALL menyajikan halaman pertama dalam waktu wajar (di bawah 1 detik p95 pada server pengembangan referensi) untuk user dengan kurang dari atau sama dengan 5000 record.
3. WHEN endpoint `/my/notifications/unread_count` dipanggil, THE Notification_System SHALL merespons di bawah 200 milidetik p95.
4. THE Notification_System SHALL menyediakan cron harian yang menghapus `Notification_Record` dengan `is_read=True` dan `create_date` lebih lama dari 180 hari.
5. WHERE channel email dipakai, THE Notification_System SHALL mengantri pengiriman pada `mail.mail` dan dieksekusi oleh worker mail Odoo, sehingga emisi notifikasi tidak memblokir request HTTP.

### Requirement 10: Correctness Properties (PBT-Ready)

**User Story:** Sebagai sistem, saya ingin perilaku Notification_Dispatcher konsisten dan dapat diverifikasi otomatis.

#### Acceptance Criteria

1. FOR ALL pasangan emisi (`user_id`, `event_code`, `reference_model`, `reference_id`) yang dipanggil dua kali atau lebih, THE Notification_Dispatcher SHALL menghasilkan tepat satu `Notification_Record` (idempotency property).
2. FOR ALL daftar `Notification_Record` milik satu user, THE Notification_System SHALL mempertahankan urutan menurun berdasarkan `create_date` pada query default (ordering property).
3. FOR ALL pemanggilan `mark_all_as_read(user_id)` berturut-turut tanpa emisi baru, THE Notification_System SHALL menghasilkan `Unread_Counter == 0` dan pemanggilan kedua tidak mengubah state lebih lanjut (idempotency mark-all-read).
4. FOR ALL `Notification_Record` yang dihapus oleh user pemiliknya, THE Notification_System SHALL memastikan record tidak muncul lagi pada query daftar dan `Unread_Counter` berkurang sesuai (consistency property).
5. FOR ALL preferensi `(user_id, category, channel)` dengan `enabled=False` pada kategori non-kritis, THE Notification_Dispatcher SHALL tidak membuat record atau email pada channel yang dimatikan (preference enforcement property).
