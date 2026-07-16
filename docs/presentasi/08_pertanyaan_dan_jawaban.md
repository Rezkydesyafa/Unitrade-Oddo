# 08 — Pertanyaan yang Mungkin Ditanyakan & Jawaban Detail

---

## BAGIAN A: Integrasi Sistem

### Q1: Bagaimana modul-modul UniTrade bisa saling berkomunikasi?

**Jawaban:** Komunikasi antar modul di Odoo menggunakan **Odoo Environment (`env`)** sebagai perantara. Setiap modul dapat mengakses model dari modul lain menggunakan `self.env['nama.model']` atau `request.env['nama.model']`.

```python
# Contoh nyata: unitrade_theme/models/customer_service.py
# Modul unitrade_THEME memanggil model dari modul unitrade_NOTIFICATION

def _emit_customer_notification(self, event_code, title, message):
    # Langkah 1: Cek apakah modul lain terinstall (aman dari error)
    if 'unitrade.notification' not in self.env.registry:
        return  # Modul notifikasi belum ada, skip saja

    # Langkah 2: Akses model dari modul lain
    Notification = self.env['unitrade.notification'].sudo()

    # Langkah 3: Panggil metode di model modul lain
    Notification.emit(
        user_id=self.user_id.id,
        event_code=event_code,
        payload={'action_url': self._customer_ticket_url()},
        channels=['in_app'],
    )
```

**Pattern kunci:** `'nama.model' not in self.env.registry` = cara aman mengecek apakah modul lain aktif.

---

### Q2: Bagaimana dependency antar modul dikelola?

```python
# unitrade_payment/__manifest__.py
{
    'depends': [
        'website_sale',      # Modul cart & checkout Odoo
        'unitrade_theme',    # Harus ada unitrade_theme dulu
        'unitrade_seller',   # Harus ada seller untuk escrow
    ],
}
```

Odoo memastikan modul di `depends` sudah terinstall sebelum modul ini. Jika `unitrade_seller` belum ada, `unitrade_payment` **tidak bisa di-install**.

---

### Q3: Bagaimana jika satu modul mengubah perilaku modul lain?

Menggunakan pola **`_inherit` + `super()`**:

```python
# unitrade_payment/models/sale_order.py
class SaleOrderUniTrade(models.Model):
    _inherit = 'sale.order'  # Extend model bawaan Odoo

    def action_confirm(self):
        """Override: tambah logika escrow SETELAH konfirmasi standar Odoo."""
        # Panggil method asli dari Odoo core dulu
        res = super(SaleOrderUniTrade, self).action_confirm()

        # Tambahkan logika kustom UniTrade
        self._unitrade_setup_escrow()
        self._unitrade_notify_seller_new_order()
        return res
```

Odoo menggunakan **MRO (Method Resolution Order)** Python — semua `_inherit` dari modul berbeda dirantai sehingga semuanya dieksekusi berurutan.

---

## BAGIAN B: Integrasi API Eksternal

### Q4: Bagaimana cara UniTrade terhubung ke Midtrans?

**Alur lengkap:**
```
1. Pembeli klik "Bayar"
2. JS kirim POST ke /unitrade/checkout/process (tipe http)
3. Controller checkout.py panggil order.action_create_midtrans_payment()
4. Model sale_order.py ambil server_key dari ir.config_parameter
5. Model buat payload JSON sesuai format Midtrans
6. POST ke https://api.sandbox.midtrans.com/v2/charge (Basic Auth)
7. Midtrans return VA number/QR code
8. Controller simpan data ke unitrade.payment.intent
9. Redirect ke halaman instruksi pembayaran
```

**Kode koneksi aktual:**
```python
# unitrade_payment/models/sale_order.py: L904-919
def _midtrans_send_charge_request(self, server_key, payload):
    # server_key diambil dari database (TIDAK hardcode)
    response = requests.post(
        self._midtrans_api_base_url() + '/v2/charge',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        },
        auth=(server_key, ''),  # Midtrans pakai Basic Auth: server_key:''
        timeout=30,
    )
    return response.status_code, response.json(), response.text
```

---

### Q5: Kenapa ada webhook di Midtrans? Bagaimana cara kerjanya?

**Webhook** = Midtrans yang menghubungi server UniTrade (bukan sebaliknya) ketika status pembayaran berubah (dibayar, expired, gagal).

```python
# unitrade_payment/controllers/main.py: L1450-1531
@http.route('/unitrade/payment/midtrans/webhook',
            type='http', auth='none', csrf=False, methods=['POST'])
def midtrans_webhook(self, **kwargs):
    """
    Endpoint ini TIDAK memerlukan user login (auth='none')
    karena yang memanggil adalah server Midtrans, bukan browser user.
    CSRF juga dinonaktifkan karena request datang dari server eksternal.
    """
    body = request.httprequest.get_data() or b''
    payload = json.loads(body.decode('utf-8'))

    # KEAMANAN: Verifikasi signature dulu sebelum proses apapun
    if not self._validate_midtrans_signature(payload):
        return self._json_response({'status': 'error'}, status=401)

    # IDEMPOTENCY: Cek apakah webhook ini sudah pernah diproses
    event_key = 'midtrans:%s:%s' % (payload.get('order_id'), payload.get('transaction_status'))
    existing = request.env['unitrade.payment.event'].sudo().search(
        [('event_key', '=', event_key)], limit=1
    )
    if existing and existing.state == 'processed':
        return self._json_response({'status': 'ok', 'duplicate': True})

    # Proses webhook: update status order di database
    status = self._normalize_midtrans_status(payload)
    if status == 'paid':
        intent.sale_order_id.sudo()._unitrade_mark_midtrans_paid(intent, payload)

    return self._json_response({'status': 'ok'})
```

