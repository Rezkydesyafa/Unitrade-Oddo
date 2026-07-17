# 02 — Modul Odoo & Integrasi Antar Modul

> **Modul di Odoo** = seperti "plugin" atau "paket fitur" yang bisa di-install secara terpisah.
> Setiap modul UniTrade adalah satu folder Python dengan struktur tertentu.

---

## Cara Odoo Memuat Modul (Mekanisme Dasar)

Ketika Odoo di-start, ia membaca semua modul yang terinstal dari database.
Setiap modul terdiri dari **3 komponen wajib**:

```
unitrade_theme/          ← nama folder = nama modul
├── __init__.py          ← entry point Python, import sub-paket
├── __manifest__.py      ← metadata modul (nama, versi, dependensi, file)
├── models/
│   ├── __init__.py      ← daftar semua file model
│   ├── otp.py           ← satu model = satu file (umumnya)
│   └── res_users.py
├── controllers/
│   ├── __init__.py      ← daftar semua file controller
│   └── controllers.py
├── views/
│   └── login_templates.xml   ← template HTML (QWeb)
├── static/
│   └── src/js/
│       └── product_detail.js ← JavaScript frontend
└── security/
    ├── ir.model.access.csv   ← hak akses model
    └── security.xml          ← definisi grup dan record rules
```

> 💡 **Cara baca struktur di atas:** Setiap folder punya tanggung jawab yang jelas. `models/` untuk logika data, `controllers/` untuk menangani HTTP request, `views/` untuk tampilan HTML, `security/` untuk hak akses. Ini bukan aturan asal-asalan — Odoo membaca folder dengan urutan tertentu saat startup, dan jika strukturnya salah, modul tidak akan dimuat.

---

### 1. `__init__.py` — Entry Point Python

```python
# unitrade_theme/__init__.py

# Baris ini memberitahu Python untuk mengimpor semua yang ada di folder models/
# Odoo akan membaca setiap file .py di sana dan mendaftarkan model-modelnya
from . import models

# Sama untuk folder controllers/
from . import controllers

# Tanda titik (.) = "dari folder yang sama" (relative import)


def post_init_hook(env):
    """
    Fungsi ini OPSIONAL.
    Dipanggil SATU KALI saat modul pertama kali di-install.
    Berguna untuk setup data awal yang tidak bisa dilakukan via XML.

    env = Odoo environment (akses ke semua model)
    """
    # Contoh: pastikan currency IDR (Rupiah) adalah default
    env['res.company']._unitrade_enforce_idr_currency()
```

> 💡 **Penjelasan:** File `__init__.py` adalah "pintu masuk" sebuah modul Python. Ketika Odoo mengimpor modul `unitrade_theme`, Python membaca file ini terlebih dahulu. Dua baris `from . import models` dan `from . import controllers` memberi tahu Python untuk masuk ke subfolder tersebut dan mengimpor semua file di dalamnya. Tanpa baris ini, model dan controller yang kita tulis tidak akan pernah "diketahui" oleh Odoo. Fungsi `post_init_hook` adalah bonus — ia dipanggil Odoo tepat satu kali saat instalasi pertama, berguna untuk setup data awal seperti memastikan mata uang Rupiah sudah terdaftar.

```python
# unitrade_theme/models/__init__.py
# File ini mendaftarkan SEMUA model yang ada di folder models/
# Urutan import bisa penting jika satu model bergantung pada model lain

from . import otp               # Impor unitrade_theme/models/otp.py
from . import res_users         # Impor models/res_users.py (override res.users)
from . import sale_order        # Impor models/sale_order.py (override sale.order)
from . import customer_service  # Impor models/customer_service.py
from . import security_activity # Impor models/security_activity.py
from . import website           # Impor models/website.py (override website)
```

> 💡 **Penjelasan:** Ini adalah `__init__.py` khusus untuk subfolder `models/`. Setiap baris `from . import nama_file` berarti "impor file `nama_file.py` dari folder ini". Urutan baris ini bisa penting — jika model B bergantung pada model A (misalnya ada relasi Many2one), maka model A harus diimpor lebih dulu agar saat Python memproses B, definisi A sudah tersedia. Tanpa file ini, Odoo tidak akan mengetahui keberadaan model-model yang kita buat.

