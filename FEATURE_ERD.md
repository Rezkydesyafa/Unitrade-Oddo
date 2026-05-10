# ERD UniTrade Marketplace

Dokumen ini menjelaskan hubungan data utama di project UniTrade dengan bahasa yang lebih umum dan mudah dibaca. Diagram dibuat dengan Mermaid, jadi jika file ini di-upload ke GitHub, diagram akan tampil otomatis.

Catatan agar mudah dibaca:

- Nama seperti `AKUN_USER` dibaca sebagai "Akun User". Garis bawah hanya dipakai agar format diagram bisa dibaca Mermaid.
- Saya hanya menampilkan data penting yang membantu memahami fitur, bukan semua kolom bawaan sistem.
- Relasi yang diberi label "dicek lewat NIM" berarti datanya dicocokkan berdasarkan aturan bisnis.

## Cara Membaca ERD

| Simbol | Arti sederhana |
| --- | --- |
| `||` | Satu data wajib ada |
| `o|` | Boleh kosong, maksimal satu |
| `o{` | Boleh kosong, bisa banyak |
| `}|` | Minimal satu, bisa banyak |

Contoh: `AKUN_USER ||--o{ KODE_OTP` artinya satu akun bisa meminta banyak kode OTP, tetapi satu kode OTP hanya milik satu akun.

## Kamus Nama Data

| Nama di diagram | Arti mudahnya |
| --- | --- |
| `AKUN_USER` | Data akun untuk login, register, dan hak akses |
| `PROFIL_USER` | Data pribadi user, alamat, nomor HP, dan lokasi |
| `KODE_OTP` | Kode verifikasi untuk email, WhatsApp, atau reset password |
| `NOTIFIKASI` | Pesan pemberitahuan untuk user |
| `DATA_MAHASISWA` | Data mahasiswa UNISA untuk validasi NIM |
| `PENGAJUAN_SELLER` | Pengajuan user untuk menjadi seller |
| `SELLER` | Data toko atau akun penjual yang sudah disetujui |
| `PRODUK` | Barang yang dijual di marketplace |
| `GAMBAR_PRODUK` | Foto tambahan untuk produk |
| `PESANAN` | Transaksi pembelian |
| `ITEM_PESANAN` | Daftar barang di dalam satu pesanan |
| `REVIEW_PRODUK` | Ulasan pembeli untuk produk |
| `WISHLIST` | Produk yang disimpan user |
| `CHAT` | Percakapan antara buyer dan seller |
| `PESAN_CHAT` | Isi pesan di dalam chat |
| `BATAS_CHAT` | Catatan pembatas aktivitas chat agar tidak spam |
| `LAPORAN_CHAT` | Laporan pelanggaran chat |
| `FILE_UPLOAD` | File atau gambar yang diunggah user |

## 1. ERD Besar UniTrade

Diagram ini menunjukkan hubungan utama antar fitur.

