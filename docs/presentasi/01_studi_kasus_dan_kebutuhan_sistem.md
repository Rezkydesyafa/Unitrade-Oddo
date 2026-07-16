# 01 — Studi Kasus & Kebutuhan Sistem

## Studi Kasus: UniTrade Marketplace UNISA Yogyakarta

### Latar Belakang Masalah

UniTrade adalah platform marketplace **C2C (Customer-to-Customer)** yang dibangun di atas **Odoo 17** untuk melayani kebutuhan jual-beli di lingkungan Universitas Aisyiyah (UNISA) Yogyakarta. Platform ini dibuat karena:

1. **Tidak ada platform jual-beli terverifikasi** di dalam ekosistem kampus. Mahasiswa selama ini memanfaatkan grup WhatsApp atau media sosial yang tidak aman.
2. **Tidak ada mekanisme verifikasi identitas penjual** — siapa saja bisa mengklaim sebagai mahasiswa UNISA.
3. **Tidak ada perlindungan dana pembeli** — jika penjual tidak mengirim barang, pembeli tidak punya jalur resmi.
4. **Tidak ada sistem dispute / mediasi** antara pembeli dan penjual.

### Solusi yang Diimplementasikan

- **Verifikasi KTM otomatis** menggunakan Google Cloud Vision OCR + fuzzy matching NIM ke database mahasiswa.
- **Sistem Escrow** untuk menahan dana pembeli sampai barang dikonfirmasi diterima.
- **Integrasi Midtrans** untuk pembayaran digital (Virtual Account, QRIS, E-Wallet).
- **AI Customer Service** berbasis Gemini 2.5 Flash untuk menangani pertanyaan umum.
- **Role-based access control** berlapis untuk memisahkan hak akses Pembeli, Penjual, dan Admin.

---

## Kebutuhan Sistem Enterprise

### 1. Kebutuhan Fungsional (Functional Requirements)

| Kode | Kebutuhan | Modul Odoo | File Utama |
|------|-----------|-----------|-----------|
| F1 | Registrasi akun dengan validasi email + OTP | `unitrade_theme` | `controllers/controllers.py` |
| F2 | Login Google OAuth (SSO) | `unitrade_theme` | `data/oauth_provider.xml` |
| F3 | Verifikasi penjual via KTM (OCR otomatis + review manual) | `unitrade_seller` | `services/ocr_service.py` |
| F4 | Listing produk + manajemen toko penjual | `unitrade_seller`, `unitrade_product_ext` | `controllers/main.py` |
| F5 | Filter produk di halaman toko | `unitrade_product_ext` | `controllers/main.py:L749` |
| F6 | Keranjang belanja | `unitrade_theme` | `controllers/cart.py` |
| F7 | Checkout + pemilihan metode pembayaran | `unitrade_theme` | `controllers/checkout.py` |
| F8 | Pembayaran via Midtrans (VA, QRIS, E-Wallet) | `unitrade_payment` | `models/sale_order.py` |
| F9 | Sistem Escrow otomatis | `unitrade_payment` | `models/payment_intent.py` |
| F10 | Pengiriman GoSend + Ambil Sendiri | `unitrade_delivery` | `models/` |
| F11 | Sistem dispute / refund | `unitrade_dispute` | `models/` |
| F12 | Wishlist produk | `unitrade_wishlist` | `controllers/main.py` |
| F13 | Ulasan dan rating produk | `unitrade_review` | `models/` |
| F14 | Notifikasi real-time (60 detik polling) | `unitrade_notification` | `static/src/js/notification_service.js` |
| F15 | Live chat antar pengguna | `unitrade_chat` | `controllers/` |
| F16 | Customer Service AI (Gemini 2.5 Flash) | `unitrade_cs_ai` | `models/cs_ai_service.py` |
| F17 | Dashboard admin (monitoring, moderasi, verifikasi KTM) | `unitrade_admin` | `models/admin_stats.py` |

### 2. Kebutuhan Non-Fungsional (Non-Functional Requirements)

| Kode | Kategori | Kebutuhan | Implementasi |
|------|----------|-----------|--------------|
| NF1 | Keamanan | Hanya mahasiswa aktif UNISA yang bisa jadi penjual | OCR KTM + NIM matching via `unisa.student` |
| NF2 | Integritas | Dana tidak langsung ke penjual | Sistem Escrow (`unitrade.escrow.ledger`) |
| NF3 | Kerahasiaan | Data sensitif terisolasi per pengguna | `ir.rule` record rules + Role ACL |
| NF4 | Ketersediaan | Sistem tidak crash saat API eksternal gagal | Retry logic + graceful degradation |
| NF5 | Ketersediaan | Idempotency webhook pembayaran | Deduplication via `unitrade.payment.event` |
| NF6 | Skalabilitas | Penambahan modul tanpa merusak fitur lain | Pola `_inherit` Odoo |
| NF7 | Keamanan | API key tidak hardcode di source code | Disimpan di `ir.config_parameter` |
| NF8 | Keamanan | Webhook Midtrans diverifikasi signature SHA-512 | `_validate_midtrans_signature()` |
| NF9 | Audit | Setiap aktivitas keamanan user dicatat | `unitrade.security.activity` |
| NF10 | Privasi | Penghapusan akun menjaga data transaksi | Anonymisasi, bukan hard delete |

---

## Alur Bisnis Utama

