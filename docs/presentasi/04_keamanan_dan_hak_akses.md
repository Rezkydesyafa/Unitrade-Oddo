# 04 — Implementasi Keamanan & Hak Akses

## Arsitektur Keamanan 5 Lapisan UniTrade

```
┌─────────────────────────────────────────────────────────────────┐
│  Lapisan 1: AUTENTIKASI                                         │
│    ✓ OTP Email (6 digit, expired 5 menit)                       │
│    ✓ Google OAuth 2.0 (SSO)                                     │
│    ✓ Rate limiting OTP (3 request / 10 menit)                   │
│    ✓ Blacklist email                                            │
│    ✓ Audit trail setiap aktivitas login                         │
├─────────────────────────────────────────────────────────────────┤
│  Lapisan 2: OTORISASI (Security Groups)                         │
│    ✓ base.group_public (Tamu)                                   │
│    ✓ base.group_user (Pembeli)                                  │
│    ✓ group_unitrade_seller (Penjual Terverifikasi)              │
│    ✓ group_unitrade_admin (Administrator)                       │
│    ✓ base.group_system (Odoo Superuser)                         │
├─────────────────────────────────────────────────────────────────┤
│  Lapisan 3: ACL — ACCESS CONTROL LIST                           │
│    ✓ Hak CRUD per model per group (ir.model.access.csv)         │
├─────────────────────────────────────────────────────────────────┤
│  Lapisan 4: RECORD RULES (Row-Level Security)                   │
│    ✓ Filter otomatis baris data per user (ir.rule)             │
│    ✓ Seller hanya lihat data tokonya sendiri                    │
├─────────────────────────────────────────────────────────────────┤
│  Lapisan 5: KEAMANAN TRANSAKSI                                  │
│    ✓ SHA-512 signature validation webhook Midtrans              │
│    ✓ Row-level locking (SELECT ... FOR UPDATE)                  │
│    ✓ Idempotency webhook (deduplication)                        │
└─────────────────────────────────────────────────────────────────┘
```

> 💡 **Penjelasan diagram:** Setiap permintaan ke sistem UniTrade melewati lapisan-lapisan ini secara berurutan. Lapisan 1 memastikan identitas user valid. Lapisan 2 memastikan user punya role yang sesuai. Lapisan 3 memastikan role tersebut boleh melakukan aksi (baca/tulis/hapus). Lapisan 4 memastikan data yang diakses benar-benar milik user tersebut. Lapisan 5 khusus untuk keamanan transaksi finansial. Sistem yang hanya punya satu lapisan keamanan sangat rentan — UniTrade menggunakan 5 lapisan sehingga jika satu lapisan terlewati, lapisan berikutnya masih menghalangi.

---

## Lapisan 1: Autentikasi

### A. Override Login Odoo + Paksa OTP

```python
# unitrade_theme/controllers/controllers.py: L60-117

class UnitradeAuthSignup(OAuthLogin):
    """
    Mewarisi controller login bawaan Odoo (OAuthLogin).
    Tambahkan logika OTP setelah login berhasil.
    """

    @http.route()  # Tanpa path = override route yang sama
    def web_login(self, *args, **kw):
        """Override web_login bawaan Odoo untuk memaksa OTP."""

        # Normalisasi input: hanya izinkan format email, tidak boleh username
        if request.httprequest.method == 'POST' and request.params.get('login'):
            login_value = _normalize_login(request.params.get('login'))
            if not _is_email(login_value):
                return self._render_login_form_error(
                    login_value, "Masukkan email yang valid untuk login."
                )

        # Panggil login standar Odoo terlebih dahulu
        response = super().web_login(*args, **kw)

        # Setelah login berhasil (session.uid terisi):
        if request.httprequest.method == 'POST' and request.session.uid:
            user = request.env['res.users'].sudo().browse(request.session.uid)

            # Hanya enforce OTP untuk portal/public user, skip untuk admin internal
            if user.exists() and not user.is_otp_verified and not user.has_group('base.group_user'):
                _logger.info("User %s belum OTP verified. Redirecting ke OTP.", user.login)

                # PENTING: Logout dulu, jangan biarkan user bypass OTP
                login_val = user.login
                request.session.logout(keep_db=True)
                request.env['ir.http']._auth_method_public()

                # Redirect ke halaman verifikasi OTP
                return self._generate_and_redirect_otp(user, login_val)

            # Login sukses dan OTP sudah valid: catat ke audit trail
            if user.exists():
                user.unitrade_record_security_activity(
                    'login',
                    title='Login berhasil',
                    detail='Masuk ke akun UniTrade.',
                    ip_address=request.httprequest.remote_addr,
                    user_agent=request.httprequest.headers.get('User-Agent', ''),
                    session_id=request.session.sid,
                )
        return response
```

