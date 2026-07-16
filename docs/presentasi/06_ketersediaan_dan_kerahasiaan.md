# 06 — Ketersediaan Sistem & Kerahasiaan Data

> **Ketersediaan (Availability):** Sistem tetap bisa diakses meskipun ada gangguan eksternal (API down, server busy, dll).
> **Kerahasiaan (Confidentiality):** Data sensitif hanya bisa diakses oleh pihak yang berwenang.

---

## A. Ketersediaan Sistem (System Availability)

### 1. Arsitektur Deployment (Docker)

UniTrade berjalan dalam **container Docker** untuk memastikan:
- **Isolasi** → Odoo dan PostgreSQL berjalan di lingkungan terpisah, tidak saling mengganggu
- **Portabilitas** → Bisa dijalankan di VPS manapun dengan perintah yang sama
- **Reprodusibilitas** → Lingkungan development = lingkungan production (tidak ada "works on my machine")

```yaml
# docker-compose.yml (ringkasan struktur)

services:
  odoo:
    image: odoo:17
    # Gambar Docker resmi Odoo versi 17
    
    depends_on:
      - db
    # Odoo tidak akan start sebelum container db siap
    # Mencegah error "database not found" saat startup
    
    ports:
      - "8069:8069"
    # Format: "HOST_PORT:CONTAINER_PORT"
    # Traffic ke port 8069 VPS diteruskan ke port 8069 di dalam container
    
    volumes:
      - ./unitrade_theme:/mnt/extra-addons/unitrade_theme
      - ./unitrade_payment:/mnt/extra-addons/unitrade_payment
    # Volume mount: folder kode kita → folder modul Odoo di dalam container
    # Perubahan kode langsung terlihat tanpa rebuild image

  db:
    image: postgres:15
    # PostgreSQL versi 15 sebagai database
    
    environment:
      POSTGRES_DB: unitrade_db       # Nama database yang dibuat otomatis
      POSTGRES_USER: odoo            # Username database
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      # Password diambil dari environment variable (file .env)
      # TIDAK pernah ditulis langsung di docker-compose.yml
    
    volumes:
      - postgres_data:/var/lib/postgresql/data
    # Volume persisten → data database tidak hilang saat container restart
```

**Alur CI/CD Deployment (dari `.github/workflows/deploy-dev.yml`):**
```
1. git push → branch main
      ↓
2. GitHub Actions: Build Docker image baru
   → docker build -t baristasigma/unitrade-app:latest .
      ↓
3. Push image ke Docker Hub (registry publik)
   → baristasigma/unitrade-app:latest
      ↓
4. SSH ke VPS, pull image terbaru
   → docker compose pull
      ↓
5. Jalankan odoo -u (upgrade modul)
   → Terapkan perubahan database (schema baru, data baru)
      ↓
6. Restart container dengan image baru
   → docker compose up -d --force-recreate
      ↓
7. Health check: curl http://127.0.0.1:8069/web/login
   → Pastikan Odoo sudah merespons
      ↓
8. Verify domain: curl https://unitrade.web.id/web/login
   → Konfirmasi domain publik online
```

---

### 2. Session Management Odoo (Autentikasi HTTP)

Odoo mengelola sesi pengguna otomatis via **session cookie**. Setiap HTTP request diverifikasi sebelum controller dijalankan.

```python
# Contoh: Route yang membutuhkan autentikasi

@http.route('/my/wishlist', type='http', auth='user', website=True)
def wishlist_page(self, **kwargs):
    """
    auth='user' artinya:
    → Odoo memeriksa apakah ada session cookie yang valid di request
    → Jika YA  → lanjutkan, set request.env.uid = ID user yang login
    → Jika TIDAK → redirect otomatis ke /web/login
    
    Developer tidak perlu menulis kode cek sesi sendiri,
    Odoo sudah menanganinya di level middleware.
    """
    items = request.env['unitrade.wishlist'].sudo().search([
        ('user_id', '=', request.env.uid),
        # request.env.uid = ID user yang sedang login (dari session cookie)
    ])
    return request.render('unitrade_wishlist.wishlist_page_template', {'wishlist_items': items})
```

**Tiga tingkat autentikasi route di Odoo:**

| `auth=` | Siapa yang boleh akses | Contoh penggunaan |
|---------|----------------------|-------------------|
| `'none'` | Semua orang (termasuk server eksternal) | Webhook Midtrans |
| `'public'` | Pengunjung + user login | Halaman produk, shop |
| `'user'` | Hanya user yang sudah login | Wishlist, profil, checkout |