---

### 2. `__manifest__.py` — Metadata & Pendaftaran File

```python
# unitrade_theme/__manifest__.py

{
    'name': 'UniTrade Theme',
    'version': '17.0.1.0.0',
    # Format versi Odoo: <odoo_version>.<major>.<minor>.<patch>
    # 17.0 = untuk Odoo 17, 1.0.0 = versi modul kita

    'category': 'Website',
    'summary': 'UniTrade Marketplace Theme dan Fitur Utama',

    # ── DEPENDENSI ────────────────────────────────────────────────────────
    'depends': [
        'website',          # Modul website bawaan Odoo (routing, QWeb)
        'website_sale',     # Modul e-commerce Odoo (cart, checkout, shop)
        'website_sale_stock', # Cek stok di halaman produk
        'portal',           # Modul portal user (my/ routes)
        'auth_signup',      # Halaman /web/signup bawaan Odoo
        'auth_oauth',       # OAuth (Google login) bawaan Odoo
    ],
    # Odoo akan memastikan semua modul di 'depends' terinstall dulu
    # sebelum unitrade_theme bisa diinstall

    # ── DATA FILE (dimuat ke database saat install/upgrade) ───────────────
    'data': [
        # URUTAN PENTING: security harus pertama
        'security/ir.model.access.csv',    # Hak akses CRUD per model per grup
        'security/security.xml',            # Definisi grup dan record rules

        'data/unitrade_config.xml',         # Parameter konfigurasi default
        'data/sequences.xml',               # Sequence nomor tiket, dll

        'views/homepage.xml',               # Template halaman beranda
        'views/login_templates.xml',        # Template halaman login/signup/OTP
        'views/product_templates.xml',      # Template halaman detail produk
        'views/checkout_templates.xml',     # Template halaman checkout
        # ... dst
    ],

    # ── ASET FRONTEND (JS/CSS yang dikirim ke browser) ───────────────────
    'assets': {
        'web.assets_frontend': [
            # web.assets_frontend = bundle untuk halaman publik (website)
            # Odoo akan menggabungkan semua file ini menjadi satu bundle

            'unitrade_theme/static/src/css/output.css',
            # File CSS hasil kompilasi Tailwind
            # npm run build → menghasilkan output.css dari semua class tw- yang dipakai

            'unitrade_theme/static/src/js/main.js',         # Script global
            'unitrade_theme/static/src/js/product_detail.js', # Halaman produk
            'unitrade_theme/static/src/js/profile.js',      # Halaman profil
            'unitrade_theme/static/src/js/checkout.js',     # Halaman checkout
        ],
    },

    'post_init_hook': 'post_init_hook',
    # Referensi ke fungsi di __init__.py yang dipanggil saat install
}
```

> 💡 **Penjelasan:** File `__manifest__.py` adalah "kartu identitas" sebuah modul Odoo. Ada tiga bagian terpenting di sini:
> - **`depends`**: Seperti `requirements.txt` di Python biasa. Odoo tidak akan menginstall modul kita jika modul yang ada di daftar ini belum ada. Ini mencegah error karena fitur yang dibutuhkan belum siap.
> - **`data`**: Daftar file XML/CSV yang akan diproses dan disimpan ke database saat instalasi. Urutan file di sini sangat penting — `security/` harus paling awal karena file lain (views, dll) mungkin merujuk ke grup/model yang didefinisikan di security. Jika dibalik, Odoo akan error karena merujuk sesuatu yang belum ada.
> - **`assets`**: File JavaScript dan CSS yang akan disertakan di setiap halaman website. Odoo menggabungkan semua file ini menjadi satu file besar (bundle) untuk performa yang lebih baik.

---

## Integrasi ke Modul Bawaan Odoo: Pola `_inherit`

