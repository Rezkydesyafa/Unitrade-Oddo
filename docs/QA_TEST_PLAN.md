# Dokumentasi QA UniTrade Marketplace

Dokumen ini dipakai sebagai panduan sederhana untuk tester. Fokusnya adalah:

- fitur apa saja yang harus dites;
- test case apa saja yang wajib dijalankan;
- hasil yang harus muncul saat fitur berjalan benar.

Catatan scope: fitur pengiriman/kurir belum masuk pengujian karena saat ini tidak ada di fitur yang akan dites.

## 1. Cara Membaca Dokumen Ini

Setiap fitur punya 2 bagian:

- **Fokus test**: hal utama yang harus dicek oleh QA.
- **Test case**: skenario uji yang bisa langsung dijalankan.

Status test yang digunakan:

| Status | Arti |
| --- | --- |
| Not Run | Belum dites |
| Pass | Hasil sesuai |
| Fail | Ada bug |
| Blocked | Tidak bisa dites karena ada kendala |
| Retest | Menunggu dites ulang setelah bug diperbaiki |

Prioritas test:

| Prioritas | Arti |
| --- | --- |
| P0 | Wajib dites sebelum demo/rilis |
| P1 | Penting, dites setelah P0 selesai |
| P2 | Tambahan, dites jika waktu cukup |

## 2. Format Test Case

Gunakan format ini untuk membuat test case baru.

| Field | Isi |
| --- | --- |
| Test Case ID | Kode unik, contoh `AUTH-001` |
| Fitur | Nama fitur yang dites |
| Prioritas | P0, P1, atau P2 |
| Role | Guest, Buyer, Seller, Admin |
| Skenario | Kondisi yang ingin diuji |
| Data Test | Akun, produk, order, atau file yang dipakai |
| Langkah Test | Langkah yang dilakukan tester |
| Hasil yang Diharapkan | Hasil yang harus muncul |
| Hasil Aktual | Hasil saat dites |
| Status | Not Run, Pass, Fail, Blocked, Retest |
| Catatan/Bug | Link bug, screenshot, atau catatan |

Template:

```markdown
| Field | Isi |
| --- | --- |
| Test Case ID |  |
| Fitur |  |
| Prioritas | P0 |
| Role |  |
| Skenario |  |
| Data Test |  |
| Langkah Test | 1. ...<br>2. ...<br>3. ... |
| Hasil yang Diharapkan |  |
| Hasil Aktual |  |
| Status | Not Run |
| Catatan/Bug |  |
```

## 3. Fitur yang Harus Dites

| No | Fitur | Fokus Test | Prioritas |
| --- | --- | --- | --- |
| 1 | Register, login, OTP | User bisa daftar, login, dan verifikasi akun | P0 |
| 2 | Profil dan alamat | User bisa update data diri dan alamat | P1 |
| 3 | Katalog produk | User bisa melihat, mencari, filter, dan buka detail produk | P0 |
| 4 | Keranjang | User bisa tambah, ubah qty, hapus produk, dan stok tervalidasi | P0 |
| 5 | Checkout dan pembayaran | User bisa membuat pesanan dan payment status berubah benar | P0 |
| 6 | Seller verification | User bisa daftar seller dan admin bisa approve/reject | P0 |
| 7 | Dashboard seller | Seller bisa kelola produk, order, dan payout | P1 |
| 8 | Wishlist | User bisa simpan dan hapus produk favorit | P1 |
| 9 | Chat | Buyer dan seller bisa chat berdasarkan produk | P1 |
| 10 | Review | Buyer hanya bisa review setelah order selesai | P0 |
| 11 | Refund/dispute | Buyer bisa ajukan refund dan seller/admin bisa merespons | P1 |
| 12 | Notifikasi | User menerima, membaca, dan menghapus notifikasi | P1 |
| 13 | Customer service | User bisa membuat tiket bantuan | P2 |
| 14 | Admin dan security | Hak akses setiap role harus benar | P0 |

## 4. Test Case Utama

### 4.1 Register, Login, dan OTP

Fokus test:

- Register hanya berhasil jika data valid.
- Email/nomor HP tidak boleh duplikat.
- User yang belum OTP diarahkan ke halaman verifikasi.
- OTP salah, expired, atau sudah dipakai harus ditolak.
- User yang OTP-nya benar bisa masuk ke sistem.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| AUTH-001 | P0 | Guest | Register akun baru dengan data valid | Buka `/web/signup`, isi nama, email, password, setujui syarat, submit | Akun dibuat dan user diarahkan ke halaman OTP |
| AUTH-002 | P0 | Guest | Register dengan email yang sudah terdaftar | Isi form register memakai email existing, submit | Sistem menolak dan menampilkan pesan email sudah digunakan |
| AUTH-003 | P0 | Guest | Login dengan akun valid yang sudah OTP | Buka `/web/login`, isi email dan password valid | User berhasil login dan masuk ke halaman utama |
| AUTH-004 | P0 | Guest | Login dengan password salah | Isi email valid dan password salah | Login gagal dan pesan error muncul |
| AUTH-005 | P0 | Guest | Verifikasi OTP benar | Register/login akun belum verified, masukkan OTP benar | Akun menjadi verified dan user bisa masuk |
| AUTH-006 | P0 | Guest | Verifikasi OTP salah | Masukkan OTP acak atau tidak sesuai | Sistem menolak OTP dan user tetap di halaman verifikasi |
| AUTH-007 | P1 | Guest | Resend OTP | Klik kirim ulang OTP | OTP baru dikirim dan OTP lama tidak boleh digunakan |
| AUTH-008 | P1 | Guest | Reset password | Buka `/web/reset_password`, masukkan email, buka link reset, ubah password | Password berhasil diganti dan user bisa login memakai password baru |

### 4.2 Profil dan Alamat

Fokus test:

- User bisa melihat data profilnya sendiri.
- User bisa mengubah data profil.
- Alamat wajib lengkap sebelum checkout.
- Koordinat/alamat invalid harus ditolak.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| PROF-001 | P1 | Buyer | Buka halaman profil | Login, buka `/my/account` | Data user tampil sesuai akun login |
| PROF-002 | P1 | Buyer | Update data profil valid | Ubah nama, nomor HP, gender, tanggal lahir, simpan | Data tersimpan dan tampil setelah refresh |
| PROF-003 | P1 | Buyer | Simpan alamat lengkap | Isi provinsi, kota, kecamatan, detail alamat, koordinat, simpan | Alamat tersimpan dan ringkasan alamat tampil |
| PROF-004 | P1 | Buyer | Simpan alamat tidak lengkap | Kosongkan field wajib alamat, simpan | Sistem menolak dan menampilkan field yang perlu diisi |
| PROF-005 | P2 | Buyer | Ubah pengaturan notifikasi | Buka settings, matikan/nyalakan preferensi notifikasi | Preferensi tersimpan setelah reload |

### 4.3 Katalog dan Detail Produk

Fokus test:

- Produk marketplace aktif tampil di katalog.
- Search dan filter menampilkan hasil yang sesuai.
- Detail produk menampilkan informasi penting.
- Produk inactive atau stok habis tidak salah ditampilkan sebagai produk siap dibeli.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| PROD-001 | P0 | Guest | Buka katalog produk | Buka `/shop` atau `/unitrade/products` | Daftar produk marketplace tampil tanpa error |
| PROD-002 | P0 | Guest | Search produk | Masukkan keyword produk di search | Hasil hanya menampilkan produk yang relevan |
| PROD-003 | P0 | Guest | Filter kategori | Pilih kategori produk | Produk yang tampil sesuai kategori |
| PROD-004 | P0 | Guest | Filter harga | Isi harga minimum dan maksimum | Produk yang tampil berada dalam rentang harga |
| PROD-005 | P0 | Guest | Filter kondisi | Pilih kondisi baru/bekas | Produk yang tampil sesuai kondisi |
| PROD-006 | P1 | Guest | Sort produk | Pilih sort termurah/termahal/terbaru | Urutan produk sesuai sort yang dipilih |
| PROD-007 | P0 | Guest | Buka detail produk | Klik salah satu produk | Detail menampilkan foto, nama, harga, stok, kondisi, seller, rating |
| PROD-008 | P1 | Guest | Produk serupa tampil | Buka detail produk yang punya kategori | Bagian produk serupa menampilkan produk relevan |

