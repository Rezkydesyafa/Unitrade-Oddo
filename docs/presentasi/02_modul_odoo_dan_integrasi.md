# 02 — Modul Odoo & Integrasi Antar Modul

## Cara Odoo Memuat Modul (Mekanisme Dasar)

Setiap modul Odoo adalah sebuah **Python package** yang terdiri dari 3 komponen inti:

### 1. `__init__.py` — Entry Point Python

```python
# unitrade_theme/__init__.py
# Memberitahu Python untuk mengimpor sub-paket models dan controllers
from . import models      # Memuat semua file di folder models/
from . import controllers # Memuat semua file di folder controllers/

def post_init_hook(env):
    """Fungsi ini dijalankan SATU KALI saat modul pertama kali di-install."""
    # Contoh: set currency IDR sebagai default
    env['res.company']._unitrade_enforce_idr_currency()
```

### 2. `__manifest__.py` — Metadata & Pendaftaran File

```python
# unitrade_theme/__manifest__.py
{
    'name': 'UniTrade Theme',
    'version': '17.0.1.0.0',
    # Daftar modul Odoo yang harus sudah terinstall sebelum modul ini
    'depends': ['website', 'website_sale', 'website_sale_stock', 'portal', 'auth_signup', 'auth_oauth'],
    # File data yang dimuat ke database saat install/upgrade
    'data': [
        'security/ir.model.access.csv',   # Hak akses model
        'security/security.xml',           # Definisi grup dan record rules
        'data/unitrade_config.xml',        # Parameter konfigurasi default
        'views/homepage.xml',              # Template halaman beranda
        'views/login_templates.xml',       # Template halaman login/signup
        'views/product_templates.xml',     # Template halaman detail produk
        # ... dst
    ],
    # Aset frontend (JS/CSS) yang di-bundle dan dikirim ke browser
    'assets': {
        'web.assets_frontend': [
            'unitrade_theme/static/src/css/output.css',     # Tailwind CSS
            'unitrade_theme/static/src/js/main.js',         # Script global
            'unitrade_theme/static/src/js/product_detail.js', # Detail produk
            'unitrade_theme/static/src/js/profile.js',      # Halaman profil
            # ... dst
        ],
    },
    'post_init_hook': 'post_init_hook',  # Fungsi yang dipanggil saat install
}
```

### 3. `models/__init__.py` & `controllers/__init__.py` — Daftar File Python

```python
# unitrade_theme/models/__init__.py
from . import otp               # → models/otp.py
from . import res_users         # → models/res_users.py (override model bawaan)
from . import sale_order        # → models/sale_order.py (override model bawaan)
from . import customer_service  # → models/customer_service.py
from . import security_activity # → models/security_activity.py
from . import website           # → models/website.py (override model bawaan)
# ...

# unitrade_theme/controllers/__init__.py
from . import controllers       # → controllers/controllers.py (login, OTP, signup)
from . import cart              # → controllers/cart.py (keranjang)
from . import checkout          # → controllers/checkout.py (pembayaran)
from . import customer_service  # → controllers/customer_service.py
```

---

## Integrasi ke Modul Bawaan Odoo (_inherit Pattern)

Ini adalah mekanisme paling penting di Odoo. **`_inherit`** memungkinkan kita menambah field dan metode ke model yang sudah ada **tanpa mengubah kode Odoo core**.

### Contoh 1: Menambah Field ke `res.users` (User)

```python
# unitrade_theme/models/res_users.py — MEWARISI model bawaan Odoo
class ResUsers(models.Model):
    _inherit = 'res.users'  # <-- Extend model bawaan, bukan buat baru

    # Tambah field kustom UniTrade ke tabel res_users PostgreSQL
    is_otp_verified = fields.Boolean(string='Is OTP Verified', default=False)
    x_gender = fields.Selection([
        ('male', 'Laki-laki'),
        ('female', 'Perempuan'),
    ], string='Jenis Kelamin')
    x_terms_privacy_accepted = fields.Boolean(default=False, readonly=True)
    x_privacy_deactivated = fields.Boolean(default=False, readonly=True)

    # Tambah metode baru ke model res.users
    def unitrade_accepts_notification(self, category):
        """Return apakah user boleh menerima notifikasi kategori tertentu."""
        if category == 'transaction':
            return bool(self.x_notify_all and self.x_notify_transaction)
        return bool(self.x_notify_all)
```