### Alur 1: Registrasi & Verifikasi Penjual (Detail)

```
[User membuka /web/signup]
   ↓ (Controller: UnitradeAuthSignup.web_auth_signup)
[Validasi: email valid, tidak di-blacklist, reCaptcha lolos]
   ↓
[Odoo membuat akun user baru (res.users)]
   ↓
[OTP dibuat di tabel unitrade.otp, dikirim via mail.mail ke email]
   ↓ (Redirect ke /web/verify-otp)
[User input OTP] → [Controller validasi OTP]
   ↓ (Jika valid: is_otp_verified = True)
[User bisa login, masuk sebagai Pembeli (base.group_user)]
   ↓ (Klik "Mulai Berjualan")
[User upload foto KTM]
   ↓ (Controller: seller_verification.py)
[Gambar dikirim ke Google Cloud Vision API]
   ↓
[OCR ekstrak teks → cari NIM (regex r'\d{8,12}')}
   ↓
[NIM dicocokkan ke tabel unisa_student (database mahasiswa)]
   ↓
[Nama dari KTM dicocokkan ke nama akun (fuzzy matching)]
   ├── Cocok → Status: APPROVED → User masuk group_unitrade_seller
   ├── Partial → Status: MANUAL_REVIEW → Admin review di dashboard
   └── Tidak cocok → Status: REJECTED → User upload ulang
```

### Alur 2: Transaksi Pembelian (Detail)

```
[Pembeli klik "Tambah ke Keranjang"]
   ↓ (Validasi stok via jsonrpc → /unitrade/product/stock/validate)
[Form checkout: pilih pengiriman, input alamat]
   ↓ (Mapbox geocoding untuk autocomplete alamat)
[Pilih metode pembayaran Midtrans]
   ↓ (Controller: checkout.py → Model: action_create_midtrans_payment)
[POST ke Midtrans API: https://api.sandbox.midtrans.com/v2/charge]
   ↓ (Midtrans response: VA number / QR code)
[Halaman instruksi pembayaran ditampilkan ke pembeli]
   ↓ (Pembeli bayar via bank/e-wallet)
[Midtrans kirim webhook ke /unitrade/payment/midtrans/webhook]
   ↓ (Validasi signature SHA-512)
[Status order: payment_pending → paid_escrow]
[Escrow: state = 'held' — dana ditahan di sistem]
   ↓ (Penjual terima notifikasi, proses & kirim barang)
[Pembeli konfirmasi terima barang]
   ↓
[Escrow: state = 'held' → 'releasable' → 'released']
[Dana dilepas ke saldo penjual]
```

### Alur 3: Customer Service AI (Detail)

```
[Pembeli klik "Bantuan" / "Customer Service"]
   ↓ (Halaman customer-service dibuka)
[Pembeli ketik pesan]
   ↓ (JS kirim via jsonrpc → /customer-service/chat/send)
[Controller meneruskan ke model unitrade.cs.ai.service]
   ↓
[Bangun payload Gemini: system_prompt + 5 riwayat pesan]
   ↓ (POST ke https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent)
[Gemini kembalikan respons teks]
   ↓
[Teks ditampilkan di chat interface]
   ↓ (Jika AI tidak bisa jawab → user klik "Eskalasi ke Admin")
[Controller: /customer-service/chat/escalate]
[Dibuat tiket di unitrade.customer.ticket]
[Admin terima notifikasi di dashboard]
```

---

## Arsitektur Sistem Lengkap

```
┌──────────────────────────────────────────────────────────────────┐
│                     BROWSER (Frontend)                           │
│                                                                  │
│  HTML/QWeb XML Templates (views/*.xml)                           │
│  JavaScript ES6 Modules (static/src/js/*.js)                     │
│    ├── publicWidget (menghubungkan JS ke elemen HTML)            │
│    ├── jsonrpc() (panggilan AJAX ke backend)                     │
│    └── OWL Components (komponen reaktif: notifikasi, filter)     │
│  Tailwind CSS (prefix tw-) via output.css                        │
└────────────────────────┬─────────────────────────────────────────┘
                         │ HTTP/HTTPS (JSON-RPC 2.0 / Form POST)
┌────────────────────────▼─────────────────────────────────────────┐
│              ODOO 17 APPLICATION SERVER (Backend)                │
│                                                                  │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │   Controllers   │  │      Models      │  │  Views/QWeb    │  │
│  │  (HTTP Routes)  │  │  (ORM + Logic)   │  │  (Templates)   │  │
│  └────────┬────────┘  └────────┬─────────┘  └────────────────┘  │
│           │ request.env[...]   │ self.env[...]                   │
│  ┌────────▼────────────────────▼──────────────────────────────┐  │
│  │              PostgreSQL Database                           │  │
│  │   Tables: sale_order, res_users, unitrade_*, ir_*          │  │
│  └────────────────────────────────────────────────────────────┘  │
└───────────────┬──────────────────┬─────────────────┬─────────────┘
                │                  │                 │
  ┌─────────────▼──────┐ ┌─────────▼───────┐ ┌──────▼──────────┐
  │   Midtrans API     │ │ Google Vision   │ │   Gemini AI     │
  │  /v2/charge        │ │   /annotate     │ │ /generateContent │
  │  Webhook Receiver  │ │   (OCR KTM)     │ │  (CS Chatbot)   │
  └────────────────────┘ └─────────────────┘ └─────────────────┘
```