### 4.4 Keranjang

Fokus test:

- User bisa tambah produk ke keranjang.
- Qty bisa diubah.
- Produk bisa dihapus.
- Qty tidak boleh melebihi stok.
- Total harga harus benar.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| CART-001 | P0 | Buyer | Tambah produk ke keranjang | Login, buka detail produk, klik tambah keranjang | Produk masuk keranjang |
| CART-002 | P0 | Buyer | Ubah qty produk | Buka cart, ubah qty produk | Qty berubah dan subtotal ikut berubah |
| CART-003 | P0 | Buyer | Hapus produk dari cart | Buka cart, hapus produk | Produk hilang dari cart dan total diperbarui |
| CART-004 | P0 | Buyer | Qty melebihi stok | Tambahkan qty lebih besar dari stok | Sistem menolak atau menampilkan warning stok |
| CART-005 | P0 | Buyer | Checkout cart valid | Cart berisi produk stok cukup, klik checkout | User masuk ke halaman checkout/payment |
| CART-006 | P0 | Buyer | Checkout tanpa alamat lengkap | Cart valid tetapi alamat belum lengkap, klik checkout | Sistem meminta user melengkapi alamat |

### 4.5 Checkout dan Pembayaran

Fokus test:

- Order dibuat dengan total yang benar.
- Voucher valid mengubah total.
- Voucher invalid ditolak.
- Payment intent dibuat dengan reference unik.
- Webhook payment valid mengubah status.
- Webhook payment invalid tidak mengubah status.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| PAY-001 | P0 | Buyer | Checkout produk valid | Cart valid, alamat lengkap, lanjut payment | Order/payment intent dibuat dengan total benar |
| PAY-002 | P1 | Buyer | Pakai voucher valid | Masukkan kode voucher valid di checkout | Diskon diterapkan dan total berubah |
| PAY-003 | P1 | Buyer | Pakai voucher invalid | Masukkan kode voucher salah/expired | Voucher ditolak dan total tidak berubah |
| PAY-004 | P0 | Buyer | Buka instruksi pembayaran | Setelah checkout, buka halaman instruksi payment | Reference, amount, metode bayar, dan status pending tampil |
| PAY-005 | P0 | Webhook | Payment sukses dari gateway | Kirim payload payment sukses yang valid | Status payment/order berubah menjadi paid/success |
| PAY-006 | P0 | Webhook | Payload payment tidak valid | Kirim payload signature/token salah | Sistem menolak dan status order tidak berubah |
| PAY-007 | P0 | Webhook | Webhook dobel | Kirim payload sukses yang sama dua kali | Status tetap benar dan tidak membuat data dobel |
| PAY-008 | P1 | Buyer | Cancel order pending | Buka order pending, klik cancel | Order dibatalkan jika status masih boleh dibatalkan |

### 4.6 Seller Verification

Fokus test:

- User login bisa mengajukan menjadi seller.
- File KTM harus valid.
- NIM wajib valid.
- Admin bisa approve atau reject.
- User yang sudah verified tidak membuat pengajuan duplikat.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| SELL-001 | P0 | Buyer | Mulai onboarding seller | Login sebagai buyer, buka `/seller-onboarding`, klik mulai | User masuk ke halaman verifikasi seller |
| SELL-002 | P0 | Buyer | Submit KTM valid | Isi NIM valid, upload KTM JPG/PNG, submit | Pengajuan seller dibuat dengan status pending/manual review |
| SELL-003 | P0 | Buyer | Upload file bukan gambar | Upload PDF/EXE/TXT di field KTM | Sistem menolak file |
| SELL-004 | P0 | Buyer | Submit tanpa NIM | Kosongkan NIM, submit | Sistem menolak dan meminta NIM |
| SELL-005 | P0 | Buyer | Submit NIM tidak terdaftar | Isi NIM yang tidak ada di data mahasiswa | Pengajuan ditolak atau masuk review manual sesuai aturan |
| SELL-006 | P0 | Admin | Approve seller | Buka backend pengajuan seller, klik approve | Status seller menjadi verified dan user menjadi seller |
| SELL-007 | P0 | Admin | Reject seller | Buka pengajuan seller, isi alasan, klik reject | Status rejected dan alasan penolakan tersimpan |
| SELL-008 | P1 | Buyer | User verified buka onboarding lagi | Login sebagai seller verified, buka onboarding | Sistem tidak membuat pengajuan baru |