**Kenapa perlu idempotency?** Midtrans kadang mengirim webhook yang sama **dua kali** karena network retry. Tanpa deduplication, order bisa ditandai "paid" dua kali.

---

### Q6: Bagaimana signature Midtrans divalidasi?

```python
# unitrade_payment/controllers/main.py: L1285-1301
def _validate_midtrans_signature(self, payload):
    """
    Midtrans menggunakan SHA-512 HMAC untuk membuktikan webhook asli dari mereka.
    Formula: SHA512(order_id + status_code + gross_amount + server_key)
    """
    server_key = self._get_midtrans_param('unitrade.midtrans.server_key')
    signature = payload.get('signature_key')

    raw = '%s%s%s%s' % (
        payload.get('order_id') or '',
        payload.get('status_code') or '',
        payload.get('gross_amount') or '',
        server_key,  # Server key hanya diketahui Midtrans dan UniTrade
    )
    expected = hashlib.sha512(raw.encode('utf-8')).hexdigest()
    # Jika signature tidak cocok = webhook palsu, tolak
    return str(signature).lower() == expected.lower()
```

---

### Q7: Bagaimana Google Vision API dipanggil? Apa yang dikirim?

```python
# unitrade_seller/services/ocr_service.py: L35-97
@staticmethod
def call_google_vision_api(env, image_bytes):
    # 1. API key dari database (TIDAK hardcode)
    api_key = env['ir.config_parameter'].sudo().get_param('unitrade.google_vision.api_key')

    # 2. Encode gambar ke Base64 (format yang diterima Google)
    encoded_image = base64.b64encode(image_bytes).decode('utf-8')

    # 3. Payload request ke Google Vision
    payload = {
        "requests": [{
            "image": {"content": encoded_image},  # Gambar dalam Base64
            "features": [{"type": "TEXT_DETECTION"}]  # Minta deteksi teks
        }]
    }

    # 4. POST ke endpoint Google Cloud Vision
    response = requests.post(
        f"https://vision.googleapis.com/v1/images:annotate?key={api_key}",
        json=payload,
        timeout=30
    )

    # 5. Ambil teks hasil OCR
    data = response.json()
    full_text = data['responses'][0]['textAnnotations'][0]['description']
    return full_text.replace('\n', ' ').strip()
```

**Apa yang terjadi setelah teks di-extract?**
1. Regex mencari NIM: `re.compile(r'\d{8,12}')` → cari angka 8-12 digit
2. Keyword KTM divalidasi: `['KARTU', 'MAHASISWA', 'UNISA', 'NIM', 'FAKULTAS', ...]`
3. NIM dicocokkan ke tabel `unisa_student` di PostgreSQL
4. Nama dicocokkan menggunakan `SequenceMatcher` (fuzzy matching)

---

### Q8: Bagaimana Gemini AI menjaga konteks percakapan?

```python
# unitrade_cs_ai/models/cs_ai_service.py: L60-73
AI_HISTORY_LIMIT = 5  # Hanya 5 pesan terakhir yang dikirim ke Gemini

def _build_contents(self, session, user_message):
    """Bangun array konteks untuk Gemini dari riwayat pesan."""

    # Ambil 5 pesan terakhir dari database
    history = session.message_ids.sorted('id')[-AI_HISTORY_LIMIT:]

    contents = []
    for message in history:
        # Gemini menggunakan 'user' dan 'model' sebagai role
        role = 'user' if message.author_type == 'user' else 'model'
        contents.append({
            'role': role,
            'parts': [{'text': message.body or ''}]
        })

    # Pastikan pesan terbaru user ada di akhir
    if not contents or contents[-1]['role'] != 'user':
        contents.append({'role': 'user', 'parts': [{'text': user_message}]})

    return contents

def generate_reply(self, session, user_message):
    payload = {
        # System prompt: menentukan "karakter" AI sebagai CS UniTrade
        'system_instruction': {
            'parts': [{'text': 'Kamu adalah asisten Customer Service UniTrade...'}]
        },
        # Konteks percakapan (5 pesan terakhir + pesan baru)
        'contents': self._build_contents(session, user_message),
        'generationConfig': {
            'temperature': 0.4,       # 0 = deterministik, 1 = kreatif
            'maxOutputTokens': 512,   # Batas panjang respons
        },
    }
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}'
    response = requests.post(url, json=payload, timeout=20)
    return self._extract_text(response.json())
```

---

## BAGIAN C: Integrasi Database (ORM)

### Q9: Bagaimana Odoo ORM berkomunikasi dengan PostgreSQL?

Odoo ORM **mengabstraksi** semua SQL. Developer menulis Python, Odoo men-generate SQL secara otomatis:

| Python ORM | SQL yang Di-generate |
|-----------|---------------------|
| `Model.create({'name': 'A'})` | `INSERT INTO table (name) VALUES ('A') RETURNING id` |
| `Model.search([('user_id', '=', 5)])` | `SELECT * FROM table WHERE user_id = 5` |
| `record.write({'status': 'paid'})` | `UPDATE table SET status = 'paid' WHERE id = ?` |
| `record.unlink()` | `DELETE FROM table WHERE id = ?` |
| `Model.search_count([...])` | `SELECT COUNT(*) FROM table WHERE ...` |

### Q10: Kapan perlu pakai raw SQL (`env.cr.execute`)?

