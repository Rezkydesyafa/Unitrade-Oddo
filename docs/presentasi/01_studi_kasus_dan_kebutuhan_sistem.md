# 01 — Studi Kasus & Kebutuhan Sistem

## Studi Kasus: UniTrade Marketplace UNISA Yogyakarta

### Latar Belakang Masalah

UniTrade adalah platform marketplace **C2C (Customer-to-Customer)** yang dibangun di atas **Odoo 17** untuk melayani kebutuhan jual-beli di lingkungan Universitas Aisyiyah (UNISA) Yogyakarta.

> **Apa itu C2C?**
> Consumer-to-Consumer = pembeli dan penjual sama-sama adalah individu (mahasiswa),
> bukan bisnis/perusahaan. Berbeda dengan B2C (Tokopedia = perusahaan ke konsumen)
> atau B2B (perusahaan ke perusahaan).

**Masalah yang dipecahkan:**

| # | Masalah | Solusi UniTrade |
|---|---------|----------------|
| 1 | Tidak ada platform jual-beli terverifikasi di kampus | Marketplace khusus mahasiswa UNISA |
| 2 | Siapapun bisa mengklaim sebagai mahasiswa UNISA | Verifikasi KTM via OCR otomatis |
| 3 | Tidak ada perlindungan dana pembeli | Sistem Escrow (dana ditahan sampai barang diterima) |
| 4 | Tidak ada jalur dispute resmi | Sistem refund dengan mediasi admin |
| 5 | Tidak ada customer service yang responsif | AI Chatbot (Gemini 2.5 Flash) |

---

## Komponen Teknologi Utama

```
┌─────────────────────────────────────────────────────────┐
│  ODOO 17  (Platform utama — semua modul berjalan di sini)│
│                                                          │
│  Python 3.12  → Logika bisnis (models, controllers)     │
│  PostgreSQL 15 → Database penyimpanan data               │
│  QWeb XML     → Template halaman web (HTML generator)   │
│  JavaScript   → Interaktivitas di browser                │
│  Tailwind CSS → Styling (prefix tw-)                    │
└─────────────────────────────────────────────────────────┘
         ↕                    ↕                   ↕
  ┌──────────────┐   ┌────────────────┐   ┌────────────────┐
  │   Midtrans   │   │ Google Vision  │   │ Google Gemini  │
  │  (Pembayaran)│   │  (OCR KTM)     │   │  (AI CS Bot)   │
  └──────────────┘   └────────────────┘   └────────────────┘
         ↕
  ┌──────────────┐   ┌────────────────┐
  │   Mapbox     │   │    GoSend      │
  │  (Peta/Alamat│   │  (Pengiriman)  │
  └──────────────┘   └────────────────┘
```

---

## Kebutuhan Sistem Enterprise

### 1. Kebutuhan Fungsional (Functional Requirements)

> **Kebutuhan Fungsional** = Fitur yang HARUS ADA agar sistem bisa digunakan.
> "Sistem harus BISA melakukan apa?"

| Kode | Kebutuhan | Modul Odoo | File Utama |
|------|-----------|-----------|-----------|
| F1 | Registrasi akun dengan validasi email + OTP | `unitrade_theme` | `controllers/controllers.py` |
| F2 | Login Google OAuth (SSO) | `unitrade_theme` | `models/res_users.py` |
| F3 | Verifikasi penjual via KTM (OCR + review manual) | `unitrade_seller` | `services/ocr_service.py` |
| F4 | Listing produk + manajemen toko | `unitrade_seller` | `controllers/main.py` |
| F5 | Filter produk di halaman toko | `unitrade_product_ext` | `controllers/main.py` |
| F6 | Keranjang belanja | `unitrade_theme` | `controllers/cart.py` |
| F7 | Checkout + pemilihan metode pembayaran | `unitrade_theme` | `controllers/checkout.py` |
| F8 | Pembayaran via Midtrans (VA, QRIS, E-Wallet) | `unitrade_payment` | `models/sale_order.py` |
| F9 | Sistem Escrow otomatis | `unitrade_payment` | `models/payment_intent.py` |
| F10 | Pengiriman GoSend + Ambil Sendiri | `unitrade_delivery` | `models/` |
| F11 | Sistem dispute / refund | `unitrade_dispute` | `models/` |
| F12 | Wishlist produk | `unitrade_wishlist` | `controllers/main.py` |
| F13 | Ulasan dan rating produk | `unitrade_review` | `models/` |
| F14 | Notifikasi real-time (polling 60 detik) | `unitrade_notification` | `static/src/js/notification_service.js` |
| F15 | Live chat antar pengguna | `unitrade_chat` | `controllers/` |
| F16 | Customer Service AI (Gemini 2.5 Flash) | `unitrade_cs_ai` | `models/cs_ai_service.py` |
| F17 | Dashboard admin (monitoring, moderasi) | `unitrade_admin` | `models/admin_stats.py` |