### 4.7 Dashboard Seller dan Produk Seller

Fokus test:

- Hanya seller verified yang bisa masuk dashboard.
- Seller bisa membuat, mengedit, dan menghapus produknya sendiri.
- Seller tidak boleh mengubah produk seller lain.
- Produk yang dibuat seller tampil di katalog jika aktif.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| SDASH-001 | P1 | Seller | Buka dashboard seller | Login seller verified, buka dashboard seller | Statistik dan menu seller tampil |
| SDASH-002 | P0 | Buyer | Buyer biasa buka dashboard seller | Login buyer non-seller, buka URL dashboard seller | Akses ditolak atau diarahkan sesuai aturan |
| SDASH-003 | P0 | Seller | Buat produk baru | Isi nama, harga, stok, kategori, kondisi, gambar, simpan | Produk tersimpan dan terkait seller login |
| SDASH-004 | P0 | Seller | Edit produk sendiri | Buka produk milik sendiri, ubah harga/stok, simpan | Perubahan tersimpan dan tampil di katalog |
| SDASH-005 | P0 | Seller | Hapus produk sendiri | Buka produk milik sendiri, klik delete | Produk tidak tampil lagi di katalog |
| SDASH-006 | P0 | Seller | Edit produk seller lain | Coba akses/edit produk milik seller lain | Sistem menolak akses |
| SDASH-007 | P1 | Seller | Lihat order seller | Buka menu pesanan seller | Hanya order yang berisi produk seller tersebut yang tampil |
| SDASH-008 | P2 | Seller | Simpan rekening payout | Isi data rekening payout, simpan | Data payout tersimpan dan tervalidasi |

### 4.8 Wishlist

Fokus test:

- User login bisa menambah dan menghapus wishlist.
- Guest tidak bisa menyimpan wishlist tanpa login.
- Produk tidak boleh dobel di wishlist.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| WISH-001 | P1 | Buyer | Tambah produk ke wishlist | Login, klik ikon wishlist di produk | Produk masuk wishlist dan ikon berubah |
| WISH-002 | P1 | Buyer | Hapus produk dari wishlist | Klik ikon wishlist lagi atau remove dari halaman wishlist | Produk keluar dari wishlist |
| WISH-003 | P1 | Guest | Guest klik wishlist | Tanpa login, klik wishlist | User diminta login |
| WISH-004 | P1 | Buyer | Tambah produk yang sama dua kali | Klik wishlist pada produk yang sama berulang | Tidak ada data wishlist dobel |
| WISH-005 | P2 | Buyer | Buka halaman wishlist | Buka `/my/wishlist` | Produk wishlist tampil dan dikelompokkan dengan benar |

### 4.9 Chat Buyer dan Seller

Fokus test:

- Buyer bisa membuka chat dari produk.
- Chat terhubung dengan produk dan seller yang benar.
- Pesan tampil di sisi buyer dan seller.
- User tidak boleh melihat chat milik orang lain.
- Report chat bisa dibuat.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| CHAT-001 | P1 | Buyer | Buka chat dari detail produk | Login buyer, buka produk seller lain, klik chat | Conversation dibuat dan halaman chat terbuka |
| CHAT-002 | P1 | Buyer | Kirim pesan text | Ketik pesan, klik kirim | Pesan tampil di chat buyer |
| CHAT-003 | P1 | Seller | Seller membaca pesan | Login seller pemilik produk, buka chat seller | Pesan buyer tampil di sisi seller |
| CHAT-004 | P1 | Buyer/Seller | Mark read | Buka conversation yang punya pesan belum dibaca | Unread count berubah sesuai pesan yang sudah dibaca |
| CHAT-005 | P1 | Buyer | Report chat | Buka chat, pilih report, isi alasan, submit | Laporan chat dibuat |
| CHAT-006 | P0 | Buyer lain | Akses chat orang lain | Login user lain, coba buka conversation bukan miliknya | Akses ditolak |