> **`_inherit`** adalah mekanisme paling penting di Odoo.
> Memungkinkan kita **menambah field dan method ke model yang sudah ada**
> tanpa mengubah kode Odoo core sama sekali.
>
> Analoginya seperti "warisan" di OOP: kita mewarisi class yang ada
> dan menambah/override method-nya.

### Contoh 1: Menambah Field ke `res.users` (Tabel User)

```python
# unitrade_theme/models/res_users.py

from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = 'res.users'
    # _inherit = 'res.users' → "Saya extend model res.users yang sudah ada"
    # Tidak ada _name = ... karena kita TIDAK membuat model baru
    # Odoo akan menambahkan field-field ini ke tabel res_users yang sudah ada
    # via ALTER TABLE (saat install/upgrade modul)

    # Field baru yang ditambahkan UniTrade ke setiap user:

    is_otp_verified = fields.Boolean(
        string='Is OTP Verified',
        default=False
        # False = belum verifikasi OTP, True = sudah
        # Cek ini digunakan di controller login untuk paksa redirect ke OTP
    )

    x_gender = fields.Selection([
        ('male', 'Laki-laki'),
        ('female', 'Perempuan'),
    ], string='Jenis Kelamin')
    # Prefix x_ = konvensi untuk field kustom (custom fields)

    x_is_seller = fields.Boolean(
        string='Is Seller',
        default=False
        # True = user sudah diverifikasi sebagai penjual
        # Diset menjadi True saat KTM diapprove
    )

    x_seller_id = fields.Many2one(
        'unitrade.seller',
        string='Toko Penjual',
        ondelete='set null'
        # Many2one = foreign key ke tabel unitrade_seller
        # ondelete='set null' = jika toko dihapus, field ini jadi NULL (bukan error)
    )

    # Method baru yang ditambahkan ke semua user
    def unitrade_allows_notification(self, category):
        """Cek apakah user mau menerima notifikasi kategori tertentu."""
        if category == 'transaction':
            return bool(self.x_notify_all and self.x_notify_transaction)
        return bool(self.x_notify_all)
```

> 💡 **Penjelasan:** Ini adalah kekuatan utama Odoo. Dengan `_inherit = 'res.users'`, kita tidak membuat tabel baru — kita menambahkan kolom baru ke tabel `res_users` yang sudah ada di PostgreSQL. Odoo akan otomatis menjalankan perintah `ALTER TABLE` saat modul di-install. Hasilnya, setiap user Odoo kini punya field tambahan seperti `is_otp_verified` dan `x_is_seller` yang digunakan UniTrade. Prefix `x_` pada nama field adalah konvensi Odoo untuk menandai bahwa field tersebut adalah kustom (bukan bawaan Odoo core), memudahkan identifikasi saat debugging atau migrasi.

**Efek di PostgreSQL:** Odoo otomatis menjalankan:
```sql
-- Saat modul di-install pertama kali:
ALTER TABLE res_users
ADD COLUMN is_otp_verified BOOLEAN DEFAULT FALSE,
ADD COLUMN x_gender VARCHAR,
ADD COLUMN x_is_seller BOOLEAN DEFAULT FALSE,
ADD COLUMN x_seller_id INTEGER REFERENCES unitrade_seller(id);

-- Saat modul di-upgrade (ada field baru):
ALTER TABLE res_users ADD COLUMN x_new_field VARCHAR;
```

> 💡 **Penjelasan:** Query SQL ini dijalankan secara otomatis oleh Odoo — developer tidak perlu menulisnya sendiri. Saat kita menjalankan `odoo -u unitrade_theme` (upgrade modul), Odoo membandingkan definisi field di kode Python dengan kolom yang ada di database, lalu mengeksekusi perintah `ALTER TABLE` untuk menyamakan keduanya. Ini yang membuat pengembangan modul Odoo lebih aman karena perubahan skema database dilakukan secara terkontrol melalui ORM.

---

### Contoh 2: Override Method di `sale.order`