```mermaid
erDiagram
    AKUN_USER ||--|| PROFIL_USER : "punya profil"
    AKUN_USER ||--o{ KODE_OTP : "meminta kode OTP"
    AKUN_USER ||--o| SELLER : "bisa menjadi seller"
    AKUN_USER ||--o{ NOTIFIKASI : "menerima notifikasi"

    PROFIL_USER ||--o{ PESANAN : "membuat pesanan"
    PROFIL_USER ||--o{ PENGAJUAN_SELLER : "mengajukan seller"

    DATA_MAHASISWA ||..o{ PENGAJUAN_SELLER : "dicek lewat NIM"
    DATA_MAHASISWA ||..o{ SELLER : "NIM seller harus valid"

    PENGAJUAN_SELLER }o--o| SELLER : "bisa menjadi seller"
    FILE_UPLOAD ||--o{ PENGAJUAN_SELLER : "menyimpan file KTM"

    SELLER ||--o{ PRODUK : "menjual produk"
    SELLER ||--o{ CHAT : "melayani chat"

    PRODUK ||--o{ GAMBAR_PRODUK : "punya foto"
    PRODUK ||--o{ WISHLIST : "disimpan user"
    PRODUK ||--o{ REVIEW_PRODUK : "mendapat review"
    PRODUK ||--o{ ITEM_PESANAN : "dibeli"
    PRODUK ||--o{ CHAT : "dibahas"

    PESANAN ||--o{ ITEM_PESANAN : "berisi barang"
    PESANAN ||--o{ REVIEW_PRODUK : "menjadi bukti pembelian"

    AKUN_USER ||--o{ WISHLIST : "menyimpan produk"
    AKUN_USER ||--o{ REVIEW_PRODUK : "menulis review"
    AKUN_USER ||--o{ CHAT : "menghubungi seller"
    AKUN_USER ||--o{ PESAN_CHAT : "mengirim pesan"
    AKUN_USER ||--o{ BATAS_CHAT : "dibatasi jika terlalu sering"

    CHAT ||--o{ PESAN_CHAT : "berisi pesan"
    CHAT ||--o{ LAPORAN_CHAT : "bisa dilaporkan"
    FILE_UPLOAD ||--o{ PESAN_CHAT : "lampiran chat"
    FILE_UPLOAD ||--o{ LAPORAN_CHAT : "bukti laporan"
```

## 2. Akun, Profil, OTP, dan Notifikasi

Bagian ini dipakai untuk fitur register, login, verifikasi akun, reset password, edit profil, dan notifikasi.

```mermaid
erDiagram
    AKUN_USER {
        int id PK
        string email_login
        string nama_user
        int profil_id FK
        boolean email_sudah_verifikasi
        boolean otp_sudah_verifikasi
        boolean adalah_seller
        string no_whatsapp
        string jenis_kelamin
        date tanggal_lahir
        boolean chat_diblokir
        datetime chat_diblokir_sampai
    }

    PROFIL_USER {
        int id PK
        string nama_lengkap
        string email
        string nomor_hp
        string alamat_jalan
        string kota
        string kode_pos
        string label_alamat
        string provinsi
        string kabupaten
        string kecamatan
        string kelurahan
        float latitude
        float longitude
    }

    KODE_OTP {
        int id PK
        int akun_id FK
        string kode
        string tujuan_otp
        string email_atau_whatsapp
        datetime berlaku_sampai
        boolean sudah_dipakai
        datetime waktu_dipakai
    }

    NOTIFIKASI {
        int id PK
        int akun_id FK
        string judul
        text isi
        string tipe_notifikasi
        string link_tujuan
        boolean sudah_dibaca
        datetime waktu_dibaca
    }

    AKUN_USER ||--|| PROFIL_USER : "punya profil"
    AKUN_USER ||--o{ KODE_OTP : "meminta kode OTP"
    AKUN_USER ||--o{ NOTIFIKASI : "menerima notifikasi"
```

Alur data sederhananya:

1. User membuat akun, lalu sistem menyimpan `AKUN_USER` dan `PROFIL_USER`.
2. Saat verifikasi atau reset password, sistem membuat `KODE_OTP`.
3. Jika ada informasi penting, sistem membuat `NOTIFIKASI` untuk akun tersebut.

## 3. Seller, Mahasiswa, dan Verifikasi KTM

Bagian ini dipakai untuk fitur daftar seller, upload KTM, pengecekan NIM, dan persetujuan seller oleh admin.