---

### 3. Ketahanan API Call: Retry Logic (Gemini AI)

API eksternal bisa lambat atau down sewaktu-waktu. Sistem **tidak langsung gagal** — ada percobaan ulang otomatis.

```python
# unitrade_cs_ai/models/cs_ai_service.py: L96-118

GEMINI_MAX_RETRIES = 3       # Coba maksimal 3 kali sebelum menyerah
GEMINI_RETRY_BACKOFF = 1.2   # Jeda awal antar percobaan (detik)

for attempt in range(1, GEMINI_MAX_RETRIES + 1):
    # attempt = 1 (pertama), 2 (kedua), 3 (ketiga)
    
    try:
        response = requests.post(url, data=body, headers=headers, timeout=20)
        # timeout=20 → jika tidak ada respons dalam 20 detik, lempar exception
        
    except requests.RequestException as error:
        # Error koneksi: timeout, DNS gagal, koneksi terputus, dll
        
        if attempt < GEMINI_MAX_RETRIES:
            time.sleep(GEMINI_RETRY_BACKOFF * attempt)
            # attempt=1 → tunggu 1.2 detik sebelum coba lagi
            # attempt=2 → tunggu 2.4 detik sebelum coba lagi
            # Jeda semakin lama agar server punya waktu recovery
            continue   # Kembali ke awal loop
        
        # Sudah 3x gagal → tampilkan pesan error ke user
        raise UserError(_('Gagal menghubungi layanan AI.')) from error

    # Cek apakah server Gemini sedang sibuk (HTTP 5xx)
    if response.status_code in (500, 502, 503, 504):
        # 500 = Internal Server Error
        # 502 = Bad Gateway
        # 503 = Service Unavailable (paling sering terjadi saat peak load)
        # 504 = Gateway Timeout
        if attempt < GEMINI_MAX_RETRIES:
            time.sleep(GEMINI_RETRY_BACKOFF * attempt)
            continue   # Coba lagi
        raise UserError(_('Layanan AI sedang sibuk.'))
    
    break  # Request sukses → keluar dari loop retry

# Di luar loop: response sudah berhasil, lanjut proses data
```

**Visualisasi alur retry:**
```
Attempt 1 → Error 503
  Tunggu 1.2 detik
Attempt 2 → Error 503
  Tunggu 2.4 detik
Attempt 3 → Sukses 200 ✅
  → Proses respons Gemini
```

---

### 4. Graceful Degradation: OCR Fallback ke Review Manual

Jika Google Vision API gagal, sistem **tidak crash** — verifikasi KTM otomatis masuk ke antrian review manual admin. Ini adalah pola **fail-safe**.

```python
# unitrade_seller/services/ocr_service.py: L455-461

try:
    # Coba panggil Google Vision API
    raw_text = cls.call_google_vision_api(env, image_bytes)

except Exception as e:
    # Jika API gagal karena alasan apapun:
    # - Quota Google habis
    # - Jaringan terputus
    # - API key tidak valid
    # - Google down (maintenance)
    
    _logger.exception('[PIPELINE] Google Vision API failed: %s', e)
    # Catat error ke log Odoo untuk keperluan debugging
    # _logger.exception() otomatis menyertakan full stack trace
    
    # TIDAK crash, TIDAK throw exception ke user
    # Kembalikan status yang aman: masuk antrian review manual
    result['reason'] = f'vision_api_failed: {str(e)}'
    result['verification_status'] = 'manual_review'
    return result
    # Admin akan melihat pengajuan ini di dashboard dan review secara manual
```

**Perbandingan: Tanpa vs Dengan Graceful Degradation**

| | Tanpa Graceful Degradation | Dengan Graceful Degradation |
|-|---------------------------|----------------------------|
| Google Vision down | User dapat error 500 | User dapat notif "dalam review" |
| Data verification | Hilang / rusak | Tetap tersimpan, antri manual |
| Pengalaman user | Buruk, frustrasi | Tetap bisa lanjut proses |
| Kerja admin | Tidak bisa diaudit | Bisa dilihat di dashboard |

---

### 5. Database Transaction Savepoint (Operasi Kritis)

Untuk operasi yang melibatkan banyak langkah (backfill escrow, dsb), menggunakan **savepoint** agar error pada satu item tidak membatalkan item lain.