```python
# Kasus 1: Locking baris untuk mencegah race condition
# unitrade_payment/models/sale_order.py: L780
self.env.cr.execute(
    'SELECT id FROM sale_order WHERE id = %s FOR UPDATE',
    [self.id]
)
# SELECT ... FOR UPDATE = PostgreSQL row-level lock
# Mencegah dua request memproses order yang sama secara bersamaan

# Kasus 2: Migrasi data kompleks saat upgrade modul
# unitrade_seller/models/seller_verification.py: L196-209
def init(self):
    super().init()
    self.env.cr.execute("""
        UPDATE unitrade_seller_verification
           SET state = 'manual_review'
         WHERE state = 'rejected'
           AND LOWER(rejection_reason) LIKE '%%vision_api_failed%%'
    """)
# Raw SQL digunakan karena ini migrasi data massal yang lebih cepat dari ORM

# Kasus 3: Membuat index PostgreSQL kustom
# unitrade_seller/models/seller.py
self.env.cr.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS unitrade_seller_nim_unique
    ON unitrade_seller (nim)
    WHERE nim IS NOT NULL AND active = true
""")
# Index unik untuk memastikan satu NIM hanya satu seller aktif
```

---

### Q11: Bagaimana sistem Escrow menjaga integritas dana?

Escrow adalah model data yang mencatat **kepemilikan dana** antara buyer, system, dan seller:

```python
# State machine escrow:
# none → held → releasable → released
#            ↓           ↓
#         disputed    refunded

# Setelah pembayaran dikonfirmasi webhook Midtrans:
order.write({
    'x_escrow_state': 'held',          # Dana ditahan di sistem
    'x_payment_status': 'paid',        # Status bayar = lunas
    'x_unitrade_order_state': 'paid_escrow',
})

# Setelah pembeli konfirmasi terima barang:
ledger.write({
    'state': 'releasable',              # Dana siap dilepas
    'buyer_confirmed_at': datetime.now(),
})

# Cron job harian melepas dana ke saldo penjual:
ledger.write({
    'state': 'released',               # Dana sudah ke penjual
    'released_at': datetime.now(),
})
```

**Kenapa perlu Savepoint?**
```python
# Jika ada error di tengah proses, SEMUA operasi dibatalkan (rollback)
with self.env.cr.savepoint():
    intent = order._unitrade_repair_payment_intent()
    ledgers = Ledger._create_for_order(order, intent)
    ledgers._sync_order_escrow_state()
# Tanpa savepoint: jika step 3 gagal, step 1 & 2 sudah terlanjur dieksekusi
# → data tidak konsisten
```

---

## BAGIAN D: Keamanan

### Q12: Bagaimana memastikan satu seller tidak bisa melihat data seller lain?

**Lapisan 1: ACL (siapa boleh akses tabel apa)**
```csv
# ir.model.access.csv
access_unitrade_seller_seller,unitrade.seller.seller,model_unitrade_seller,
  unitrade_seller.group_unitrade_seller,1,1,1,0
# → Seller boleh READ/WRITE/CREATE tabel unitrade_seller, tapi TIDAK BISA DELETE
```

**Lapisan 2: Record Rules (filter baris data per user)**
```xml
<!-- security.xml -->
<record id="rule_seller_own" model="ir.rule">
    <field name="domain_force">[('user_id', '=', user.id)]</field>
    <field name="groups" eval="[(4, ref('group_unitrade_seller'))]"/>
</record>
```

**Efeknya:** Ketika kode berikut dijalankan oleh Seller A:
```python
# Seller A mencoba lihat SEMUA data seller
all_sellers = request.env['unitrade.seller'].search([])
# Meskipun tidak ada filter, Odoo OTOMATIS tambahkan:
# WHERE user_id = [ID_SELLER_A]
# Sehingga Seller A hanya melihat data miliknya sendiri
```

---

### Q13: Apa perbedaan `auth='public'`, `auth='user'`, dan `auth='none'` di controller?

```python
# auth='none': Siapa saja bisa akses, termasuk server eksternal (webhook)
@http.route('/unitrade/payment/midtrans/webhook', auth='none', csrf=False)
def midtrans_webhook(self): ...  # Dipanggil oleh server Midtrans

# auth='public': Bisa diakses tanpa login (untuk halaman publik)
@http.route('/unitrade/product/stock/validate', auth='public')
def stock_validate(self): ...  # Pengunjung bisa cek stok tanpa login

# auth='user': WAJIB login, jika tidak ada sesi valid → redirect ke /web/login
@http.route('/my/wishlist', auth='user', website=True)
def wishlist_page(self): ...  # Hanya user login yang bisa akses

# auth='user' + cek tambahan manual:
@http.route('/unitrade/admin', auth='user', website=True)
def admin_dashboard(self):
    if not self._is_admin():  # Cek apakah user punya group admin
        return self._forbidden('Tidak ada akses.')
```

---

### Q14: Bagaimana API key dijaga keamanannya?

**Yang SALAH (hardcode):**
```python
# JANGAN LAKUKAN INI!
api_key = "AIzaSyB1234567890abcdef"  # Langsung di source code
```

**Yang BENAR (dari database):**
```python
# Simpan di tabel ir.config_parameter (bisa diubah via UI admin)
# Tidak pernah ada di source code / git repository
api_key = self.env['ir.config_parameter'].sudo().get_param(
    'unitrade.google_vision.api_key', ''
)
```

**Konfigurasi disimpan di `data/midtrans_config.xml`:**
```xml
<!-- unitrade_payment/data/midtrans_config.xml -->
<record id="config_midtrans_server_key" model="ir.config_parameter">
    <field name="key">unitrade.midtrans.server_key</field>
    <field name="value">FILL_THIS_IN_ADMIN_PANEL</field>
    <!-- Value diisi via Admin > Technical > Parameters > System Parameters -->
</record>
```

---

### Q15: Bagaimana data sensitif user dilindungi saat penghapusan akun?