### 4.10 Review Produk

Fokus test:

- Review hanya bisa dibuat oleh buyer yang order-nya selesai.
- Satu order hanya boleh punya satu review.
- Rating harus 1 sampai 5.
- Review tampil di detail produk.
- Admin bisa menyembunyikan review jika perlu.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| REV-001 | P0 | Buyer | Buat review order selesai | Login buyer dengan order selesai, beri rating dan komentar | Review tersimpan dan tampil di produk |
| REV-002 | P0 | Buyer | Review produk yang belum dibeli | Coba review produk tanpa order selesai | Sistem menolak |
| REV-003 | P0 | Buyer | Review dobel | Submit review kedua untuk order yang sama | Sistem menolak review duplikat |
| REV-004 | P0 | Buyer | Rating invalid | Kirim rating 0 atau lebih dari 5 | Sistem menolak |
| REV-005 | P1 | Guest | Lihat daftar review | Buka detail produk yang punya review | Review dan rata-rata rating tampil |
| REV-006 | P1 | Admin | Sembunyikan review | Admin hide review dari backend | Review tidak tampil di website |

### 4.11 Refund dan Dispute

Fokus test:

- Buyer hanya bisa refund order miliknya.
- Refund wajib punya alasan.
- Bukti upload harus valid.
- Seller bisa approve/reject refund.
- User lain tidak boleh melihat dispute tersebut.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| REF-001 | P1 | Buyer | Buat refund valid | Buka order milik sendiri, klik refund, isi alasan dan bukti, submit | Dispute/refund dibuat |
| REF-002 | P1 | Buyer | Refund tanpa alasan | Submit refund tanpa alasan | Sistem menolak |
| REF-003 | P1 | Buyer | Upload bukti invalid | Upload file bukan gambar/dokumen yang diizinkan | Sistem menolak file |
| REF-004 | P0 | Buyer lain | Buka refund user lain | Login user lain, akses URL refund tersebut | Akses ditolak |
| REF-005 | P1 | Seller | Seller approve refund | Login seller terkait, approve refund | Status refund berubah sesuai approval |
| REF-006 | P1 | Seller | Seller reject refund | Login seller terkait, reject dengan alasan | Status refund rejected dan alasan tersimpan |

### 4.12 Notifikasi

Fokus test:

- Notifikasi dibuat saat event penting terjadi.
- User hanya melihat notifikasi miliknya sendiri.
- Unread count benar.
- Mark read dan delete bekerja.
- Preferensi notifikasi tersimpan.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| NOTIF-001 | P1 | Buyer | Buka notification center | Login, buka `/my/notifications` | List notifikasi user tampil |
| NOTIF-002 | P1 | Buyer | Cek unread count | Buat notifikasi baru, cek badge/bell | Jumlah unread sesuai |
| NOTIF-003 | P1 | Buyer | Mark one as read | Klik notifikasi atau tombol read | Status berubah menjadi read |
| NOTIF-004 | P1 | Buyer | Mark all as read | Klik read all | Semua notifikasi user menjadi read |
| NOTIF-005 | P1 | Buyer | Delete notifikasi | Hapus salah satu notifikasi | Notifikasi hilang dari list user |
| NOTIF-006 | P0 | Buyer lain | Akses notifikasi user lain | Coba mark/read/delete notif milik user lain | Akses ditolak |
| NOTIF-007 | P2 | Buyer | Update preference | Ubah preference notifikasi di settings | Preference tersimpan |

### 4.13 Customer Service

Fokus test:

- User bisa membuat tiket bantuan.
- Field wajib harus divalidasi.
- User hanya melihat tiket miliknya.
- Bukti lampiran tampil di detail tiket.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| CS-001 | P2 | Buyer | Buat tiket valid | Buka halaman customer service, isi kategori, judul, deskripsi, submit | Tiket dibuat |
| CS-002 | P2 | Buyer | Buat tiket tanpa judul | Kosongkan judul, submit | Sistem menolak |
| CS-003 | P2 | Buyer | Upload bukti tiket | Buat tiket dengan lampiran | Lampiran tersimpan dan tampil di detail |
| CS-004 | P1 | Buyer lain | Buka tiket user lain | Login user lain dan akses URL tiket | Akses ditolak |