**Efeknya di PostgreSQL:** Odoo otomatis menjalankan `ALTER TABLE res_users ADD COLUMN is_otp_verified BOOLEAN DEFAULT FALSE;` saat modul di-install/upgrade.

### Contoh 2: Menambah Field & Logika ke `sale.order` (Pesanan)

```python
# unitrade_payment/models/sale_order.py
class SaleOrderUniTrade(models.Model):
    _inherit = 'sale.order'  # <-- Sama-sama extend sale.order

    # Field Midtrans yang ditambahkan ke tabel sale_order
    x_midtrans_order_id = fields.Char(string='Midtrans Order ID', readonly=True, copy=False)
    x_payment_status = fields.Selection([
        ('pending', 'Menunggu'),
        ('paid', 'Dibayar'),
        ('expired', 'Kadaluarsa'),
    ], default='pending', tracking=True)
    x_escrow_state = fields.Selection([
        ('none', 'Belum Ada'),
        ('held', 'Ditahan'),
        ('released', 'Dirilis'),
    ], default='none', readonly=True)

    # Override metode bawaan Odoo
    def action_confirm(self):
        """Override: tambahkan logika escrow saat order dikonfirmasi."""
        res = super().action_confirm()  # Panggil logika asli Odoo dulu
        self._unitrade_setup_escrow()   # Tambahkan logika kustom
        return res
```

### Contoh 3: Menambah Logika ke `website` (Halaman Web)

```python
# unitrade_theme/models/website.py
class Website(models.Model):
    _inherit = 'website'

    def _unitrade_browser_title(self, path='', title='', default_title=''):
        """Override judul browser tab untuk semua halaman UniTrade."""
        exact_titles = {
            '/': 'Marketplace Mahasiswa Yogyakarta',
            '/shop': 'Belanja Produk | UniTrade',
            '/web/login': 'Masuk | UniTrade',
            '/web/signup': 'Daftar Akun | UniTrade',
            # ...
        }
        return exact_titles.get(path, title or 'UniTrade')
```

### Contoh 4: Override Controller Login Bawaan Odoo

```python
# unitrade_theme/controllers/controllers.py: L60-117
# Mewarisi OAuthLogin yang mewarisi controller bawaan Odoo
class UnitradeAuthSignup(OAuthLogin):
    """Override signup dan login untuk redirect ke verifikasi OTP."""

    @http.route()  # Tanpa path = override route yang sama dengan parent
    def web_login(self, *args, **kw):
        """Override web_login untuk memaksa verifikasi OTP."""
        # Normalisasi input login
        if request.httprequest.method == 'POST' and request.params.get('login'):
            login_value = _normalize_login(request.params.get('login'))
            if not _is_email(login_value):
                return self._render_login_form_error(login_value, "Masukkan email yang valid.")

        # Panggil login standar Odoo terlebih dahulu
        response = super().web_login(*args, **kw)

        # Setelah login berhasil, cek apakah OTP sudah diverifikasi
        if request.httprequest.method == 'POST' and request.session.uid:
            user = request.env['res.users'].sudo().browse(request.session.uid)
            if user.exists() and not user.is_otp_verified:
                # Paksa logout lagi, redirect ke halaman OTP
                request.session.logout(keep_db=True)
                return self._generate_and_redirect_otp(user, user.login)

            # Login sukses: catat ke audit trail
            user.unitrade_record_security_activity(
                'login',
                title='Login berhasil',
                ip_address=request.httprequest.remote_addr,
                session_id=request.session.sid,
            )
        return response
```

---

## Peta Integrasi Antar Modul UniTrade