```python
# unitrade_theme/models/res_users.py: L91-110
def unitrade_privacy_deactivate(self, ...):
    """
    Mengikuti prinsip GDPR Right to Erasure:
    Data pribadi dihapus, data transaksi tetap ada (untuk akuntabilitas).
    """
    for user in self.sudo():
        # Generate ID acak untuk anonimisasi
        anonymized_ref = 'deleted-user-%s-%s' % (user.id, uuid.uuid4().hex[:10])

        partner = user.partner_id.sudo()
        partner.write({
            'name': 'Pengguna Dihapus',    # Nama dihapus
            'email': False,                 # Email dihapus dari database
            'phone': False,
            'mobile': False,
            'street': False,
            'image_1920': False,            # Foto profil dihapus
        })

        user.write({
            'active': False,                # Akun dinonaktifkan (soft delete)
            'x_privacy_anonymized_ref': anonymized_ref,
            'x_privacy_deactivated_at': fields.Datetime.now(),
        })

        # CATATAN PENTING: sale.order, unitrade.payment.intent, dll TETAP ADA
        # Mereka terhubung ke partner_id yang sudah dianonimisasi
        # Sehingga data keuangan tetap bisa diaudit, tapi identitas dirahasiakan
```

---

### Q16: Bagaimana sistem mencegah spam registrasi OTP?

```python
# unitrade_theme/controllers/controllers.py: L448-454
def send_otp_to_email(self, email='', **kw):
    otp_model = request.env['unitrade.otp'].sudo()
    purpose = request.session.get('otp_purpose', 'account_verification')

    # Rate limiting: maksimal 3 request OTP per 10 menit
    limit = otp_model.rate_limit_status(
        user_id,
        purpose=purpose,
        window_minutes=10,
        max_attempts=3
    )

    if not limit['allowed']:
        return {'success': False, 'message': 'Terlalu banyak permintaan OTP. Coba lagi dalam 10 menit.'}

    # Baru generate OTP jika lolos rate limit
    otp_record = otp_model.generate_otp(user_id, email, purpose=purpose)
    self._send_otp_email_direct(email, otp_record.code)
```

Ini mencegah penyerang melakukan brute force atau spam pengiriman email OTP.

---

## BAGIAN E: Logika Bisnis & Fitur Spesifik

### Q17: Bagaimana sistem menghitung biaya layanan (service fee) secara otomatis?

UniTrade menerapkan biaya layanan **flat (bukan persentase)** berdasarkan rentang nilai subtotal keranjang. Logika ini ada di model `sale.order`:

```python
# unitrade_theme/models/sale_order.py: L34-49
def _unitrade_service_fee_amount(self, subtotal):
    """
    Biaya layanan UniTrade dihitung FLAT per transaksi,
    bukan persentase, agar tidak memberatkan transaksi kecil.
    """
    subtotal = subtotal or 0.0
    if subtotal <= 0:
        return 0.0
    if subtotal < 50000:
        fee = 1000          # Rp1.000 untuk belanja di bawah Rp50.000
    elif subtotal <= 150000:
        fee = 1500          # Rp1.500 untuk Rp50.000 – Rp150.000
    elif subtotal <= 500000:
        fee = 2000          # Rp2.000 untuk Rp150.001 – Rp500.000
    elif subtotal <= 1000000:
        fee = 3000          # Rp3.000 untuk Rp500.001 – Rp1.000.000
    else:
        fee = 4000          # Rp4.000 untuk di atas Rp1.000.000

    # currency_id.round() = pembulatan sesuai mata uang (IDR = 0 desimal)
    return self.currency_id.round(fee)
```

**Cara biaya layanan masuk ke order:**

```python
# unitrade_theme/models/sale_order.py: L51-103
def _unitrade_checkout_amounts(self, sync_fee=False):
    """
    Hitung ulang semua komponen harga checkout:
    item_subtotal + service_fee = total
    """
    # Pisahkan order_line menjadi:
    # 1. product_lines → baris produk asli dari pembeli
    # 2. fee_lines    → baris biaya layanan (produk virtual)
    fee_product = self._unitrade_service_fee_product()
    product_lines = self.order_line.filtered(
        lambda line: not line.display_type and line.product_id
                     and line.product_id != fee_product
    )

    subtotal = sum(product_lines.mapped('price_subtotal'))
    service_fee = self._unitrade_service_fee_amount(subtotal)

    if sync_fee and self.state == 'draft':
        # Hapus baris fee lama, hitung ulang dengan harga terkini
        fee_lines = self.order_line.filtered(lambda l: l.product_id == fee_product)
        if fee_lines:
            fee_lines.sudo().unlink()  # Hapus dulu
        # Tambahkan baris biaya layanan baru ke order_line
        self.sudo().write({
            'order_line': [(0, 0, {
                'product_id': fee_product.id,
                'product_uom_qty': 1,
                'price_unit': service_fee,
                'name': 'Biaya Layanan UniTrade',
            })]
        })

    return {
        'item_subtotal': subtotal,
        'service_fee': service_fee,
        'total': subtotal + service_fee,
    }
```

**Contoh:**
- Beli produk Rp75.000 → service fee = Rp1.500 → Total = Rp76.500
- Beli produk Rp250.000 → service fee = Rp2.000 → Total = Rp252.000

---

### Q18: Bagaimana mekanisme OTP bekerja secara teknis dari model hingga email?

OTP adalah proses multi-langkah yang melibatkan **model**, **controller**, dan **mail.mail** (email Odoo):

**Langkah 1 — Model membuat kode OTP**
```python
# unitrade_theme/models/otp.py: L39-63
@api.model
def generate_otp(self, user_id, email, purpose='account_verification'):
    """Generate OTP 6 digit untuk user."""

    # Batalkan semua OTP lama yang belum dipakai (satu user = satu OTP aktif)
    self.search([
        ('user_id', '=', user_id),
        ('purpose', '=', purpose),
        ('is_used', '=', False),
    ]).write({'is_used': True})

    # Generate kode acak 6 digit menggunakan random.choices
    code = ''.join(random.choices(string.digits, k=6))
    # Contoh kode: '847291'

    # OTP valid selama 5 menit
    expires_at = fields.Datetime.now() + timedelta(minutes=5)

    otp_record = self.create({
        'user_id': user_id,
        'code': code,
        'email': email,
        'purpose': purpose,
        'expires_at': expires_at,  # Kadaluarsa 5 menit dari sekarang
        'is_used': False,
    })
    return otp_record
```