### 2. Kebutuhan Non-Fungsional (Non-Functional Requirements)

> **Kebutuhan Non-Fungsional** = BAGAIMANA sistem harus berperilaku.
> "Sistem harus seberapa AMAN? Seberapa CEPAT? Seberapa ANDAL?"

| Kode | Kategori | Kebutuhan | Implementasi |
|------|----------|-----------|--------------|
| NF1 | Keamanan | Hanya mahasiswa UNISA yang bisa jadi penjual | OCR KTM + NIM matching |
| NF2 | Integritas | Dana tidak langsung ke penjual sebelum barang diterima | Sistem Escrow (`unitrade.escrow.ledger`) |
| NF3 | Kerahasiaan | Data terisolasi per pengguna | `ir.rule` record rules + ACL |
| NF4 | Ketersediaan | Sistem tidak crash saat API eksternal gagal | Retry logic + graceful degradation |
| NF5 | Ketersediaan | Idempotency webhook pembayaran | Deduplication via `unitrade.payment.event` |
| NF6 | Skalabilitas | Modul baru tidak merusak fitur lain | Pola `_inherit` Odoo |
| NF7 | Keamanan | API key tidak hardcode di source code | Disimpan di `ir.config_parameter` |
| NF8 | Keamanan | Webhook Midtrans diverifikasi signature | SHA-512 HMAC validation |
| NF9 | Audit | Setiap aktivitas keamanan user dicatat | `unitrade.security.activity` |
| NF10 | Privasi | Penghapusan akun menjaga data transaksi | Anonimisasi, bukan hard delete |

---

## Alur Bisnis Utama (Dengan Kode)

### Alur 1: Registrasi & Verifikasi Penjual

```
[User buka /web/signup]
        │
        ▼
[Controller: UnitradeAuthSignup.web_auth_signup]
  Validasi: email valid? → TIDAK → Error "Masukkan email yang valid"
  Validasi: email di-blacklist? → YA → Error "Email tidak bisa digunakan"
  Validasi: Terms disetujui? → TIDAK → Error "Setujui Syarat Ketentuan"
  Validasi: Google reCaptcha → GAGAL → Error "Suspicious activity"
        │ Semua validasi LULUS
        ▼
[Odoo: do_signup() → buat record baru di tabel res_users]
        │
        ▼
[Model: unitrade.otp.generate_otp()]
  → Buat kode acak 6 digit: random.choices(string.digits, k=6)
  → Simpan ke tabel unitrade_otp dengan expires_at = now + 5 menit
  → Kirim email via mail.mail.send()
        │
        ▼
[Redirect ke /web/verify-otp]
  User input kode OTP dari email
        │
        ▼
[Model: unitrade.otp.verify_otp()]
  Cek: kode benar? is_used=False? belum expired?
  → YA: user.is_otp_verified = True → Login berhasil
  → TIDAK: Error "OTP salah atau kadaluarsa"
        │
        ▼
[User masuk sebagai Pembeli (base.group_user)]
        │ (Klik "Mulai Berjualan")
        ▼
[User upload foto KTM]
  → Foto dikirim ke Google Vision API
  → OCR extract teks
  → Pipeline 5 langkah: keywords → NIM → database → nama → fuzzy match
        ├── Semua lulus → Status: APPROVED → Masuk group_unitrade_seller
        ├── Parsial → Status: MANUAL_REVIEW → Admin review di dashboard
        └── Gagal → Status: REJECTED → Upload ulang
```