```mermaid
erDiagram
    DATA_MAHASISWA {
        int id PK
        string nim
        string nama_mahasiswa
        string fakultas
        boolean masih_aktif
    }

    PENGAJUAN_SELLER {
        int id PK
        int profil_user_id FK
        int file_ktm_id FK
        int seller_terkait_id FK
        string status_pengajuan
        string nim_terbaca
        string nim_terdaftar
        string nama_mahasiswa
        float skor_kecocokan_nama
        string alasan_ditolak
        text catatan_admin
        datetime waktu_pengajuan
        datetime waktu_diperiksa
    }

    SELLER {
        int id PK
        int akun_user_id FK
        int profil_user_id FK
        string nim
        string status_seller
        string link_profil
        text deskripsi_toko
        string alamat_toko
        float latitude_toko
        float longitude_toko
        image foto_ktm
        text hasil_baca_ktm
        datetime tanggal_disetujui
        int admin_penyetuju_id FK
        string status_laporan
    }

    FILE_UPLOAD {
        int id PK
        string nama_file
        string tipe_file
        string asal_data
        int id_data_asal
    }

    AKUN_USER ||--|| PROFIL_USER : "punya profil"
    AKUN_USER ||--o| SELLER : "bisa menjadi seller"
    PROFIL_USER ||--o{ PENGAJUAN_SELLER : "mengajukan seller"
    FILE_UPLOAD ||--o{ PENGAJUAN_SELLER : "menyimpan file KTM"
    PENGAJUAN_SELLER }o--o| SELLER : "bisa membuat data seller"
    DATA_MAHASISWA ||..o{ PENGAJUAN_SELLER : "dicek lewat NIM"
    DATA_MAHASISWA ||..o{ SELLER : "NIM seller harus valid"
```

Alur data sederhananya:

1. User mengirim pengajuan seller melalui `PENGAJUAN_SELLER`.
2. File KTM disimpan sebagai `FILE_UPLOAD`.
3. NIM dari KTM dicocokkan ke `DATA_MAHASISWA`.
4. Jika valid dan admin menyetujui, user mendapatkan data `SELLER`.

## 4. Produk Marketplace

Bagian ini dipakai untuk fitur tambah produk, tampilkan produk, filter pencarian, wishlist, review, dan chat produk.

```mermaid
erDiagram
    SELLER {
        int id PK
        int akun_user_id FK
        string nim
        string status_seller
        string link_profil
        text deskripsi_toko
    }

    PRODUK {
        int id PK
        string nama_produk
        money harga
        int kategori_id FK
        boolean boleh_dijual
        boolean tampil_di_website
        string kondisi_barang
        int seller_id FK
        string lokasi_seller
        string provinsi_barang
        string kabupaten_barang
        text spesifikasi
        float rating_rata_rata
        int jumlah_review
        string merek
        float berat
        float diskon_persen
        int stok_total
        int stok_tersedia
    }

    GAMBAR_PRODUK {
        int id PK
        int produk_id FK
        image gambar
        string nama_gambar
        int urutan
    }

    WISHLIST {
        int id PK
        int akun_user_id FK
        int produk_id FK
        datetime waktu_disimpan
    }

    REVIEW_PRODUK {
        int id PK
        int produk_id FK
        int akun_user_id FK
        int pesanan_id FK
        int rating
        text komentar
        string tag_review
        boolean tampil
        image foto_review_1
        image foto_review_2
        image foto_review_3
        datetime waktu_review
    }

    CHAT {
        int id PK
        int buyer_id FK
        int seller_id FK
        int produk_id FK
        datetime waktu_pesan_terakhir
        boolean aktif
    }

    SELLER ||--o{ PRODUK : "menjual produk"
    PRODUK ||--o{ GAMBAR_PRODUK : "punya foto"
    PRODUK ||--o{ WISHLIST : "disimpan user"
    PRODUK ||--o{ REVIEW_PRODUK : "mendapat review"
    PRODUK ||--o{ CHAT : "dibahas di chat"
```

Alur data sederhananya:

1. Seller membuat `PRODUK`.
2. Foto tambahan produk disimpan di `GAMBAR_PRODUK`.
3. User bisa menyimpan produk ke `WISHLIST`.
4. Setelah membeli, user bisa menulis `REVIEW_PRODUK`.
5. Produk juga bisa menjadi topik awal di `CHAT`.

## 5. Pesanan, Pembayaran, Review, dan Wishlist