```python
# unitrade_payment/models/sale_order.py: L227-244

for order in orders:
    # Setiap order diproses dalam savepoint TERPISAH
    
    try:
        with self.env.cr.savepoint():
            """
            Savepoint = checkpoint di dalam transaksi database.
            
            Berbeda dengan transaksi biasa:
            - Transaksi biasa: jika error → SEMUA perubahan dibatalkan (rollback total)
            - Savepoint: jika error → hanya perubahan DALAM savepoint ini yang dibatalkan
                         perubahan di luar savepoint (order sebelumnya) tetap tersimpan
            
            Analogi: seperti save game di tengah permainan.
            Jika mati di area berikutnya, kembali ke save point,
            bukan ke awal permainan.
            """
            intent = order._unitrade_repair_payment_intent()
            # Cek/buat payment intent jika belum ada
            
            ledgers = Ledger._create_for_order(order, intent)
            # Buat escrow ledger untuk order ini
            
            ledgers._sync_order_escrow_state()
            # Sinkronkan status escrow ke tabel sale_order
            
            # ✅ Jika semua langkah sukses → savepoint "commit"
            # (data tersimpan permanen untuk order ini)

    except Exception:
        # ❌ Jika ada error di langkah manapun:
        # → Savepoint untuk order ini di-rollback (batalkan perubahan)
        # → Log error untuk debugging
        _logger.exception('Failed to backfill escrow for order %s', order.name)
        # → Lanjut ke order BERIKUTNYA (tidak berhenti total)
```

---

### Contoh Skenario Pengujian Ketersediaan

```
═══════════════════════════════════════════════════════════════
SKENARIO 1: Midtrans mengirim webhook duplikat (retry otomatis)
═══════════════════════════════════════════════════════════════

Penyebab: Midtrans tidak menerima respons dari server kita
          (koneksi putus sesaat) → Midtrans kirim ulang webhook
          yang sama.

Request pertama:
  POST /unitrade/payment/midtrans/webhook
  Body: {"order_id": "UT-001", "transaction_status": "settlement"}
  
  → event_key = "midtrans:UT-001:settlement" belum ada di DB
  → Diproses: order.x_payment_status = 'paid'
  → event.state = 'processed'
  → Respons: {"status": "ok"}

Request kedua (duplikat):
  POST /unitrade/payment/midtrans/webhook
  Body: {"order_id": "UT-001", "transaction_status": "settlement"}
  
  → event_key = "midtrans:UT-001:settlement" SUDAH ADA di DB dengan state='processed'
  → Skip pemrosesan (idempotent)
  → Respons: {"status": "ok", "duplicate": true}
  → Status order: TIDAK berubah (tetap 'paid', tidak diproses dua kali)

Kode yang menjamin idempotency:
  # unitrade_payment/controllers/main.py: L1464-1467
  if existing_event and existing_event.state == 'processed':
      return self._json_response({'status': 'ok', 'duplicate': True})

═══════════════════════════════════════════════════════════════
SKENARIO 2: Gemini AI tidak merespons (timeout)
═══════════════════════════════════════════════════════════════

Attempt 1: POST ke Gemini → Timeout setelah 20 detik
  → Tunggu 1.2 detik
Attempt 2: POST ke Gemini → HTTP 503 (Service Unavailable)
  → Tunggu 2.4 detik
Attempt 3: POST ke Gemini → HTTP 200 OK ✅
  → Proses respons, tampilkan jawaban ke user

Hasil: User mungkin menunggu ~24 detik, tapi tetap mendapat jawaban.
```

---

## B. Kerahasiaan Data (Data Confidentiality)

### 1. API Key Tidak Pernah Hardcode

```python
# Pola yang SAMA digunakan di SEMUA integrasi API:

# ── Midtrans Server Key ───────────────────────────────────────────────────
server_key = self.env['ir.config_parameter'].sudo().get_param(
    'unitrade.midtrans.server_key'  # Nama kunci di database
)
# Digunakan untuk: Basic Auth ke Midtrans API + validasi signature webhook

# ── Google Vision API Key ─────────────────────────────────────────────────
api_key = env['ir.config_parameter'].sudo().get_param(
    'unitrade.google_vision.api_key', ''  # '' = default jika belum diisi
)
# Digunakan untuk: Query parameter di URL Google Vision

# ── Gemini API Key ────────────────────────────────────────────────────────
api_key = self.env['ir.config_parameter'].sudo().get_param(
    'unitrade.gemini.api_key', ''
)
# Digunakan untuk: Query parameter di URL Gemini

# ── Mapbox Token ─────────────────────────────────────────────────────────
token = request.env['ir.config_parameter'].sudo().get_param(
    'unitrade.mapbox_access_token'
)
# Digunakan untuk: Proxy request geocoding (token tidak sampai ke browser)
```

