# 06 — Ketersediaan Sistem & Kerahasiaan Data

---

## A. Ketersediaan Sistem (System Availability)

### 1. Arsitektur Deployment (Docker)

Sistem UniTrade di-deploy menggunakan Docker untuk memastikan isolasi dan portabilitas:

```yaml
# docker-compose.yml (ringkasan)
services:
  odoo:
    image: odoo:17
    depends_on:
      - db
    ports:
      - "8069:8069"
    volumes:
      - ./unitrade_theme:/mnt/extra-addons/unitrade_theme
      - ./unitrade_payment:/mnt/extra-addons/unitrade_payment
      # ... modul lainnya

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: unitrade_db
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

### 2. Session Management Odoo

Odoo mengelola sesi pengguna secara otomatis. Setiap request HTTP yang membutuhkan autentikasi diverifikasi via session cookie:

```python
# Contoh route yang membutuhkan autentikasi
@http.route('/my/wishlist', type='http', auth='user', website=True)
def wishlist_page(self, **kwargs):
    # auth='user': Odoo otomatis redirect ke /web/login jika tidak ada sesi aktif
    items = request.env['unitrade.wishlist'].sudo().search([
        ('user_id', '=', request.env.uid),
    ])
    return request.render('unitrade_wishlist.wishlist_page_template', {'wishlist_items': items})
```

Tingkat `auth` yang tersedia:
| Auth Level | Keterangan |
|------------|-----------|
| `auth='none'` | Semua bisa akses (webhook eksternal) |
| `auth='public'` | Public + user login (halaman produk/shop) |
| `auth='user'` | Harus login (wishlist, profil, checkout) |

### 3. Ketahanan API Call: Retry Logic

Untuk panggilan ke API eksternal (Gemini AI), sistem memiliki retry otomatis agar gangguan sementara tidak membuat fitur mati total:

```python
# unitrade_cs_ai/models/cs_ai_service.py: L96-118
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BACKOFF = 1.2  # detik, naik tiap percobaan

for attempt in range(1, GEMINI_MAX_RETRIES + 1):
    try:
        response = requests.post(url, data=body, headers=headers, timeout=20)
    except requests.RequestException as error:
        if attempt < GEMINI_MAX_RETRIES:
            time.sleep(GEMINI_RETRY_BACKOFF * attempt)  # 1.2s, 2.4s, dst
            continue
        raise UserError(_('Gagal menghubungi layanan AI.')) from error

    # Retry jika server Gemini busy (5xx)
    if response.status_code in (500, 502, 503, 504):
        if attempt < GEMINI_MAX_RETRIES:
            time.sleep(GEMINI_RETRY_BACKOFF * attempt)
            continue
        raise UserError(_('Layanan AI sedang sibuk.'))
    break
```

### 4. Graceful Degradation: OCR Fallback ke Review Manual

Jika Google Vision API gagal, sistem tidak crash. Verifikasi KTM otomatis masuk ke antrian review manual admin:

```python
# unitrade_seller/services/ocr_service.py: L455-461
try:
    raw_text = cls.call_google_vision_api(env, image_bytes)
except Exception as e:
    _logger.exception('[PIPELINE] Google Vision API failed: %s', e)
    # Sistem TIDAK crash, melainkan masuk review manual
    result['reason'] = f'vision_api_failed: {str(e)}'
    result['verification_status'] = 'manual_review'
    return result
```

### 5. Database Transaction Savepoint

Operasi kritis menggunakan savepoint untuk memastikan konsistensi data meskipun terjadi error di tengah proses:

```python
# unitrade_payment/models/sale_order.py: L227-244
for order in orders:
    try:
        with self.env.cr.savepoint():  # Jika error, otomatis rollback
            intent = order._unitrade_repair_payment_intent()
            ledgers = Ledger._create_for_order(order, intent)
            ledgers._sync_order_escrow_state()
    except Exception:
        _logger.exception('Failed to backfill escrow for order %s', order.name)
        # Error pada satu order tidak menghentikan pemrosesan order lain
```

### Contoh Pengujian Ketersediaan
```
Skenario: Midtrans mengirim webhook duplikat (retry 2x)

Expected:
  - Request 1: Diproses → status 'processed' → Response 200 OK
  - Request 2: Terdeteksi duplikat → Response 200 OK {'duplicate': true}
  - Status order: Tidak berubah ganda (idempotent)

Kode yang menjamin ini:
  unitrade_payment/controllers/main.py: L1464-1467
  if existing_event and existing_event.state == 'processed':
      return self._json_response({'status': 'ok', 'duplicate': True})
```

---

## B. Kerahasiaan Data (Data Confidentiality)

### 1. API Key Tidak Pernah Hardcode

Semua credential sensitif disimpan di tabel `ir.config_parameter` (database terenkripsi), bukan di source code:

```python
# Pola yang digunakan di SEMUA integrasi API:

# Midtrans Server Key
server_key = self.env['ir.config_parameter'].sudo().get_param('unitrade.midtrans.server_key')

# Google Vision API Key
api_key = env['ir.config_parameter'].sudo().get_param('unitrade.google_vision.api_key', '')

# Gemini API Key
api_key = self.env['ir.config_parameter'].sudo().get_param('unitrade.gemini.api_key', '')
```

### 2. Pemisahan Data Antar Seller (Record Rules)

Setiap seller hanya bisa mengakses data miliknya sendiri. Odoo secara otomatis menambahkan filter SQL:

```xml
<!-- unitrade_seller/security/security.xml: L33-42 -->
<record id="rule_seller_own" model="ir.rule">
    <field name="name">Seller: Own Record Only</field>
    <field name="model_id" ref="model_unitrade_seller"/>
    <!-- Filter otomatis ditambahkan ke setiap query untuk group Seller -->
    <field name="domain_force">[('user_id', '=', user.id)]</field>
    <field name="groups" eval="[(4, ref('group_unitrade_seller'))]"/>
</record>
```

Efeknya di SQL:
```sql
-- Query Seller A (user.id = 5):
SELECT * FROM unitrade_seller WHERE user_id = 5;

-- Seller A TIDAK BISA mengakses data Seller B (user.id = 7),
-- meskipun mencoba search tanpa domain:
request.env['unitrade_seller'].search([])
-- Tetap hanya mengembalikan data user_id = 5
```

### 3. sudo() Digunakan dengan Bijak

`sudo()` hanya digunakan untuk kasus yang benar-benar diperlukan, bukan sebagai jalan pintas:

```python
# BENAR: sudo() diperlukan karena pembeli tamu (public user) perlu
# melihat stok produk tanpa hak akses admin
product = request.env['product.product'].sudo().browse(int(product_id)).exists()

# BENAR: sudo() diperlukan agar sistem bisa buat notifikasi untuk user lain
notification = self.env['unitrade.notification'].sudo().create({
    'user_id': buyer_id,  # Notifikasi untuk user lain
    'title': 'Pesanan dikonfirmasi',
})

# SALAH (jangan lakukan): sudo() tanpa alasan yang jelas
data = self.env['res.users'].sudo().search([])  # Berbahaya: ekspos semua user
```

### 4. Proteksi Data Pembayaran

Token dan detail transaksi Midtrans disimpan dalam field yang `readonly=True`:

```python
# unitrade_payment/models/sale_order.py: L41-44
x_midtrans_order_id = fields.Char(
    string='Midtrans Order ID',
    readonly=True,  # Tidak bisa diubah manual via UI
    copy=False      # Tidak ikut di-copy jika order di-duplicate
)
x_midtrans_snap_token = fields.Char(
    string='Snap Token',
    readonly=True,
    copy=False
)
```

### 5. Anonimisasi Data saat Penghapusan Akun

Data pribadi user yang menghapus akun tidak dihapus permanen (karena terkait ke histori transaksi), melainkan di-anonymize:

```python
# unitrade_theme/models/res_users.py: L91-110
def unitrade_privacy_deactivate(self, ...):
    for user in self.sudo():
        # Generate referensi acak untuk anonimisasi
        anonymized_ref = 'deleted-user-%s-%s' % (user.id, uuid.uuid4().hex[:10])
        partner = user.partner_id.sudo()
        partner.write({
            'name': 'Pengguna Dihapus',   # Nama dihapus
            'email': False,               # Email dihapus
            'phone': False,               # Nomor HP dihapus
            'mobile': False,
        })
        user.write({
            'active': False,                        # Akun dinonaktifkan
            'x_privacy_anonymized_ref': anonymized_ref,  # Referensi acak
            'x_privacy_deactivated_at': fields.Datetime.now(),
        })
        # Histori pesanan tetap ada namun tidak terhubung ke identitas asli
```

### Contoh Pengujian Kerahasiaan

```
Skenario 1: Seller A mencoba mengakses toko Seller B
  URL: /unitrade/seller/dashboard (auth='user')
  User: Seller A (user.id = 5)
  Expected: Hanya melihat data tokonya sendiri
  Mekanisme: Record Rule domain_force [('user_id', '=', user.id)]

Skenario 2: User biasa mencoba akses halaman admin
  URL: /unitrade/admin
  User: Pembeli biasa (tidak punya group_unitrade_admin)
  Expected: Redirect ke halaman forbidden
  Mekanisme: _is_admin() check → render 'unitrade_admin.admin_forbidden'

Skenario 3: Webhook Midtrans palsu tanpa signature yang benar
  URL: POST /unitrade/payment/midtrans/webhook
  Payload: Tanpa signature_key yang valid
  Expected: HTTP 401 Unauthorized
  Mekanisme: _validate_midtrans_signature() → SHA-512 comparison
```