> 💡 **Penjelasan:** Kode ini mengimplementasikan alur login dua langkah (2FA sederhana menggunakan email OTP). Setelah password benar diverifikasi Odoo (`super().web_login()`), kita segera cek field `is_otp_verified` di tabel user. Jika `False`, berarti user belum pernah verifikasi OTP — kita paksa logout (`request.session.logout()`) dan redirect ke halaman OTP. Penting: logout dilakukan sebelum redirect, bukan setelahnya — ini mencegah jendela singkat di mana session sudah aktif tapi OTP belum diverifikasi. Setiap login berhasil juga dicatat ke `unitrade.security.activity` dengan IP address dan user agent untuk keperluan audit forensik.

---

### B. Flow Signup dengan Validasi Berlapis

```python
# unitrade_theme/controllers/controllers.py: L119-175
@http.route('/web/signup', type='http', auth='public', website=True)
def web_auth_signup(self, *args, **kw):
    """Override signup Odoo dengan validasi UniTrade tambahan."""
    qcontext = self.get_auth_signup_qcontext()

    if request.httprequest.method == 'POST':
        login_value = _normalize_login(qcontext.get('login'))

        # Validasi 1: Format email harus valid
        if not _is_email(login_value):
            raise UserError("Masukkan alamat email yang valid.")

        # Validasi 2: Email tidak ada di blacklist
        if _is_unitrade_contact_blacklisted(email=login_value):
            raise UserError("Email ini tidak dapat digunakan untuk membuat akun UniTrade.")

        # Validasi 3: Harus setuju Terms & Kondisi
        if request.params.get('terms_accepted') != '1':
            raise UserError("Anda harus menyetujui Syarat Ketentuan & Kebijakan Privasi.")

        # Validasi 4: Google reCaptcha (mencegah bot registrasi)
        if not request.env['ir.http']._verify_request_recaptcha_token('signup'):
            raise UserError("Suspicious activity detected by Google reCaptcha.")

        # Buat akun user baru di Odoo
        self.do_signup(qcontext)

        # Cari user yang baru dibuat
        user_sudo = request.env['res.users'].sudo().search(
            [('login', '=', login_value)], limit=1
        )
        if user_sudo:
            # Catat event registrasi ke audit trail
            user_sudo.unitrade_record_security_activity(
                'register',
                title='Akun dibuat',
                detail='Registrasi akun UniTrade.',
                ip_address=request.httprequest.remote_addr,
            )
            # Simpan persetujuan Terms & Privacy
            user_sudo.unitrade_accept_terms_privacy(
                ip_address=request.httprequest.remote_addr,
            )
            # Generate OTP 6 digit, kirim ke email, redirect ke halaman verifikasi
            return self._generate_and_redirect_otp(user_sudo, login_value)
```

> 💡 **Penjelasan:** Registrasi melewati empat pagar sebelum akun dibuat. Ini bukan sekadar validasi form biasa — masing-masing punya tujuan keamanan spesifik. Validasi email format mencegah data sampah masuk ke database. Cek blacklist mencegah email yang pernah disalahgunakan (spammer, akun palsu) mendaftar ulang. Pengecekan persetujuan Terms merupakan syarat hukum agar pengguna sadar telah menyetujui kebijakan platform. reCaptcha mencegah bot membuat ratusan akun secara otomatis. Baru setelah semua ini lulus, akun dibuat. Setiap langkah juga dicatat ke audit trail sehingga ada bukti hukum bahwa user benar-benar menyetujui syarat ketentuan pada timestamp tertentu.