```
┌─────────────────────────────────────────────────────────────────────┐
│                     MODUL INTI ODOO (Core)                          │
│  res.users  |  sale.order  |  product.template  |  website          │
└──────┬──────┴──────┬────────┴──────────┬──────────┴──────┬──────────┘
       │ _inherit    │ _inherit           │ _inherit         │ _inherit
┌──────▼──────┐ ┌────▼────────┐ ┌────────▼─────┐    ┌──────▼───────┐
│unitrade_    │ │unitrade_    │ │unitrade_     │    │unitrade_     │
│theme        │ │payment      │ │product_ext   │    │theme         │
│(OTP, login) │ │(Midtrans,   │ │(filter, stock│    │(website,     │
│             │ │ escrow)     │ │ validasi)    │    │ judul tab)   │
└──────┬──────┘ └────┬────────┘ └──────────────┘    └──────────────┘
       │              │ memanggil
       │              ▼
       │     ┌────────────────────┐
       │     │  unitrade_delivery  │
       │     │  (GoSend shipping) │
       │     └────────────────────┘
       │
       ├──► unitrade_seller (profil toko, KTM verif)
       │         ↓ menulis ke
       │    unitrade_seller_verification (model)
       │
       ├──► unitrade_notification (notifikasi real-time)
       │         ↑ dipanggil dari semua modul
       │
       ├──► unitrade_cs_ai (Gemini chatbot)
       │         ↑ menerima tiket dari
       │    unitrade_theme/models/customer_service.py
       │
       └──► unitrade_admin (dashboard monitoring)
                 ↑ membaca semua model via
            unitrade.admin.stats (AbstractModel)
```

### Cara Modul Memanggil Model dari Modul Lain

```python
# Contoh: customer_service.py memanggil unitrade.notification (modul berbeda)
# unitrade_theme/models/customer_service.py: L133-158

def _emit_customer_notification(self, event_code, title, message):
    # 1. Cek apakah modul unitrade_notification sudah terinstall
    if 'unitrade.notification' not in self.env.registry:
        return  # Graceful: tidak error jika modul tidak ada

    # 2. Panggil model dari modul lain menggunakan self.env
    Notification = self.env['unitrade.notification'].sudo()
    for ticket in self.sudo():
        Notification.emit(
            user_id=ticket.user_id.id,
            event_code=event_code,
            payload={
                'reference_model': ticket._name,  # 'unitrade.customer.ticket'
                'reference_id': ticket.id,
                'action_url': ticket._customer_ticket_url(),
            },
            channels=['in_app'],
        )
```

**Penjelasan:**
- `self.env['nama.model']` = cara mengakses model dari modul manapun di Odoo
- `'unitrade.notification' not in self.env.registry` = cara aman mengecek apakah modul lain terinstall
- Pattern ini membuat modul-modul bisa berinteraksi **tanpa hardcode dependency** satu sama lain

---

## Tabel Semua Route URL → Controller → Model

| URL | Metode | Controller | Model yang Dipanggil |
|-----|--------|-----------|---------------------|
| `/` (homepage) | GET | `Website` (Odoo core) | `product.template` via `unitrade_product_ext` |
| `/web/signup` | POST | `UnitradeAuthSignup.web_auth_signup` | `res.users`, `unitrade.otp` |
| `/web/login` | POST | `UnitradeAuthSignup.web_login` | `res.users`, `unitrade.security.activity` |
| `/web/verify-otp` | POST | `UnitradeOTPController` | `unitrade.otp` |
| `/seller-verification` | POST | `SellerVerificationController` | `unitrade.seller.verification` + Google Vision |
| `/shop` | GET | Odoo `WebsiteSale` | `product.template` via `unitrade_product_ext` |
| `/unitrade/product/stock/validate` | JSON | `UnitradeCartController` | `product.product` |
| `/unitrade/wishlist/toggle` | JSON | `UnitradeWishlistController` | `unitrade.wishlist` |
| `/unitrade/checkout/shipping/select` | JSON | `UnitradeCheckoutController` | `sale.order` |
| `/unitrade/payment/midtrans/webhook` | POST | `UnitradePaymentController` | `unitrade.payment.intent`, `sale.order` |
| `/my/notifications/unread_count` | JSON | `UnitradeNotificationController` | `unitrade.notification` |
| `/customer-service/chat/send` | JSON | `UnitradeCsPortal` | `unitrade.cs.ai.service` → Gemini API |
| `/unitrade/mapbox/geocode` | JSON | `UnitradeProfileController` | — (proxy ke Mapbox API) |
| `/unitrade/admin` | GET | `UnitradeAdminController` | `unitrade.admin.stats` |