### 4.14 Admin dan Security

Fokus test:

- Admin bisa mengakses menu backend UniTrade.
- User biasa tidak bisa mengakses menu admin.
- Buyer tidak bisa melihat data buyer lain.
- Seller tidak bisa mengubah data seller lain.
- Endpoint publik tidak membocorkan data sensitif.

| ID | Prioritas | Role | Skenario | Langkah Test | Hasil yang Diharapkan |
| --- | --- | --- | --- | --- | --- |
| SEC-001 | P0 | Admin | Buka backend UniTrade | Login admin, buka menu seller/review/payment/notifikasi | Menu dan data tampil tanpa error access |
| SEC-002 | P0 | Buyer | Buka backend admin | Login buyer, coba akses backend/menu admin | Akses ditolak |
| SEC-003 | P0 | Buyer | Akses order user lain | Login buyer A, coba buka order buyer B | Akses ditolak |
| SEC-004 | P0 | Seller | Edit produk seller lain | Login seller A, coba edit produk seller B | Akses ditolak |
| SEC-005 | P0 | Guest | Buka halaman login-required | Tanpa login, buka `/my/account`, wishlist, chat, order | User diarahkan ke login |
| SEC-006 | P0 | Webhook | Kirim request webhook invalid | Kirim payload tanpa signature/token valid | Request ditolak dan data tidak berubah |
| SEC-007 | P0 | QA | Cek credential API | Cari credential di file source dan cek config | Credential tidak hardcode, dibaca dari config |

## 5. Smoke Test Singkat Sebelum Demo

Jalankan ini sebelum demo. Jika salah satu P0 gagal, demo sebaiknya ditunda atau bug dicatat sebagai risiko.

| No | Test | Hasil yang Diharapkan |
| --- | --- | --- |
| 1 | Buka homepage | Halaman tampil normal |
| 2 | Login buyer | Login berhasil |
| 3 | Buka katalog produk | Produk tampil |
| 4 | Search/filter produk | Hasil sesuai filter |
| 5 | Buka detail produk | Info produk lengkap |
| 6 | Tambah produk ke cart | Produk masuk cart |
| 7 | Checkout | Order/payment dibuat |
| 8 | Login seller | Dashboard seller tampil |
| 9 | Seller buat/edit produk | Produk tersimpan |
| 10 | Buyer chat seller | Pesan terkirim |
| 11 | Buyer tambah wishlist | Wishlist berubah |
| 12 | Buyer buat review order selesai | Review tersimpan |
| 13 | Buyer buat refund | Refund/dispute dibuat |
| 14 | Buka notifikasi | Notifikasi tampil |
| 15 | Login admin | Menu admin UniTrade bisa dibuka |

## 6. Data yang Perlu Disiapkan QA

Minimal data test:

- 1 akun buyer aktif.
- 1 akun seller verified.
- 1 akun seller pending/rejected.
- 1 akun admin.
- Beberapa produk aktif dengan kategori, kondisi, harga, dan stok berbeda.
- 1 produk stok terbatas untuk test validasi stok.
- 1 order pending.
- 1 order paid/success.
- 1 order selesai untuk test review.
- 1 order eligible untuk refund.
- 1 voucher valid dan 1 voucher expired/invalid.
- File KTM valid dan file invalid untuk test upload.
- Gambar produk/review valid dan file non-image untuk negative test.

Jika memakai seed data project, ikuti panduan di [Test Data Seed](./UNITRADE_TEST_DATA_SEED.md).

## 7. Definition of Done QA

Fitur dianggap siap jika:

- Semua test P0 terkait fitur tersebut Pass.
- Tidak ada bug Critical atau High yang masih terbuka.
- Bug Medium sudah dicatat dan disetujui jika belum diperbaiki.
- Test evidence tersedia untuk flow utama.
- User role sudah diuji, terutama buyer, seller, dan admin.
- Tidak ada data user lain yang bocor.
- Tidak ada credential API yang hardcode.