---

### C. Rate Limiting OTP (Anti-Spam)

```python
# Dipanggil sebelum generate OTP baru:
limit = otp_model.rate_limit_status(
    user_id,
    purpose='account_verification',
    window_minutes=10,   # Window waktu 10 menit
    max_attempts=3       # Maksimal 3 kali permintaan OTP dalam 10 menit
)

if not limit['allowed']:
    return {
        'success': False,
        'message': 'Terlalu banyak permintaan OTP. Coba lagi dalam 10 menit.'
    }

# Baru generate OTP jika lolos rate limit
otp_record = otp_model.generate_otp(user_id, email, purpose='account_verification')
```

> 💡 **Penjelasan:** Tanpa rate limiting, penyerang bisa mengirim ribuan request OTP ke email korban (email flooding / spam attack) atau mencoba menebak kode OTP dengan brute force. Mekanisme ini membatasi satu user hanya boleh meminta OTP maksimal 3 kali dalam 10 menit. Jika melewati batas, sistem menolak permintaan tanpa generate kode baru. Implementasinya sederhana: sistem menghitung berapa baris di tabel `unitrade_otp` yang dibuat oleh `user_id` yang sama dalam 10 menit terakhir. Jika jumlahnya ≥ 3, request ditolak.

---

### D. Audit Trail Keamanan

```python
# unitrade_theme/models/security_activity.py: L8-47
class UnitradeSecurityActivity(models.Model):
    _name = 'unitrade.security.activity'
    _description = 'UniTrade Security Activity'
    _order = 'event_date desc, id desc'  # Terbaru tampil pertama

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    event_type = fields.Selection([
        ('register', 'Registrasi'),
        ('consent_accepted', 'Terms & Privacy Disetujui'),
        ('otp_verified', 'OTP Diverifikasi'),
        ('login', 'Login'),
        ('password_change', 'Perubahan Password'),
        ('session_revoke', 'Session Dicabut'),
        ('session_revoke_all', 'Semua Session Dicabut'),
        ('deactivate_anonymize', 'Akun Dinonaktifkan'),
    ], required=True, index=True)
    title = fields.Char(string='Judul', required=True)
    ip_address = fields.Char(string='IP Address')  # Untuk forensik keamanan
    user_agent = fields.Char(string='User Agent')  # Browser/device info
    session_id = fields.Char(string='Session ID')
    event_date = fields.Datetime(required=True, default=fields.Datetime.now, index=True)

    @api.model
    def record_activity(self, user, event_type, title=False, ip_address=False, ...):
        """Buat baris audit trail PERMANEN untuk user."""
        # sudo() karena model ini perlu diakses dari berbagai konteks
        return self.sudo().create({
            'user_id': user.id,
            'event_type': event_type,
            'title': title or dict(self._fields['event_type'].selection).get(event_type),
            'ip_address': ip_address or '',
        })
```

> 💡 **Penjelasan:** Model ini adalah "buku catatan keamanan" UniTrade. Setiap kejadian penting (login, registrasi, perubahan password, penghapusan akun) dicatat secara permanen dengan timestamp, IP address, dan informasi browser. Data ini sangat berharga untuk tiga skenario: (1) investigasi insiden keamanan — jika ada akun yang dibobol, kita bisa melihat dari IP mana login terjadi; (2) compliance/audit — membuktikan bahwa user benar-benar menyetujui terms pada tanggal tertentu; (3) forensik — jika ada aktivitas mencurigakan, admin bisa melihat timeline lengkap aktivitas seorang user. Field `ondelete='cascade'` berarti jika akun user dihapus, catatan aktivitasnya juga ikut dihapus (kecuali pada proses anonimisasi yang tetap mempertahankan record).

---

## Lapisan 2: Security Groups (Role)

### Definisi Lengkap Role