```python
# unitrade_payment/models/sale_order.py

class SaleOrderUniTrade(models.Model):
    _inherit = 'sale.order'
    # Extend model sale.order bawaan Odoo

    # Tambah field baru ke tabel sale_order
    x_payment_status = fields.Selection([
        ('pending', 'Menunggu'),
        ('paid', 'Dibayar'),
        ('expired', 'Kadaluarsa'),
    ], default='pending', readonly=True, tracking=True)
    # tracking=True = Odoo otomatis catat setiap perubahan di chatter

    x_escrow_state = fields.Selection([
        ('none', 'Belum Ada'),
        ('held', 'Ditahan'),
        ('released', 'Dirilis'),
        ('disputed', 'Disengketakan'),
    ], default='none', readonly=True)

    def action_confirm(self):
        """
        Override method action_confirm() bawaan Odoo.
        Dipanggil saat order dikonfirmasi.

        POLA: Panggil super() dulu (Odoo asli), baru tambahkan logika kita.
        Urutan ini penting agar Odoo punya kesempatan memproses dulu
        sebelum kita modifikasi hasilnya.
        """
        # 1. Jalankan logic konfirmasi standar Odoo
        res = super(SaleOrderUniTrade, self).action_confirm()
        # super() = panggil method dari class parent (sale.order bawaan Odoo)

        # 2. Tambahkan logika kustom UniTrade SETELAH Odoo selesai
        self._unitrade_setup_escrow()
        # Buat escrow ledger untuk order yang baru dikonfirmasi

        self._unitrade_notify_seller_new_order()
        # Kirim notifikasi ke penjual bahwa ada order baru

        return res  # Kembalikan hasil dari super() (biasanya True)
```

> 💡 **Penjelasan:** Di sini kita tidak hanya menambah field, tapi juga mengubah perilaku method yang sudah ada. Ketika pembeli mengkonfirmasi order, Odoo biasanya hanya mengubah status order. Dengan `_inherit`, kita menyisipkan logika tambahan: setelah Odoo selesai memprosesnya (via `super()`), kita langsung otomatis membuat escrow ledger dan mengirim notifikasi ke penjual. Kuncinya adalah memanggil `super()` terlebih dahulu — ini memastikan alur standar Odoo tetap berjalan, dan kita hanya menambahkan di atasnya tanpa mengganggu fungsionalitas dasar.

---

### Contoh 3: Override Controller Login Bawaan Odoo

```python
# unitrade_theme/controllers/controllers.py

# Import class controller bawaan Odoo yang ingin di-override
from odoo.addons.auth_oauth.controllers.main import OAuthLogin

class UnitradeAuthSignup(OAuthLogin):
    """
    Mewarisi OAuthLogin (yang mewarisi Home, yang mewarisi Controller).
    Ini adalah rantai warisan (inheritance chain) di Odoo.

    OAuthLogin → menangani login Google OAuth
    Home       → menangani /web/login dan /web/signup standar
    Controller → class dasar semua controller Odoo
    """

    @http.route()
    # @http.route() TANPA argumen path = override route yang SAMA dengan parent
    # Odoo akan menggantikan handler lama dengan yang baru ini
    def web_login(self, *args, **kw):
        """Override /web/login untuk memaksa verifikasi OTP."""

        # Normalisasi input: trim whitespace, lowercase email
        if request.httprequest.method == 'POST' and request.params.get('login'):
            login_value = _normalize_login(request.params.get('login'))
            if not _is_email(login_value):
                # Tampilkan form login lagi dengan pesan error
                return self._render_login_form_error(
                    login_value,
                    "Masukkan email yang valid untuk login."
                )

        # LANGKAH 1: Panggil login standar Odoo (cek username+password di database)
        response = super().web_login(*args, **kw)
        # Setelah super() berhasil: request.session.uid = ID user yang login

        # LANGKAH 2: Setelah login berhasil, cek OTP
        if request.httprequest.method == 'POST' and request.session.uid:
            user = request.env['res.users'].sudo().browse(request.session.uid)

            if user.exists() and not user.is_otp_verified:
                # User berhasil login tapi OTP belum diverifikasi

                login_val = user.login
                # Simpan email sebelum logout

                request.session.logout(keep_db=True)
                # LOGOUT PAKSA → hapus session yang baru saja dibuat
                # Ini mencegah user bypass OTP dengan cara apapun
                # keep_db=True = tetap di database yang sama

                # Redirect ke halaman verifikasi OTP
                return self._generate_and_redirect_otp(user, login_val)
                # Fungsi ini: generate OTP → kirim email → redirect /web/verify-otp

            # Login sukses DAN OTP sudah valid
            if user.exists():
                # Catat login ke audit trail (untuk forensik keamanan)
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

> 💡 **Penjelasan:** Ini contoh pola `_inherit` yang diterapkan ke Controller (bukan Model). Odoo menggunakan sistem routing berbasis class inheritance — ketika class baru menggunakan `@http.route()` tanpa argumen, Odoo menggantikan handler lama dengan yang baru ini. Alurnya: user submit form login → Odoo memeriksa username+password seperti biasa (`super()`) → setelah berhasil, kita sisipkan pengecekan OTP. Jika OTP belum diverifikasi, session yang baru saja dibuat langsung kita hapus (`session.logout()`) agar user tidak bisa bypass verifikasi. Teknik "logout paksa" ini penting untuk keamanan — tanpa ini, user bisa langsung mengakses halaman lain setelah login meskipun belum OTP.

---

## Peta Integrasi Antar Modul UniTrade

Modul-modul UniTrade tidak berdiri sendiri — mereka saling berinteraksi melalui `self.env`:

```python
# Cara modul A memanggil model dari modul B:
# self.env['nama.model'] = akses model dari modul manapun