**Langkah 2 — Controller mengirim email**
```python
# unitrade_theme/controllers/controllers.py: L473-487
def _send_otp_email_direct(self, email_to, code):
    """Kirim OTP via email menggunakan mail.mail Odoo."""
    template_values = {
        'email_from': request.env.company.email or 'noreply@unitrade.dev',
        'email_to': email_to,
        'subject': '🔐 UniTrade - Kode Verifikasi Akun Anda',
        'body_html': self._build_otp_email_html(code, email_to),
        'auto_delete': True,  # Email dihapus dari antrian setelah terkirim
    }
    # mail.mail = model bawaan Odoo untuk kirim email
    mail = request.env['mail.mail'].sudo().create(template_values)
    mail.send()  # Odoo menggunakan konfigurasi SMTP di Settings > Technical
```

**Langkah 3 — User input OTP, model memverifikasi**
```python
# unitrade_theme/models/otp.py: L65-87
@api.model
def verify_otp(self, user_id, code, purpose=None):
    """Verifikasi kode OTP yang diinput user."""
    domain = [
        ('user_id', '=', user_id),
        ('code', '=', code),           # Kode harus cocok persis
        ('is_used', '=', False),       # Kode belum pernah dipakai
    ]
    if purpose:
        domain.append(('purpose', '=', purpose))

    otp_record = self.search(domain, order='create_date desc', limit=1)

    if not otp_record:
        return False  # Kode salah atau sudah dipakai

    # Cek apakah OTP sudah kadaluarsa (lebih dari 5 menit)
    if fields.Datetime.now() > otp_record.expires_at:
        return False  # OTP expired

    # Tandai OTP sebagai sudah dipakai (tidak bisa dipakai lagi)
    otp_record.is_used = True
    return True
```

**OTP memiliki 3 `purpose` yang berbeda:**
| Purpose | Digunakan Saat |
|---------|---------------|
| `account_verification` | Registrasi akun baru |
| `seller_onboarding` | Pendaftaran sebagai seller |
| `settings_password_reset` | Reset password dari halaman settings |

---

### Q19: Bagaimana sistem dispute/refund bekerja? Siapa yang bisa mengajukan?

**Hanya pembeli yang bisa mengajukan refund**, dan hanya dalam kondisi tertentu:

```python
# unitrade_dispute/models/sale_order.py: L54-76
def _unitrade_refund_blocker(self, partner=None, ledger=False):
    """Cek semua kondisi yang menghalangi pengajuan refund."""
    self.ensure_one()

    # Kondisi 1: Harus sudah dibayar
    if self.x_payment_status != 'paid':
        return 'Refund hanya tersedia setelah pembayaran berhasil.'

    # Kondisi 2: Order masih dalam tahap 'processing' (belum diterima pembeli)
    if self.x_unitrade_order_state != 'processing':
        return 'Refund hanya tersedia saat pesanan masih diproses.'

    # Kondisi 3: Status escrow masih 'held' atau 'disputed'
    if self.x_escrow_state not in ('held', 'disputed'):
        return 'Refund tidak tersedia untuk status transaksi ini.'

    # Kondisi 4: Order belum dibatalkan
    if self.state == 'cancel':
        return 'Pesanan sudah dibatalkan.'

    # Kondisi 5: Tidak ada dispute aktif sebelumnya
    if self._unitrade_active_refund_dispute(ledger=ledger):
        return 'Refund untuk pesanan ini sedang diproses.'

    return False  # Tidak ada blocker → boleh refund
```

**Proses pengajuan refund dengan validasi bukti:**
```python
# unitrade_dispute/models/sale_order.py: L100-177
def action_unitrade_create_refund(self, reason_note='', evidence_items=None, ...):
    # Kunci baris order (mencegah double-submit refund bersamaan)
    self.env.cr.execute('SELECT id FROM sale_order WHERE id = %s FOR UPDATE', [order.id])

    # Validasi: catatan alasan minimal 20 karakter
    if len(reason_note) < 20:
        raise UserError('Catatan pengembalian minimal 20 karakter.')

    # Validasi: wajib upload minimal 1 foto bukti
    has_photo = any(
        item.get('evidence_type') == 'buyer_photo' and item.get('datas')
        for item in evidence_items
    )
    if not has_photo:
        raise UserError('Minimal upload 1 foto bukti pengembalian.')

    # Validasi: URL Google Drive harus valid
    drive_urls = [item.get('url') for item in evidence_items
                  if item.get('evidence_type') == 'google_drive_url']
    if any(url and not self._unitrade_is_google_drive_url(url) for url in drive_urls):
        raise UserError('Link Google Drive harus menggunakan domain drive.google.com.')

    # Buat record dispute
    dispute = self.env['unitrade.dispute'].sudo().create({
        'dispute_type': 'refund',
        'state': 'draft',
        'order_id': order.id,
        'buyer_id': order.partner_id.id,
        'reason_code': reason_code,
        'reason_note': reason_note,
        'requested_amount': amount,
    })

    # Simpan semua evidence (foto + URL)
    for item in evidence_items:
        if item.get('datas'):  # File di-encode base64
            attachment = self.env['ir.attachment'].sudo().create({
                'name': item.get('name') or 'bukti-pengembalian',
                'datas': item.get('datas'),  # Konten file base64
                'res_model': 'unitrade.dispute',
                'res_id': dispute.id,
            })
        self.env['unitrade.dispute.evidence'].sudo().create({
            'dispute_id': dispute.id,
            'evidence_type': item.get('evidence_type'),
            'attachment_id': attachment.id if attachment else False,
            'url': item.get('url') or False,
        })

    dispute.action_submit()  # Ubah state ke 'submitted'
    return dispute
```