```xml
<!-- unitrade_seller/security/security.xml -->

<!-- 1. Kategori modul di menu Settings → Groups -->
<record id="module_category_unitrade" model="ir.module.category">
    <field name="name">UniTrade Marketplace</field>
    <field name="sequence">100</field>
</record>

<!-- 2. Role SELLER: Penjual yang sudah verifikasi KTM -->
<record id="group_unitrade_seller" model="res.groups">
    <field name="name">Seller</field>
    <field name="category_id" ref="module_category_unitrade"/>
    <field name="comment">
        Penjual terverifikasi di UniTrade Marketplace.
        User mendapat role ini setelah KTM disetujui admin atau OCR lulus.
    </field>
</record>

<!-- 3. Role ADMIN: Mewarisi SEMUA hak Seller + hak tambahan admin -->
<record id="group_unitrade_admin" model="res.groups">
    <field name="name">Admin / Manager</field>
    <field name="category_id" ref="module_category_unitrade"/>
    <!--
        implied_ids: Admin OTOMATIS mendapat semua hak Seller.
        Ini berarti admin tidak perlu di-assign ke dua group sekaligus.
    -->
    <field name="implied_ids" eval="[(4, ref('group_unitrade_seller'))]"/>
</record>
```

> 💡 **Penjelasan:** File XML ini mendefinisikan hierarki role UniTrade di Odoo. `ir.module.category` adalah "nama folder" di menu Settings → Users & Companies → Groups — membantu admin mengorganisir banyak group. Yang menarik adalah field `implied_ids` pada group Admin: ini berarti siapapun yang di-assign ke group `group_unitrade_admin` secara otomatis juga mendapat semua hak dari `group_unitrade_seller`. Admin tidak perlu di-assign ke dua group sekaligus — ini mencegah human error (lupa assign satu group) dan memudahkan manajemen. Sintaks `(4, ref('group_unitrade_seller'))` adalah sintaks khusus Odoo untuk Many2many: angka `4` berarti "tambahkan relasi ke record dengan ID ini".

---

### Hierarki Role Lengkap

```
Belum login (Tamu/Public)
    ↓ registrasi email + OTP verified
base.group_user (Portal User / Pembeli)
    │  Bisa: browse produk, checkout, wishlist, CS AI
    │  Tidak bisa: buat produk, lihat dashboard seller
    ↓ upload KTM + OCR approved / admin approve
unitrade_seller.group_unitrade_seller (Penjual Terverifikasi)
    │  Bisa: semua hak Pembeli + buat produk, kelola toko, lihat pesanan masuk
    │  Tidak bisa: akses admin dashboard, lihat data seller lain
    ↓ ditunjuk oleh Odoo Superuser
unitrade_seller.group_unitrade_admin (Administrator UniTrade)
    │  Bisa: semua hak Seller + approve/reject KTM, lihat semua data
    │  Panel: /unitrade/admin dashboard
    ↓ Odoo superuser saja
base.group_system (Odoo Technical Admin)
    Bisa: semua hal termasuk konfigurasi teknis server
```

> 💡 **Penjelasan:** Diagram ini menunjukkan bagaimana seseorang "naik level" di UniTrade. Setiap level mewarisi semua kemampuan level di bawahnya, ditambah kemampuan baru. Yang penting diperhatikan: untuk naik dari Pembeli ke Penjual, diperlukan verifikasi KTM yang tidak bisa dilewati (OCR + review admin). Ini adalah "pintu gerbang" utama yang memastikan hanya mahasiswa UNISA aktif yang bisa berjualan. Role Admin tidak bisa diraih oleh user biasa — hanya Odoo Superuser yang bisa mengangkat seseorang menjadi admin, dan ini dilakukan secara manual oleh pengelola sistem.

---

### Pengecekan Role di Controller