### Alur 2: Transaksi Pembelian (dengan Kode)

```python
# ── LANGKAH 1: Pembeli klik "Tambah ke Keranjang" ─────────────────────
# JS: product_detail.js
const result = await jsonrpc('/unitrade/product/stock/validate', {
    product_id: 42,   # ID produk
    add_qty: 1,       # Jumlah yang ditambahkan
})
# Controller cek stok: jika stok cukup → lanjut, jika tidak → tampilkan warning

# ── LANGKAH 2: Checkout ───────────────────────────────────────────────
# Controller checkout.py memanggil:
amounts = order._unitrade_prepare_checkout_server_state()
# → sync harga terkini (mencegah harga stale)
# → hitung ulang service fee
# → validasi stok sekali lagi sebelum bayar

# ── LANGKAH 3: Buat Payment Intent ke Midtrans ────────────────────────
# Model sale_order.py:
status_code, response_payload, _ = self._midtrans_send_charge_request(
    server_key=server_key,
    payload={
        "payment_type": "bank_transfer",
        "transaction_details": {
            "order_id": "UT-2026-001",
            "gross_amount": 76500    # subtotal + service_fee
        }
    }
)
# Midtrans return VA number → ditampilkan ke pembeli

# ── LANGKAH 4: Webhook saat Pembayaran Berhasil ────────────────────────
# Midtrans POST ke /unitrade/payment/midtrans/webhook
# Controller validasi SHA-512 signature
# Update database:
order.write({
    'x_payment_status': 'paid',
    'x_unitrade_order_state': 'paid_escrow',
    'x_escrow_state': 'held',   # Dana ditahan dalam escrow
})
# Notifikasi dikirim ke penjual

# ── LANGKAH 5: Release Escrow setelah Barang Diterima ─────────────────
# Pembeli konfirmasi terima barang → escrow.state = 'releasable'
# Cron job harian melepas dana ke saldo penjual → escrow.state = 'released'
```

---

## Arsitektur Sistem Lengkap

```
┌──────────────────────────────────────────────────────────────────────┐
│                       BROWSER (Frontend)                             │
│                                                                      │
│  HTML dirender dari QWeb XML template (oleh Odoo di server)          │
│  JavaScript ES6 Modules:                                             │
│    ├── publicWidget  → attach JS ke elemen HTML otomatis             │
│    ├── jsonrpc()     → kirim request AJAX ke backend (JSON-RPC 2.0)  │
│    └── fetch()       → kirim request HTTP manual                     │
│  Tailwind CSS (prefix tw-) untuk styling                             │
└────────────────────────────────────┬─────────────────────────────────┘
                                     │ HTTP/HTTPS
                         ┌───────────▼────────────┐
                         │   NGINX (Reverse Proxy) │
                         │   unitrade.web.id:443   │
                         └───────────┬────────────┘
                                     │
                         ┌───────────▼────────────┐
                         │   ODOO 17 (Port 8069)   │
                         │                         │
                         │  Controllers (routing)  │
                         │       ↕                 │
                         │  Models (ORM + logic)   │
                         │       ↕                 │
                         │  PostgreSQL 15 (DB)     │
                         └───────────┬────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          ▼                          ▼                          ▼
  ┌───────────────┐        ┌────────────────┐        ┌─────────────────┐
  │   Midtrans    │        │ Google Vision  │        │  Google Gemini  │
  │  Payment GW   │        │   OCR API      │        │   AI Chatbot    │
  │  sandbox/prod │        │ TEXT_DETECTION │        │ gemini-2.5-flash│
  └───────────────┘        └────────────────┘        └─────────────────┘
          │                                                    
  ┌───────────────┐        ┌────────────────┐
  │    Mapbox     │        │   Docker Hub   │
  │ Geocoding API │        │ (Image Registry│
  └───────────────┘        └────────────────┘
```