**Mengapa ini penting?**
```
Source code UniTrade ada di GitHub (public/private repository).
Jika API key ditulis langsung di kode:
  → Siapapun yang melihat kode bisa menggunakan key tersebut
  → Key bisa ter-leak ke git history, bahkan setelah dihapus
  → Biaya API akan ditanggung oleh pemilik key (financial risk)

Dengan ir.config_parameter:
  → Key hanya ada di database production (server VPS)
  → Tidak ada di source code, tidak ada di git
  → Admin bisa rotate key kapan saja dari panel admin
  → Key berbeda untuk environment berbeda (dev/staging/production)
```

---

### 2. Pemisahan Data Antar Seller (Record Rules)

Record Rules adalah **filter SQL otomatis** yang ditambahkan Odoo ke setiap query berdasarkan user yang sedang login.

```xml
<!-- unitrade_seller/security/security.xml: L33-42 -->

<record id="rule_seller_own" model="ir.rule">
    <field name="name">Seller: Own Record Only</field>
    <field name="model_id" ref="model_unitrade_seller"/>
    <!--
        domain_force = filter yang SELALU ditambahkan ke query
        untuk user dalam group ini.
        
        user.id = variabel built-in = ID user yang sedang login
        
        Artinya: WHERE user_id = [ID_USER_YANG_LOGIN]
    -->
    <field name="domain_force">[('user_id', '=', user.id)]</field>
    
    <!--
        (4, ref('group_unitrade_seller')) = tambahkan group Seller
        ke record rule ini. Hanya berlaku untuk user dalam group Seller.
    -->
    <field name="groups" eval="[(4, ref('group_unitrade_seller'))]"/>
</record>
```

**Efek nyata di SQL yang dieksekusi:**

```sql
-- Seller A (user.id = 5) menjalankan:
-- request.env['unitrade.seller'].search([])
-- Kelihatannya tanpa filter, tapi SQL yang benar-benar berjalan:

SELECT id, name, nim, status, ...
FROM unitrade_seller
WHERE user_id = 5          -- ← Record Rule ditambahkan otomatis oleh Odoo
  AND active = true
ORDER BY id;

-- Seller A TIDAK AKAN PERNAH melihat data Seller B (user.id = 7)
-- meskipun kodenya tidak menulis filter apapun.
-- Keamanan bekerja di level ORM, bukan level controller.
```

```python
# Demonstrasi di kode Python:

# Kode ini dijalankan oleh Seller A (user.id = 5):
all_shops = request.env['unitrade.seller'].search([])  # tanpa filter
# → Odoo otomatis tambahkan WHERE user_id = 5
# → Hasilnya: HANYA toko milik Seller A

# Kode ini dijalankan oleh Admin (group_unitrade_admin):
all_shops = request.env['unitrade.seller'].search([])  # tanpa filter
# → Admin punya rule: domain_force = [(1, '=', 1)] = tidak ada filter
# → Hasilnya: SEMUA toko dari semua seller
```

---

### 3. `sudo()` Digunakan dengan Bijak dan Alasan Jelas

`sudo()` membypass SEMUA record rules dan ACL. Harus digunakan hanya ketika benar-benar perlu.

```python
# ✅ CONTOH PENGGUNAAN BENAR:

# Kasus 1: Baca konfigurasi sistem (ir.config_parameter hanya bisa dibaca admin)
server_key = self.env['ir.config_parameter'].sudo().get_param('unitrade.midtrans.server_key')
# sudo() diperlukan agar non-admin bisa membaca parameter yang dibutuhkan sistem.

# Kasus 2: Buat notifikasi untuk user LAIN
# (creator notifikasi ≠ penerima notifikasi)
notification = self.env['unitrade.notification'].sudo().create({
    'user_id': buyer_id,   # Notifikasi untuk user lain, bukan self.env.uid
    'title': 'Pesanan dikonfirmasi',
})
# Tanpa sudo(), Odoo akan cek: apakah env.user berhak buat notif untuk buyer_id?
# Karena sistem yang buat (bukan user sendiri), sudo() diperlukan.

# Kasus 3: Webhook handler (auth='none', tidak ada user session)
intent = request.env['unitrade.payment.intent'].sudo().search(
    [('midtrans_order_id', '=', order_id)], limit=1
)
# auth='none' → request.env.uid = public user yang tidak punya hak akses
# sudo() diperlukan agar bisa query tabel payment intent


# ❌ CONTOH PENGGUNAAN SALAH:

# SALAH: Menggunakan sudo() untuk menghindari error akses tanpa memahami kenapa
data = self.env['res.users'].sudo().search([])
# → BERBAHAYA: Mengekspos SEMUA data user tanpa filter apapun
# → Gunakan search([('id', '=', request.env.uid)]) untuk data sendiri
# → Biarkan record rule bekerja secara normal tanpa sudo()
```