```python
# unitrade_admin/controllers/admin_dashboard.py: L12-18
def _is_admin(self):
    """Cek apakah user yang sedang login memiliki hak admin UniTrade."""
    user = request.env.user
    return (
        user.has_group('base.group_system') or
        user.has_group('unitrade_seller.group_unitrade_admin')
    )

@http.route('/unitrade/admin', type='http', auth='user', website=True)
def admin_dashboard(self, **kwargs):
    """
    auth='user' = harus login.
    Tapi login saja tidak cukup — harus cek role admin juga.
    """
    if not self._is_admin():
        return request.render('unitrade_admin.admin_forbidden', {
            'error': 'Akun Anda tidak memiliki akses admin UniTrade.'
        })
    # Lanjutkan render dashboard...

# unitrade_admin/models/sale_order.py: L65-68
def _unitrade_is_admin(self, user=None):
    """Cek role admin di level model."""
    user = user or self.env.user
    return (
        user.has_group('unitrade_seller.group_unitrade_admin') or
        user.has_group('base.group_system')
    )
```

> 💡 **Penjelasan:** Perhatikan bahwa pengecekan role dilakukan di DUA tempat: di Controller (line `_is_admin()`) dan di Model (`_unitrade_is_admin()`). Mengapa dua kali? Defense in depth — bahkan jika seseorang berhasil memanggil method model secara langsung (misalnya via Odoo RPC), pengecekan di level model tetap menghalangi. `user.has_group('nama.group')` adalah cara idiomatik Odoo untuk cek keanggotaan group — Odoo secara internal melakukan JOIN ke tabel `res_groups_users_rel` di PostgreSQL. Jika akses ditolak, sistem me-render halaman "forbidden" yang informatif, bukan menampilkan error 500 yang membingungkan.

---

## Lapisan 3: Access Control List (ACL)

File `ir.model.access.csv` mendefinisikan hak **CRUD** setiap role terhadap setiap model:

**Format:** `id, name, model_id:id, group_id:id, perm_read, perm_write, perm_create, perm_unlink`

```csv
# unitrade_seller/security/ir.model.access.csv

# Model: unitrade.seller (Toko Penjual)
# --- User biasa: TIDAK boleh akses tabel seller sama sekali ---
access_unitrade_seller_user,unitrade.seller.user,model_unitrade_seller,base.group_user,0,0,0,0

# --- Seller: R/W/C boleh, tapi TIDAK boleh hapus toko sendiri ---
access_unitrade_seller_seller,unitrade.seller.seller,model_unitrade_seller,
  unitrade_seller.group_unitrade_seller,1,1,1,0

# --- Admin: akses PENUH termasuk hapus ---
access_unitrade_seller_admin,unitrade.seller.admin,model_unitrade_seller,
  unitrade_seller.group_unitrade_admin,1,1,1,1

# Model: unitrade.seller.verification (KTM Verification)
# --- Seller: hanya bisa LIHAT verifikasi miliknya (read-only) ---
access_seller_verif_seller,seller.verif.seller,model_unitrade_seller_verification,
  unitrade_seller.group_unitrade_seller,1,0,0,0

# --- Admin: bisa approve/reject (write diizinkan) ---
access_seller_verif_admin,seller.verif.admin,model_unitrade_seller_verification,
  unitrade_seller.group_unitrade_admin,1,1,1,0
```

**Arti kolom:**
- `perm_read = 1` → boleh SELECT / search
- `perm_write = 1` → boleh UPDATE / write()
- `perm_create = 1` → boleh INSERT / create()
- `perm_unlink = 1` → boleh DELETE / unlink()

> 💡 **Penjelasan:** File CSV ini adalah "matriks izin" yang menentukan siapa boleh melakukan apa terhadap setiap tabel. Setiap baris mewakili satu aturan akses. Angka `0` dan `1` di empat kolom terakhir seperti saklar on/off untuk operasi Read, Write, Create, Delete. Contoh nyata: Seller bisa membuat dan mengedit tokonya (`1,1,1,0`) tapi tidak bisa menghapusnya (unlink = `0`) — ini melindungi integritas data histori. User biasa sama sekali tidak bisa mengakses tabel seller (`0,0,0,0`) — bahkan operasi baca pun dilarang. Jika user yang tidak berhak mencoba mengakses model ini via ORM, Odoo akan otomatis melempar exception `AccessError` tanpa perlu kode pengecekan tambahan di controller.