**State machine dispute:**
```
[draft] → [submitted] → [under_review] → [need_buyer_evidence]
                                       → [need_seller_response]
                                       → [admin_review_final]
                                           ↓               ↓
                                       [approved]      [rejected]
                                    (dana ke pembeli) (dana ke penjual)
```

---

### Q20: Bagaimana admin memproses verifikasi KTM (approve/reject)?

**Alur dari controller ke model:**

```python
# unitrade_admin/controllers/admin_dashboard.py: L400-410
# Admin klik tombol "Approve" di halaman KTM Verifications

@http.route('/unitrade/admin/api/report-list/set-status', type='json', auth='user')
def api_report_set_status(self, report_type='', report_id=0, status='', note='', **kwargs):
    if not self._is_admin():
        return {'ok': False, 'error': 'forbidden'}
    # Delegate ke Stats model yang memiliki logika bisnis
    return self._stats().admin_set_report_status(report_type, report_id, status, note=note)
```

**Model yang menangani approve:**
```python
# unitrade_seller/models/seller_verification.py: L306-343
def action_approve(self):
    """Admin menyetujui verifikasi KTM."""

    # Cek apakah user punya hak admin
    self._check_admin_verification('approve_ktm')

    for record in self:
        # 1. Buat/update record unitrade.seller
        seller = record._approve_to_seller()

        # 2. Update status verifikasi
        record.write({
            'state': 'approved',
            'reviewed_by': self.env.uid,
            'reviewed_date': fields.Datetime.now(),
        })

        # 3. Kirim email notifikasi ke seller via mail template
        template = self.env.ref(
            'unitrade_seller.mail_template_seller_verified',
            raise_if_not_found=False,
        )
        if template:
            template.sudo().send_mail(seller.id, force_send=True)

        # 4. Catat ke admin audit log
        log_admin_action(
            self.env,
            'ktm.approve',
            description='Verifikasi KTM untuk %s disetujui oleh %s.' % (
                record.partner_id.name, self.env.user.name,
            ),
            record=record,
            severity='warning',
        )
```

**Validasi admin sebelum eksekusi:**
```python
# unitrade_seller/models/seller_verification.py: L392-404
def _check_admin_verification(self, action_label):
    """Gate keamanan: hanya admin yang boleh approve/reject KTM."""
    user = self.env.user
    is_admin = (
        user.has_group('unitrade_seller.group_unitrade_admin') or
        user.has_group('base.group_system')
    )
    if not is_admin:
        # Log attempt tidak sah
        _logger.warning(
            'Verification %s: unauthorized %s attempt by uid=%s',
            self.mapped('id') or '-', action_label, self.env.uid,
        )
        # Lempar exception → HTTP 403
        raise AccessDenied('Aksi ini hanya boleh dilakukan oleh admin UniTrade.')
```

---

### Q21: Bagaimana dashboard admin mengumpulkan statistik dari berbagai tabel?

Model `unitrade.admin.stats` adalah **AbstractModel** — tidak punya tabel sendiri di PostgreSQL, tapi bisa mengakses semua model lain. Ini adalah pola **Service/Aggregator**:

```python
# unitrade_admin/models/admin_stats.py: L14-34
class UnitradeAdminStats(models.AbstractModel):
    """
    AbstractModel = tidak buat tabel di PostgreSQL.
    Hanya berisi metode agregasi dari berbagai model.
    Satu panggilan get_dashboard_data() mengumpulkan
    semua data yang dibutuhkan dashboard sekaligus.
    """
    _name = 'unitrade.admin.stats'
    _description = 'UniTrade Admin Dashboard Aggregator'

    @api.model
    def _check_admin(self):
        """Gate keamanan setiap metode harus panggil ini dulu."""
        user = self.env.user
        if user.has_group('base.group_system') or \
           user.has_group('unitrade_seller.group_unitrade_admin'):
            return
        raise AccessError('Hanya admin UniTrade yang dapat membuka dashboard ini.')

    @staticmethod
    def _safe_count(model, domain):
        """Hitung record dengan error handling — dashboard tidak boleh crash."""
        try:
            return model.search_count(domain)
        except Exception:
            _logger.exception('Failed counting %s', model)
            return 0  # Return 0, bukan error → dashboard tetap jalan
```

**Cara agregasi data GMV (Gross Merchandise Value) menggunakan raw SQL:**
```python
# unitrade_admin/models/admin_stats.py: L374-401
# GMV 7 hari terakhir menggunakan aggregate SQL langsung ke PostgreSQL
self.env.cr.execute(
    """
    SELECT date_trunc('day', create_date)::date AS day,
           COALESCE(SUM(amount_total), 0)       AS total
      FROM sale_order
     WHERE state IN ('sale', 'done')
       AND create_date::date >= %s
     GROUP BY day
     ORDER BY day
    """,
    [seven_days_ago],  # Parameter binding untuk mencegah SQL injection
)
rows = {r['day']: r['total'] for r in self.env.cr.dictfetchall()}

# Bangun series 7 hari (termasuk hari yang nilai GMV-nya 0)
gmv_series = []
for offset in range(7):
    day = seven_days_ago + timedelta(days=offset)
    value = float(rows.get(day, 0) or 0)
    gmv_series.append({
        'date': fields.Date.to_string(day),
        'label': day.strftime('%d %b'),  # Format: "16 Jul"
        'value': value,
    })
```

**Kenapa raw SQL untuk GMV?**
- ORM Odoo tidak mendukung `date_trunc`, `GROUP BY date`, `SUM` agregat secara efisien
- Raw SQL jauh lebih cepat untuk laporan besar
- Parameter binding (`%s`) mencegah SQL injection