Bagian ini dipakai untuk checkout, pembayaran, daftar barang yang dibeli, wishlist, dan review setelah pembelian.

```mermaid
erDiagram
    PROFIL_USER {
        int id PK
        string nama_lengkap
        string email
        string nomor_hp
        string alamat_jalan
        string kota
        float latitude
        float longitude
    }

    PESANAN {
        int id PK
        string nomor_pesanan
        int profil_pembeli_id FK
        string status_pesanan
        money total_bayar
        string kode_transaksi_pembayaran
        string token_pembayaran
        string status_pembayaran
        string metode_pembayaran
        datetime waktu_dibayar
        text data_pembayaran
    }

    ITEM_PESANAN {
        int id PK
        int pesanan_id FK
        int produk_id FK
        int jumlah
        money harga_satuan
        money subtotal
        string peringatan_stok
    }

    PRODUK {
        int id PK
        string nama_produk
        money harga
        int seller_id FK
        int stok_tersedia
    }

    AKUN_USER {
        int id PK
        string email_login
        string nama_user
    }

    REVIEW_PRODUK {
        int id PK
        int produk_id FK
        int akun_user_id FK
        int pesanan_id FK
        int rating
        text komentar
        boolean tampil
    }

    WISHLIST {
        int id PK
        int akun_user_id FK
        int produk_id FK
        datetime waktu_disimpan
    }

    PROFIL_USER ||--o{ PESANAN : "membuat pesanan"
    PESANAN ||--o{ ITEM_PESANAN : "berisi barang"
    PRODUK ||--o{ ITEM_PESANAN : "dibeli"
    PESANAN ||--o{ REVIEW_PRODUK : "menjadi bukti pembelian"
    PRODUK ||--o{ REVIEW_PRODUK : "mendapat review"
    AKUN_USER ||--o{ REVIEW_PRODUK : "menulis review"
    AKUN_USER ||--o{ WISHLIST : "menyimpan produk"
    PRODUK ||--o{ WISHLIST : "disimpan user"
```

Alur data sederhananya:

1. Buyer membuat `PESANAN`.
2. Barang yang dibeli disimpan sebagai `ITEM_PESANAN`.
3. Status pembayaran disimpan di `PESANAN`.
4. Jika pesanan valid, buyer bisa membuat `REVIEW_PRODUK`.
5. Produk yang belum dibeli bisa disimpan ke `WISHLIST`.

## 6. Chat Buyer dan Seller

Bagian ini dipakai untuk fitur chat produk, kirim pesan, kirim gambar, status belum dibaca, dan pembatasan spam.

```mermaid
erDiagram
    AKUN_USER {
        int id PK
        string email_login
        string nama_user
        boolean chat_diblokir
        datetime chat_diblokir_sampai
    }

    SELLER {
        int id PK
        int akun_user_id FK
        string status_seller
        string link_profil
    }

    PRODUK {
        int id PK
        string nama_produk
        money harga
        int seller_id FK
    }

    CHAT {
        int id PK
        int buyer_id FK
        int seller_id FK
        int produk_id FK
        int pesan_terakhir_id FK
        text isi_pesan_terakhir
        datetime waktu_pesan_terakhir
        int buyer_belum_baca
        int seller_belum_baca
        boolean aktif
    }

    PESAN_CHAT {
        int id PK
        int chat_id FK
        int pengirim_id FK
        string tipe_pesan
        text isi_pesan
        int produk_id FK
        int file_gambar_id FK
        datetime waktu_terkirim
        datetime waktu_dibaca
    }

    FILE_UPLOAD {
        int id PK
        string nama_file
        string tipe_file
        string asal_data
        int id_data_asal
    }

    BATAS_CHAT {
        int id PK
        int akun_user_id FK
        string aksi
        datetime mulai_periode
        int jumlah_request
    }

    AKUN_USER ||--o{ CHAT : "sebagai buyer"
    SELLER ||--o{ CHAT : "sebagai seller"
    PRODUK ||--o{ CHAT : "produk yang dibahas"
    CHAT ||--o{ PESAN_CHAT : "berisi pesan"
    AKUN_USER ||--o{ PESAN_CHAT : "mengirim pesan"
    PRODUK ||--o{ PESAN_CHAT : "bisa dikirim sebagai kartu produk"
    FILE_UPLOAD ||--o{ PESAN_CHAT : "lampiran gambar"
    AKUN_USER ||--o{ BATAS_CHAT : "dicatat aktivitasnya"
```