---

## Lapisan 4: Record Rules (Row-Level Security)

```xml
<!-- unitrade_seller/security/security.xml -->

<!--
    RULE 1: Seller hanya bisa lihat & edit TOKO MILIKNYA SENDIRI
    domain_force = filter SQL yang OTOMATIS ditambahkan ke SETIAP query
    Odoo tidak perlu developer tambahkan filter manual di setiap tempat
-->
<record id="rule_seller_own" model="ir.rule">
    <field name="name">Seller: Own Record Only</field>
    <field name="model_id" ref="model_unitrade_seller"/>
    <!--
        domain_force ini dikonversi Odoo menjadi:
        WHERE user_id = [ID_USER_YANG_SEDANG_LOGIN]
        user.id adalah variabel built-in di domain ir.rule
    -->
    <field name="domain_force">[('user_id', '=', user.id)]</field>
    <field name="groups" eval="[(4, ref('group_unitrade_seller'))]"/>
    <field name="perm_read" eval="True"/>
    <field name="perm_write" eval="True"/>
    <field name="perm_unlink" eval="False"/>
</record>

<!--
    RULE 2: Admin bisa melihat SEMUA toko (tidak ada filter)
-->
<record id="rule_seller_admin" model="ir.rule">
    <field name="name">Seller: Admin Full Access</field>
    <field name="model_id" ref="model_unitrade_seller"/>
    <!-- (1, '=', 1) = kondisi selalu TRUE = tidak ada filter = lihat semua -->
    <field name="domain_force">[(1, '=', 1)]</field>
    <field name="groups" eval="[(4, ref('group_unitrade_admin'))]"/>
</record>
```

> 💡 **Penjelasan:** Record Rule adalah mekanisme keamanan di level baris data (row-level security), berbeda dari ACL yang bekerja di level tabel. ACL menjawab "apakah user ini boleh mengakses tabel ini?", sedangkan Record Rule menjawab "baris mana saja yang boleh dilihat user ini?". Field `domain_force` berisi filter Odoo domain yang **otomatis disisipkan ke SETIAP query SQL** untuk group yang ditentukan. Artinya, developer tidak perlu ingat untuk menambahkan filter `user_id = ...` di setiap baris kode — Odoo melakukannya secara transparan. Domain `(1, '=', 1)` adalah trik untuk "tidak ada filter" (selalu true), digunakan untuk admin yang perlu lihat semua data.

**Demonstrasi efek Record Rule:**
```python
# Seller A (user.id = 5) menjalankan kode ini:
shops = request.env['unitrade.seller'].search([])  # Tanpa filter apapun

# SQL yang BENAR-BENAR dieksekusi oleh Odoo:
# SELECT * FROM unitrade_seller WHERE user_id = 5  ← filter ditambahkan otomatis
# Hasilnya: hanya toko milik Seller A

# Admin (group_unitrade_admin) menjalankan kode yang sama:
shops = request.env['unitrade.seller'].search([])

# SQL yang dieksekusi:
# SELECT * FROM unitrade_seller WHERE (1 = 1)  ← tidak ada filter
# Hasilnya: SEMUA toko dari semua seller
```

> 💡 **Penjelasan:** Inilah kekuatan Record Rule — keamanan berjalan secara otomatis tanpa developer perlu menulis filter di setiap controller atau service. Bahkan jika developer lupa menambahkan domain filter di kode mereka, Record Rule tetap memproteksi data. Ini mengurangi risiko "security by mistake" di mana keamanan bergantung pada ingatan developer. Kode yang sama (`search([])`) menghasilkan SQL yang berbeda tergantung siapa yang menjalankannya — itulah transparansi yang disediakan oleh ORM Odoo.

---

## Lapisan 5: Keamanan Transaksi

### A. SHA-512 Signature Validation