---

### Q22: Bagaimana Google OAuth (SSO) terintegrasi dan menangani akun yang sudah ada?

UniTrade meng-override metode `_auth_oauth_signin` bawaan Odoo untuk **menautkan akun yang sudah ada** ke Google OAuth:

```python
# unitrade_theme/models/res_users.py: L183-224
@api.model
def _auth_oauth_signin(self, provider, validation, params):
    """
    Override metode SSO Odoo.
    Problem standar Odoo: jika user sudah daftar via email+password,
    lalu coba login via Google dengan email yang sama → error "user not found".

    Solusi UniTrade: link akun lama ke OAuth provider secara otomatis.
    """
    oauth_uid = validation['user_id']

    # Langkah 1: Coba cara standar — cari by oauth_uid
    oauth_user = self.search([
        ('oauth_uid', '=', oauth_uid),
        ('oauth_provider_id', '=', provider),
    ])
    if oauth_user:
        oauth_user.write({'oauth_access_token': params['access_token']})
        return oauth_user.login  # User sudah terhubung sebelumnya → langsung login

    # Langkah 2: Tidak ketemu by oauth_uid → cari by email
    email = validation.get('email')
    if email:
        # Cek blacklist dulu sebelum lanjut
        if 'unitrade.account.blacklist' in self.env.registry:
            if self.env['unitrade.account.blacklist'].sudo().is_contact_blocked(email=email):
                raise AccessDenied('Email ini tidak dapat digunakan untuk masuk ke UniTrade.')

        # Cari akun lama dengan email yang sama
        existing_user = self.search([('login', '=', email)], limit=1)
        if existing_user:
            # Tautkan akun lama ke Google OAuth → seamless experience
            existing_user.write({
                'oauth_provider_id': provider,
                'oauth_uid': oauth_uid,
                'oauth_access_token': params['access_token'],
            })
            _logger.info('Linked existing user %s to OAuth provider %s',
                         existing_user.login, provider)
            return existing_user.login

    # Langkah 3: User benar-benar baru → buat akun baru (Odoo default flow)
    return super()._auth_oauth_signin(provider, validation, params)
```

**Skenario yang ditangani:**
| Skenario | Hasil |
|----------|-------|
| Login Google pertama kali (email baru) | Buat akun baru |
| Login Google lagi (sudah terhubung) | Login langsung |
| Login Google dengan email yang sudah daftar manual | Link ke akun lama + login |
| Login Google dengan email di-blacklist | `AccessDenied` exception |

---

## BAGIAN F: Pertanyaan Konseptual & Arsitektur

### Q23: Apa perbedaan `@api.model` vs method biasa di Odoo? Kapan digunakan?

```python
# TANPA @api.model → method yang butuh record (self = recordset)
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """
        Dipanggil pada record yang sudah ada.
        self bisa satu atau banyak record.
        """
        self.ensure_one()  # Validasi: hanya boleh satu record
        # self.id = ID record yang spesifik
        # Contoh panggilan: order.action_confirm()
        return super().action_confirm()

    def write(self, vals):
        """
        Override write() untuk semua record.
        self = recordset berisi record-record yang di-update.
        """
        return super().write(vals)


# DENGAN @api.model → method di level class, bukan record spesifik
class UnitradeOtp(models.Model):
    _name = 'unitrade.otp'

    @api.model  # ← Dekorator ini!
    def generate_otp(self, user_id, email, purpose='account_verification'):
        """
        Tidak perlu record yang sudah ada untuk memanggilnya.
        Contoh: OTP.generate_otp(user_id=5, email='user@unisa.ac.id')
        Seperti @staticmethod tapi masih bisa akses self.env
        """
        code = ''.join(random.choices(string.digits, k=6))
        return self.create({...})  # Buat record baru

    @api.model
    def rate_limit_status(self, user_id, purpose, window_minutes, max_attempts):
        """
        Cek global (tidak butuh record spesifik).
        Dipanggil dari controller: request.env['unitrade.otp'].rate_limit_status(...)
        """
        cutoff = fields.Datetime.now() - timedelta(minutes=window_minutes)
        attempts = self.search_count([
            ('user_id', '=', user_id),
            ('purpose', '=', purpose),
            ('create_date', '>=', cutoff),
        ])
        return {'allowed': attempts < max_attempts}
```

**Ringkasan:**
| | `@api.model` | Method biasa |
|-|-------------|-------------|
| Butuh record | ❌ Tidak | ✅ Ya |
| Akses `self.env` | ✅ Ya | ✅ Ya |
| `self.id` | ❌ Tidak ada | ✅ Ada |
| Contoh penggunaan | `create()`, `search()`, class-level operation | `write()`, `action_*`, per-record logic |

---

### Q24: Apa itu `AbstractModel` di Odoo? Kapan digunakan?

```python
# unitrade_admin/models/admin_stats.py: L14-22
class UnitradeAdminStats(models.AbstractModel):
    """
    AbstractModel: Tidak membuat tabel di PostgreSQL.
    Digunakan sebagai:
    1. Service layer (kumpulan logika bisnis tanpa state)
    2. Mixin (shared behavior antar model)
    """
    _name = 'unitrade.admin.stats'
```

**Perbandingan:**
| | `models.Model` | `models.AbstractModel` | `models.TransientModel` |
|-|--------------|----------------------|------------------------|
| Tabel di DB | ✅ Ya | ❌ Tidak | ✅ Ya (temp) |
| Data persisten | ✅ Ya | ❌ Tidak | ❌ Dihapus otomatis |
| Kegunaan | Data master | Service/Mixin | Wizard/popup |