---

### 4. Proteksi Field Data Sensitif

Field yang menyimpan data sensitif dibuat `readonly=True` agar tidak bisa diubah manual via UI Odoo backend.

```python
# unitrade_payment/models/sale_order.py: L41-44

x_midtrans_order_id = fields.Char(
    string='Midtrans Order ID',
    readonly=True,
    # readonly=True pada field Char/Integer/dll:
    # → Tidak bisa diubah via form view Odoo backend
    # → Tetap bisa diubah via kode Python (write()) yang sudah tervalidasi
    # → Mencegah admin tidak sengaja mengubah ID transaksi yang penting
    copy=False
    # copy=False: field ini TIDAK ikut ter-copy saat record di-duplicate
    # Penting: setiap order harus punya Midtrans ID yang unik
)

x_midtrans_snap_token = fields.Char(
    string='Snap Token',
    readonly=True,   # Token Midtrans tidak boleh diubah manual
    copy=False       # Tidak boleh di-copy (token beda per transaksi)
)

x_payment_status = fields.Selection([
    ('pending', 'Menunggu'),
    ('paid', 'Dibayar'),
    ('expired', 'Kadaluarsa'),
], default='pending',
   readonly=True,    # Status pembayaran hanya bisa diubah oleh sistem
                     # (webhook handler), bukan manual oleh user/admin
   tracking=True     # Odoo otomatis catat setiap perubahan status di chatter
)
```

---

### 5. Anonimisasi Data Saat Penghapusan Akun (GDPR-style)

Ketika user menghapus akun, data personal dihapus tapi histori transaksi tetap ada (untuk keperluan akuntansi dan audit).

```python
# unitrade_theme/models/res_users.py: L91-135

def unitrade_privacy_deactivate(self, reason=False, ip_address=False, ...):
    """
    Penghapusan akun dengan prinsip Privacy by Design.
    
    PRINSIP: Data MINIMUM yang disimpan setelah penghapusan.
    
    YANG DIHAPUS (data identitas personal):
    - Nama lengkap → diganti 'Pengguna Dihapus'
    - Email → dihapus (None/False)
    - Nomor HP → dihapus
    - Foto profil → dihapus
    - Alamat → dihapus
    
    YANG DIPERTAHANKAN (data transaksi untuk akuntabilitas):
    - Riwayat pesanan (sale.order) → tetap ada, tapi partner sudah anonim
    - Data escrow (unitrade.escrow.ledger) → tetap ada untuk audit keuangan
    - Nomor tiket CS (unitrade.customer.ticket) → tetap ada untuk arsip
    """
    for user in self.sudo():
        # Buat kode acak unik sebagai penanda bahwa akun ini pernah ada
        # Format: 'deleted-user-42-a3f9d2c1b8'
        anonymized_ref = 'deleted-user-%s-%s' % (user.id, uuid.uuid4().hex[:10])
        # uuid.uuid4() = ID acak yang hampir mustahil duplikat
        # .hex[:10]    = ambil 10 karakter pertama (cukup unik)

        partner = user.partner_id.sudo()
        partner.write({
            'name': 'Pengguna Dihapus',   # Nama generik, tidak mengidentifikasi
            'email': False,                # False di Odoo = NULL di PostgreSQL
            'phone': False,
            'mobile': False,
            'street': False,               # Alamat dihapus
            'street2': False,
            'city': False,
            'image_1920': False,           # Foto profil dihapus
        })
        # Setelah ini, tabel sale_order masih ada dengan partner_id yang sama,
        # tapi partner tersebut sekarang bernama 'Pengguna Dihapus' tanpa email.

        user.write({
            'active': False,
            # active=False = soft delete di Odoo
            # Record tidak benar-benar dihapus dari DB, tapi tidak muncul di query biasa
            # (kecuali search dengan domain ('active', 'in', [True, False]))
            
            'x_privacy_anonymized_ref': anonymized_ref,
            # Simpan referensi acak untuk keperluan audit internal
            # (tahu bahwa akun ini sudah dihapus, tanpa tahu siapa orangnya)
            
            'x_privacy_deactivated': True,
            'x_privacy_deactivated_at': fields.Datetime.now(),
            # Timestamp penghapusan untuk keperluan audit
        })

        # Catat event penghapusan ke audit trail keamanan
        self.env['unitrade.security.activity'].sudo().record_activity(
            user,
            'deactivate_anonymize',           # Tipe event
            title='Akun dinonaktifkan dan dianonimisasi',
            detail='Pengguna menghapus akun atas permintaan sendiri.',
            ip_address=ip_address,            # IP saat penghapusan (untuk forensik)
        )
```