```python
# unitrade_payment/controllers/main.py: L1285-1301
def _validate_midtrans_signature(self, payload):
    """
    Setiap notifikasi dari Midtrans harus divalidasi signature-nya.
    Tanpa ini, siapapun bisa mengirim request palsu dan memalsukan pembayaran.

    Formula signature Midtrans (versi simplifikasi):
    SHA512(order_id + status_code + gross_amount + server_key)
    """
    # Ambil server_key dari database (rahasia, hanya diketahui Midtrans + kita)
    server_key = self._get_midtrans_param('unitrade.midtrans.server_key')
    if not server_key:
        _logger.warning('Midtrans server key is not configured.')
        return False

    signature = payload.get('signature_key')
    if not signature:
        _logger.warning('Midtrans webhook missing signature_key.')
        return False

    # Buat string yang sama seperti yang Midtrans gunakan untuk sign
    raw = '%s%s%s%s' % (
        payload.get('order_id') or '',
        payload.get('status_code') or '',
        payload.get('gross_amount') or '',
        server_key,
    )
    # Hitung SHA-512 dan bandingkan
    expected = hashlib.sha512(raw.encode('utf-8')).hexdigest()
    return str(signature).lower() == expected.lower()
```

> 💡 **Penjelasan:** Endpoint webhook (`/unitrade/payment/midtrans/webhook`) menggunakan `auth='none'` — artinya siapapun bisa mengirim POST ke sana tanpa perlu login. Ini diperlukan karena yang mengirim adalah server Midtrans, bukan browser user. Namun hal ini membuka celah: penyerang bisa mengirim POST palsu yang mengklaim "order sudah dibayar" tanpa benar-benar membayar. Validasi signature SHA-512 menutup celah ini. Hanya pihak yang mengetahui `server_key` (rahasia antara UniTrade dan Midtrans) yang bisa menghasilkan signature yang benar. SHA-512 dipilih karena sangat sulit di-reverse (tidak bisa mengetahui `server_key` dari signature yang dihasilkan) dan resisten terhadap collision attack.

---

### B. Row-Level Locking (Mencegah Race Condition)

```python
# unitrade_payment/models/sale_order.py: L780
def _unitrade_lock_payment_order_row(self):
    """
    Kunci baris order di PostgreSQL sebelum memproses pembayaran.

    MASALAH TANPA LOCKING:
    - Request A dan Request B sama-sama membaca order yang sama
    - Keduanya melihat state='draft' dan melanjutkan proses
    - Keduanya membuat payment intent → order dibayar DUA KALI

    SOLUSI: SELECT FOR UPDATE
    - PostgreSQL mengunci baris saat transaksi A berjalan
    - Transaksi B harus MENUNGGU sampai A selesai
    - Ketika B mendapat giliran, state sudah berubah → B berhenti
    """
    self.env.cr.execute(
        'SELECT id FROM sale_order WHERE id = %s FOR UPDATE',
        [self.id]
    )
```

> 💡 **Penjelasan:** Race condition adalah bug yang hanya muncul ketika dua request terjadi hampir bersamaan — sangat sulit direproduksi tapi bisa sangat mahal dampaknya (double payment, double order). Analoginya: bayangkan dua kasir di toko yang sama-sama mengambil barang terakhir dari rak secara bersamaan karena keduanya melihat stok = 1. `SELECT FOR UPDATE` adalah instruksi ke PostgreSQL untuk mengunci baris tersebut: "jangan izinkan transaksi lain membaca atau mengubah baris ini sampai saya selesai". Transaksi lain yang mencoba mengakses baris yang dikunci akan diblokir (menunggu) sampai kunci dilepas. Hasilnya: operasi kritis seperti pembuatan payment intent dijamin hanya terjadi sekali meskipun ada seratus request bersamaan.

---

### C. Idempotency Webhook

```python
# unitrade_payment/controllers/main.py: L1464-1467
event_key = 'midtrans:%s' % request_key

# Cek di database: apakah event ini sudah pernah diproses?
existing_event = event_env.search([('event_key', '=', event_key)], limit=1)
if existing_event and existing_event.state == 'processed':
    # Webhook duplikat (Midtrans kirim ulang): kembalikan OK tanpa proses
    return self._json_response({'status': 'ok', 'duplicate': True})

# Kalau belum ada: simpan event dan proses
event = event_env.create({
    'name': event_key,
    'provider': 'midtrans',
    'event_key': event_key,
    'state': 'received',
})
# ... proses pembayaran ...
event.write({'state': 'processed'})
```