**Contoh mixin menggunakan AbstractModel:**
```python
# Jika beberapa model punya logika yang sama, buat Abstract dulu
class UnitradeTimestampMixin(models.AbstractModel):
    _name = 'unitrade.timestamp.mixin'

    created_by = fields.Many2one('res.users', default=lambda s: s.env.uid)
    modified_at = fields.Datetime()

    def write(self, vals):
        vals['modified_at'] = fields.Datetime.now()
        return super().write(vals)

# Lalu inherit di model lain
class UnitradeDispute(models.Model):
    _name = 'unitrade.dispute'
    _inherit = ['unitrade.timestamp.mixin']  # Dapat semua field + method mixin
```

---

### Q25: Bagaimana Odoo menangani nomor urut otomatis (sequence) seperti nomor tiket CS?

```python
# unitrade_theme/models/customer_service.py: L93-104
@api.model_create_multi
def create(self, vals_list):
    """
    @api.model_create_multi = override create() untuk batch insert.
    Lebih efisien dari override create() biasa karena Odoo bisa
    memanggil single INSERT ... VALUES (...), (...), (...)
    """
    for vals in vals_list:
        # Auto-generate nomor tiket dari sequence
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = (
                self.env['ir.sequence'].next_by_code('unitrade.customer.ticket')
                or _('New')
            )
            # Hasilnya: 'CS/2026/07/0001', 'CS/2026/07/0002', dst
    return super().create(vals_list)
```

**Definisi sequence di XML:**
```xml
<!-- unitrade_theme/data/sequences.xml -->
<record id="seq_unitrade_customer_ticket" model="ir.sequence">
    <field name="name">UniTrade Customer Ticket</field>
    <field name="code">unitrade.customer.ticket</field>
    <!-- Format: CS/2026/07/0001 -->
    <field name="prefix">CS/%(year)s/%(month)s/</field>
    <field name="padding">4</field>   <!-- 4 digit: 0001 -->
    <field name="number_increment">1</field>
</record>
```

---

### Q26: Mengapa menggunakan `request.env` di Controller vs `self.env` di Model?

```python
# Di CONTROLLER (HTTP handler):
class UnitradeController(http.Controller):

    @http.route('/my/wishlist', type='http', auth='user', website=True)
    def wishlist_page(self, **kwargs):
        # request.env = environment dari HTTP request yang sedang berjalan
        # → sudah tahu siapa user yang login (request.env.uid = ID user login)
        # → sudah tahu database yang digunakan
        # → sudah tahu context (language, timezone)
        items = request.env['unitrade.wishlist'].sudo().search([
            ('user_id', '=', request.env.uid),  # UID user dari session HTTP
        ])
        return request.render('...', {'items': items})


# Di MODEL (business logic):
class UnitradeWishlist(models.Model):
    _name = 'unitrade.wishlist'

    def action_toggle(self):
        # self.env = environment yang diinjeksi saat model diinstansiasi
        # → sudah tahu user, database, context
        # → SAMA dengan request.env, hanya cara aksesnya berbeda
        other_model = self.env['unitrade.notification'].sudo()
        # self.env.uid = ID user yang menjalankan aksi ini
        current_user = self.env.user
```

**Intinya:** `request.env` dan `self.env` adalah **hal yang sama** — keduanya adalah `odoo.api.Environment`. Perbedaannya hanya **konteks pemanggilannya**: di Controller gunakan `request.env`, di Model gunakan `self.env`.

---

### Q27: Apa risiko penggunaan `sudo()` yang berlebihan dan bagaimana UniTrade menggunakannya dengan benar?

`sudo()` membypass semua security check Odoo (ACL + Record Rules). Ini berbahaya jika disalahgunakan.

```python
# ❌ SALAH: sudo() dipakai sembarangan untuk menghindari error akses
@http.route('/my/profile', auth='user')
def profile_page(self):
    # BERBAHAYA: user bisa melihat data semua user lain!
    all_users = request.env['res.users'].sudo().search([])
    return request.render('...', {'users': all_users})


# ✅ BENAR: sudo() digunakan dengan alasan yang jelas dan scope minimal
@http.route('/my/profile', auth='user')
def profile_page(self):
    # sudo() untuk notifikasi: sistem perlu buat notifikasi untuk user lain
    # (creator notifikasi berbeda dengan penerima notifikasi)
    Notification = request.env['unitrade.notification'].sudo()
    Notification.create({
        'user_id': buyer_id,       # Notifikasi untuk user LAIN
        'title': 'Pesanan dikonfirmasi',
    })

    # TANPA sudo() untuk data user sendiri: record rule sudah membatasi
    my_data = request.env['unitrade.wishlist'].search([])
    # → Record rule otomatis filter: WHERE user_id = request.env.uid
    # → User hanya bisa lihat wishlist miliknya tanpa perlu filter manual


# ✅ BENAR: sudo() untuk cek konfigurasi sistem (ir.config_parameter)
api_key = request.env['ir.config_parameter'].sudo().get_param('unitrade.midtrans.server_key')
# ir.config_parameter hanya bisa dibaca oleh admin (group_system)
# sudo() diperlukan agar non-admin bisa baca konfigurasi yang dibutuhkan sistem
```

**Panduan kapan boleh `sudo()`:**
| Kasus | Boleh `sudo()`? |
|-------|----------------|
| Membaca `ir.config_parameter` | ✅ Ya — perlu untuk config sistem |
| Membuat notifikasi untuk user lain | ✅ Ya — sistem yang buat, bukan user |
| Proses webhook dari pihak ketiga (auth=none) | ✅ Ya — tidak ada user session |
| Membaca data semua user tanpa filter | ❌ Tidak — pakai record rule |
| Akses admin-only data dari halaman publik | ❌ Tidak — gunakan cek role |
| Bypass validasi bisnis | ❌ Tidak — ikuti alur normal |