---

### Skenario Pengujian Kerahasiaan

```
═══════════════════════════════════════════════════════════════
SKENARIO 1: Seller A mencoba mengakses data Seller B
═══════════════════════════════════════════════════════════════

URL: GET /unitrade/seller/dashboard
User: Seller A (user.id = 5)
Aksi: request.env['unitrade.seller'].search([])

Mekanisme: Record Rule domain_force [('user_id', '=', user.id)]
SQL yang dijalankan: SELECT * FROM unitrade_seller WHERE user_id = 5

Hasil: ✅ Seller A hanya melihat data tokonya sendiri.
       Data Seller B (user_id = 7) tidak pernah dikembalikan
       meskipun kode tidak menulis filter apapun.

═══════════════════════════════════════════════════════════════
SKENARIO 2: User biasa mencoba akses halaman admin
═══════════════════════════════════════════════════════════════

URL: GET /unitrade/admin
User: Pembeli biasa (tidak punya group_unitrade_admin)
Expected: Halaman forbidden ditampilkan

Kode pengaman:
  # unitrade_admin/controllers/admin_dashboard.py: L12-22
  def _is_admin(self):
      user = request.env.user
      return (
          user.has_group('base.group_system') or
          user.has_group('unitrade_seller.group_unitrade_admin')
      )

  @http.route('/unitrade/admin', auth='user', website=True)
  def admin_dashboard(self, **kwargs):
      if not self._is_admin():           # ← Cek role admin
          return self._forbidden('Tidak ada akses admin.')  # ← Tampilkan forbidden
      # ... render dashboard hanya jika admin

Hasil: ✅ User biasa mendapat halaman "Akses Ditolak",
       bukan error 500 atau data admin yang bocor.

═══════════════════════════════════════════════════════════════
SKENARIO 3: Webhook palsu tanpa signature yang benar
═══════════════════════════════════════════════════════════════

URL: POST /unitrade/payment/midtrans/webhook
Payload: {"order_id": "UT-001", "transaction_status": "settlement",
          "signature_key": "abc123_palsu"}

Proses validasi:
  raw = "UT-001" + "200" + "75000.00" + server_key_asli
  expected = SHA512(raw) = "a3f9d2c1..." (64 karakter hex)
  
  "abc123_palsu" != "a3f9d2c1..."  → TIDAK COCOK

Hasil: ✅ HTTP 401 Unauthorized dikembalikan.
       Status order TIDAK berubah.
       Tidak ada dana yang dianggap masuk.

═══════════════════════════════════════════════════════════════
SKENARIO 4: Mapbox token tidak sampai ke browser
═══════════════════════════════════════════════════════════════

Masalah: Jika Mapbox token ada di JavaScript browser, user bisa
         copy token dan menggunakannya untuk keperluan lain
         (melampaui quota, menyalahgunakan).

Solusi UniTrade: Backend sebagai proxy
  1. Browser kirim query: POST /unitrade/mapbox/geocode {"query": "Jl. Padjajaran"}
  2. Controller Python ambil token dari database (tidak dikirim ke browser)
  3. Controller POST ke Mapbox API menggunakan token tersebut
  4. Hasil geocoding dikembalikan ke browser (tanpa token)

Kode proxy:
  # unitrade_theme/controllers/controllers.py: L741-804
  def unitrade_mapbox_geocode(self, query=None, ...):
      token = request.env['ir.config_parameter'].sudo().get_param(
          'unitrade.mapbox_access_token'  # Token ada di server, tidak di browser
      )
      response = requests.get(mapbox_url, params={'access_token': token, ...})
      return {'success': True, 'features': [...]}  # Token tidak ikut dikembalikan

Hasil: ✅ Browser hanya melihat hasil geocoding,
       TIDAK pernah melihat token Mapbox.