> 💡 **Penjelasan:** Idempotency berarti "melakukan operasi yang sama berkali-kali menghasilkan hasil yang sama seperti melakukannya sekali". Midtrans memiliki mekanisme retry — jika server kita tidak merespons dalam waktu tertentu (misalnya karena restart), Midtrans akan mengirim webhook yang sama lagi. Tanpa idempotency, order bisa diproses dua kali: saldo escrow ter-double, notifikasi dikirim dua kali, dll. Dengan menyimpan `event_key` (kombinasi unik dari provider + order_id + status) ke database dan mengeceknya sebelum proses, kita memastikan setiap event unik hanya diproses tepat satu kali. Response `{'duplicate': True}` tetap mengembalikan HTTP 200 agar Midtrans tidak terus-menerus retry.

---

## Kerahasiaan Data: Right to Erasure (Penghapusan Akun)

```python
# unitrade_theme/models/res_users.py: L91-135
def unitrade_privacy_deactivate(self, reason=False, ip_address=False, user_agent=False, session_id=False):
    """
    Privacy-safe account deletion mengikuti prinsip GDPR.

    PENTING: Data TIDAK dihapus permanen karena:
    1. Histori transaksi (sale.order) masih dibutuhkan untuk akuntabilitas
    2. Data escrow (unitrade.escrow.ledger) masih dibutuhkan untuk audit
    3. Tapi identitas personal tidak lagi bisa dilacak ke individu

    YANG DIHAPUS: nama, email, nomor HP, foto profil, alamat
    YANG DIPERTAHANKAN: nomor order, nominal transaksi, tanggal
    """
    for user in self.sudo():
        # Generate kode acak untuk referensi anonimisasi
        anonymized_ref = 'deleted-user-%s-%s' % (user.id, uuid.uuid4().hex[:10])

        # Hapus data personal dari profil (res.partner)
        partner = user.partner_id.sudo()
        partner.write({
            'name': 'Pengguna Dihapus',  # Nama diganti generic
            'email': False,               # Email dihapus
            'phone': False,
            'mobile': False,
            'street': False,
            'street2': False,
            'image_1920': False,          # Foto profil dihapus
        })

        # Nonaktifkan akun dan tandai sebagai dianonimisasi
        user.write({
            'active': False,             # Soft delete (tidak bisa login)
            'x_privacy_deactivated': True,
            'x_privacy_anonymized_ref': anonymized_ref,
            'x_privacy_deactivated_at': fields.Datetime.now(),
        })

        # Catat event penghapusan ke audit trail (untuk dokumentasi)
        self.env['unitrade.security.activity'].sudo().record_activity(
            user,
            'deactivate_anonymize',
            title='Akun dinonaktifkan dan dianonimisasi',
            detail='Pengguna menghapus akun sesuai permintaan.',
            ip_address=ip_address,
        )
```

> 💡 **Penjelasan:** Menghapus akun pengguna di sistem marketplace lebih kompleks dari sekedar `DELETE FROM res_users WHERE id = ?`. Histori transaksi (sale.order) yang terhubung ke akun tersebut masih dibutuhkan untuk keperluan akuntansi, audit pajak, dan penyelesaian dispute. Jika kita hard-delete akun, semua relasi database akan rusak (foreign key constraint violation). Solusinya adalah **anonimisasi (anonymization)**: data identitas personal dihapus (nama → "Pengguna Dihapus", email → NULL), tapi record akun dan transaksinya tetap ada. `active = False` adalah "soft delete" Odoo — akun tidak muncul di pencarian normal, tidak bisa login, tapi record-nya masih ada di database. Kode acak `anonymized_ref` memungkinkan audit internal (mengetahui record ini pernah ada) tanpa mengekspos identitas aslinya.