Alur data sederhananya:

1. Buyer membuka chat dengan seller untuk satu produk.
2. Sistem membuat `CHAT`.
3. Setiap pesan masuk ke `PESAN_CHAT`.
4. Jika pesan berisi gambar, file gambar masuk ke `FILE_UPLOAD`.
5. Aktivitas chat dicatat di `BATAS_CHAT` untuk mencegah spam.

## 7. Laporan Chat dan Moderasi

Bagian ini dipakai saat user melaporkan pesan atau percakapan yang bermasalah.

```mermaid
erDiagram
    CHAT {
        int id PK
        int buyer_id FK
        int seller_id FK
        int produk_id FK
        boolean aktif
    }

    LAPORAN_CHAT {
        int id PK
        int chat_id FK
        int pelapor_id FK
        int user_dilaporkan_id FK
        string alasan
        text detail_alasan
        int bukti_utama_id FK
        string status_laporan
        int admin_pemeriksa_id FK
        datetime waktu_diperiksa
        text catatan_admin
    }

    AKUN_USER {
        int id PK
        string email_login
        string nama_user
        boolean chat_diblokir
        datetime chat_diblokir_sampai
    }

    FILE_UPLOAD {
        int id PK
        string nama_file
        string tipe_file
        string asal_data
        int id_data_asal
    }

    CHAT ||--o{ LAPORAN_CHAT : "bisa dilaporkan"
    AKUN_USER ||--o{ LAPORAN_CHAT : "terlibat sebagai pelapor, terlapor, atau admin"
    FILE_UPLOAD ||--o{ LAPORAN_CHAT : "bukti laporan"
```

Alur data sederhananya:

1. User membuat `LAPORAN_CHAT` untuk satu `CHAT`.
2. Laporan menyimpan siapa pelapor dan siapa user yang dilaporkan.
3. Bukti gambar disimpan sebagai `FILE_UPLOAD`.
4. Admin memeriksa laporan, mengubah status, dan bisa memblokir chat user jika perlu.

## Ringkasan Relasi Utama

| Data utama | Terhubung ke | Penjelasan sederhana |
| --- | --- | --- |
| Akun User | Profil User | Satu akun punya satu profil |
| Akun User | Kode OTP | Satu akun bisa meminta banyak OTP |
| Akun User | Seller | Satu akun bisa punya satu data seller |
| Profil User | Pengajuan Seller | Satu profil bisa mengajukan verifikasi seller |
| Pengajuan Seller | File Upload | Pengajuan seller menyimpan file KTM |
| Data Mahasiswa | Pengajuan Seller | NIM dari KTM dicek ke data mahasiswa |
| Seller | Produk | Satu seller bisa menjual banyak produk |
| Produk | Gambar Produk | Satu produk bisa punya banyak foto |
| Profil User | Pesanan | Satu profil buyer bisa membuat banyak pesanan |
| Pesanan | Item Pesanan | Satu pesanan berisi banyak barang |
| Produk | Review Produk | Satu produk bisa punya banyak review |
| Akun User | Wishlist | Satu akun bisa menyimpan banyak produk |
| Chat | Pesan Chat | Satu chat berisi banyak pesan |
| Chat | Laporan Chat | Satu chat bisa memiliki laporan |
| File Upload | Pesan atau Laporan | File bisa dipakai sebagai lampiran atau bukti |