# Contoh: unitrade_theme memanggil unitrade.notification (modul berbeda)
# unitrade_theme/models/customer_service.py: L133-158

def _emit_customer_notification(self, event_code, title, message):

    # LANGKAH 1: Cek apakah modul unitrade_notification sudah terinstall
    # Ini PENTING untuk mencegah error jika modul belum ada
    if 'unitrade.notification' not in self.env.registry:
        return  # Modul belum ada? Skip saja, tidak error
        # self.env.registry = daftar semua model yang terdaftar di Odoo

    # LANGKAH 2: Akses model dari modul lain
    Notification = self.env['unitrade.notification'].sudo()
    # self.env['nama.model'] = cara standar akses model manapun di Odoo
    # .sudo() diperlukan karena kita buat notifikasi untuk user lain

    # LANGKAH 3: Panggil method di model tersebut
    for ticket in self.sudo():
        try:
            Notification.emit(
                user_id=ticket.user_id.id,     # Siapa penerima notifikasi
                event_code=event_code,          # Kode event untuk template
                payload={
                    'reference_model': ticket._name,  # 'unitrade.customer.ticket'
                    'reference_id': ticket.id,
                    'action_url': ticket._customer_ticket_url(),
                    # URL yang dibuka saat user klik notifikasi
                },
                channels=['in_app'],            # Kirim via notifikasi in-app
            )
        except Exception:
            # Jika notifikasi gagal, jangan crash seluruh proses
            # Tiket tetap dibuat meskipun notifikasi gagal
            _logger.exception(
                'Failed to emit notification for ticket %s', ticket.name
            )
```

> 💡 **Penjelasan:** Ini adalah cara modul-modul UniTrade saling berkomunikasi. Setiap modul bisa mengakses model dari modul lain cukup dengan `self.env['nama.model']` — tidak perlu import apapun selama modul tersebut sudah terinstall. Baris pengecekan `if 'unitrade.notification' not in self.env.registry` adalah praktik terbaik untuk membuat modul yang "toleran" — jika seseorang menghapus modul notifikasi, modul lain tidak akan crash, melainkan hanya melewati bagian notifikasi. Pola `try/except` di akhir juga penting: kegagalan kirim notifikasi tidak boleh membatalkan pembuatan tiket CS yang lebih penting.

---

## Tabel URL → Controller → Model

Setiap URL di UniTrade ditangani oleh Controller tertentu yang kemudian memanggil Model:

| URL | Method | Controller | Model yang Dipanggil |
|-----|--------|-----------|---------------------|
| `/` | GET | `Website` (Odoo core) | `product.template` |
| `/web/signup` | POST | `UnitradeAuthSignup.web_auth_signup` | `res.users`, `unitrade.otp` |
| `/web/login` | POST | `UnitradeAuthSignup.web_login` | `res.users`, `unitrade.security.activity` |
| `/web/verify-otp` | POST | `UnitradeOTPController` | `unitrade.otp` |
| `/seller-verification` | POST | `SellerVerificationController` | `unitrade.seller.verification` + Google Vision |
| `/shop` | GET | Odoo `WebsiteSale` | `product.template` |
| `/unitrade/product/stock/validate` | JSON | `UnitradeCartController` | `product.product` |
| `/unitrade/wishlist/toggle` | JSON | `UnitradeWishlistController` | `unitrade.wishlist` |
| `/unitrade/payment/midtrans/webhook` | POST | `UnitradePaymentController` | `unitrade.payment.intent`, `sale.order` |
| `/my/notifications/unread_count` | JSON | `UnitradeNotificationController` | `unitrade.notification` |
| `/customer-service/chat/send` | JSON | `UnitradeCsPortal` | `unitrade.cs.ai.service` → Gemini AI |
| `/unitrade/mapbox/geocode` | JSON | `UnitradeProfileController` | — (proxy ke Mapbox API) |
| `/unitrade/admin` | GET | `UnitradeAdminController` | `unitrade.admin.stats` |

> 💡 **Penjelasan:** Tabel ini adalah "peta jalan" sistem UniTrade. Kolom `Method` menunjukkan apakah URL menggunakan HTTP GET (ambil data), POST (kirim data form), atau JSON (AJAX). Kolom `Controller` adalah file Python yang menangani request, dan `Model yang Dipanggil` adalah model/tabel database yang dibaca atau diubah. Perhatikan baris `/unitrade/mapbox/geocode` — controller ini tidak memanggil model database, melainkan langsung memproxy request ke API Mapbox eksternal. Ini adalah teknik keamanan agar token Mapbox tidak terekspos ke browser.

---

## Cara Modul Baru Ditambahkan (Extensibility)

Ini adalah kekuatan utama arsitektur Odoo. Ketika ada kebutuhan baru:

```python
# Contoh: modul unitrade_review (ulasan produk) ditambahkan belakangan

# 1. Buat file __manifest__.py
{
    'name': 'UniTrade Review',
    'depends': [
        'unitrade_theme',    # Butuh unitrade_theme dulu
        'website_sale',      # Butuh e-commerce Odoo
    ],
}

# 2. Extend model product.template (tambah field rating)
class ProductTemplateReview(models.Model):
    _inherit = 'product.template'

    x_average_rating = fields.Float(
        string='Rating Rata-rata',
        compute='_compute_average_rating',
        store=True  # Simpan di database untuk performa query
    )

    x_review_ids = fields.One2many(
        'unitrade.review',
        'product_id',
        string='Ulasan'
    )

# 3. Install modul → Odoo otomatis ALTER TABLE untuk tambah kolom baru
# 4. TIDAK perlu mengubah kode unitrade_theme atau modul lain sama sekali
```

> 💡 **Penjelasan:** Inilah prinsip **Open/Closed Principle** dalam arsitektur Odoo — sebuah sistem terbuka untuk ekstensi tapi tertutup untuk modifikasi. Ketika tim ingin menambahkan fitur ulasan produk, mereka tidak perlu menyentuh kode `unitrade_theme` atau modul lain yang sudah berjalan di production. Cukup buat modul baru `unitrade_review`, declare `_inherit = 'product.template'`, dan field baru langsung tersedia di semua produk yang sudah ada. Field `compute` dengan `store=True` berarti nilai rating dihitung otomatis dari data ulasan dan disimpan ke database — query pencarian produk berdasarkan rating tetap cepat karena hasilnya sudah tersimpan, tidak dihitung ulang setiap kali.

**Hasilnya:** Fitur ulasan langsung terintegrasi dengan produk yang sudah ada,
tanpa memodifikasi modul lain. Ini yang disebut **Open/Closed Principle** —
terbuka untuk ekstensi, tertutup untuk modifikasi.
