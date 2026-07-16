# 07 — Integrasi Frontend & Backend (Detail)

## Arsitektur Frontend-Backend di Odoo 17

UniTrade menggunakan **dua pendekatan** untuk komunikasi frontend-backend:

```
Pendekatan A: Sinkronous (Server-Side Rendering)
  Browser → HTTP GET/POST → Controller Python → QWeb XML → HTML ke Browser
  Digunakan: navigasi halaman, submit form

Pendekatan B: Asinkronous (AJAX JSON-RPC)
  Browser JavaScript → fetch/jsonrpc → Controller Python (type='json') → JSON → JS
  Digunakan: validasi stok, wishlist toggle, notifikasi, AI chat
```

---

## A. Pendekatan Sinkronous (Server-Side Rendering)

### Cara Kerja

```
1. Browser kirim GET/POST request ke URL
2. Odoo HTTP server menerima request
3. Controller Python memanggil Models untuk data
4. Models query PostgreSQL
5. Data di-render ke template QWeb XML
6. HTML lengkap dikembalikan ke browser
```

### Contoh: Halaman Wishlist

**1. Template QWeb (HTML)**
```xml
<!-- unitrade_wishlist/views/wishlist_templates.xml -->
<template id="wishlist_page_template" name="Wishlist Page">
    <t t-call="website.layout">  <!-- Memanggil layout bawaan Odoo -->
        <div class="tw-max-w-7xl tw-mx-auto tw-px-4 tw-py-8">
            <h1 class="tw-text-2xl tw-font-bold">Wishlist Saya</h1>
            <!-- t-foreach = loop di QWeb, seperti for loop Python -->
            <t t-foreach="wishlist_items" t-as="item">
                <div class="tw-border tw-rounded-lg tw-p-4">
                    <!-- t-esc = render nilai dengan escape (aman dari XSS) -->
                    <p><t t-esc="item.product_id.name"/></p>
                    <!-- t-att-src = render attribute HTML secara dinamis -->
                    <img t-att-src="'/web/image/product.template/%s/image_128' % item.product_id.product_tmpl_id.id"/>
                </div>
            </t>
        </div>
    </t>
</template>
```

**2. Controller Python (Pengiriman Data ke Template)**
```python
# unitrade_wishlist/controllers/main.py: L15-26
@http.route('/my/wishlist', type='http', auth='user', website=True)
def wishlist_page(self, **kwargs):
    # Ambil data dari database menggunakan ORM
    items = request.env['unitrade.wishlist'].sudo().search([
        ('user_id', '=', request.env.uid),
    ])
    # Kirim data ke template XML sebagai dictionary (context variables)
    values = {
        'wishlist_items': items,       # Bisa di-akses via t-foreach di QWeb
        'wishlist_count': len(items),  # Bisa di-akses via t-esc di QWeb
    }
    # render() = Odoo mencari template XML berdasarkan ID dan mengisi data
    return request.render('unitrade_wishlist.wishlist_page_template', values)
```

**Penjelasan alur:**
1. User buka `/my/wishlist`
2. Odoo cocokkan URL dengan dekorator `@http.route('/my/wishlist', ...)`
3. Fungsi `wishlist_page()` dijalankan
4. `request.env['unitrade.wishlist'].search(...)` → `SELECT * FROM unitrade_wishlist WHERE user_id = ?`
5. Data dimasukkan ke `values` dict
6. `request.render(...)` → Odoo render template XML dengan data tersebut
7. HTML yang sudah terisi data dikirim ke browser

---

## B. Pendekatan Asinkronous (AJAX JSON-RPC)

### Struktur JSON-RPC 2.0

Semua request AJAX ke Odoo harus menggunakan format JSON-RPC 2.0:

```json
// Request dari Browser ke Server
{
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
        "product_id": 42,
        "add_qty": 1
    }
}

// Response dari Server ke Browser
{
    "jsonrpc": "2.0",
    "id": null,
    "result": {
        "valid": true,
        "stock": 15,
        "message": ""
    }
}
```

### Cara A: `jsonrpc()` — Odoo Modern Module (ES6)

Digunakan di file JS yang menggunakan sistem modul Odoo (`/** @odoo-module **/`):

```javascript
// unitrade_theme/static/src/js/product_detail.js: L1-4
/** @odoo-module **/

// Import fungsi jsonrpc dari library bawaan Odoo
// Ini secara otomatis menambahkan jsonrpc header dan menangani error
import { jsonrpc } from '@web/core/network/rpc_service';

// Cara penggunaan: jsonrpc(url, params)
// Tidak perlu set header manual, Odoo menanganinya
const result = await jsonrpc('/unitrade/product/stock/validate', {
    product_id: 42,   // Dikirim ke controller sebagai kwargs
    add_qty: 1,
    include_cart: false,
});

// result langsung berisi nilai yang di-return oleh Python controller
if (result.valid === false) {
    showWarning(result.message);
}
```

### Cara B: Native `fetch()` — Vanilla JavaScript

Digunakan di file JS yang tidak menggunakan sistem modul Odoo:

```javascript
// unitrade_notification/static/src/js/notification_service.js: L36-62

async function _jsonPost(url, params = {}) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',  // Header wajib untuk Odoo
        },
        // Harus bungkus params dalam struktur JSON-RPC 2.0
        body: JSON.stringify({
            jsonrpc: '2.0',
            method: 'call',
            params: params,        // Data yang dikirim ke controller
        }),
        credentials: 'same-origin',  // Kirim cookie sesi Odoo
    });

    const data = await response.json();

    // Odoo membungkus response di dalam { result: ... } atau { error: ... }
    if (data && data.error) {
        throw new Error(data.error.data.message || 'RPC error');
    }
    return data ? data.result : undefined;  // Unwrap dari { result: value }
}
```

### Cara C: Public Widget — Menghubungkan JS ke Elemen HTML

`publicWidget` adalah sistem Odoo untuk menghubungkan JavaScript dengan elemen HTML di halaman secara otomatis:

```javascript
// unitrade_theme/static/src/js/product_detail.js: L6-30
publicWidget.registry.UnitradeProductDetail = publicWidget.Widget.extend({
    // selector = CSS selector untuk elemen HTML yang akan "di-attach" widget ini
    // Widget ini aktif HANYA pada halaman yang memiliki element #product_detail
    selector: '#product_detail.ut-product-detail-hydrating',

    // events = mapping event HTML ke method di class ini
    // Format: 'eventType CSS-selector': 'methodName'
    events: {
        'click #add_to_cart': '_onAddToCartClick',
        'change input[name="add_qty"]': '_onQtyChange',
        'click .unitrade-wishlist-btn': '_onWishlistClick',
    },

    // start() = lifecycle method, dipanggil saat widget pertama kali di-attach
    start() {
        this._hasAttemptedSubmit = false;
        return this._super(...arguments);
    },

    // Handler untuk event klik tombol "Tambah ke Keranjang"
    async _onAddToCartClick(ev) {
        ev.preventDefault();
        const form = this.el.closest('form');
        const result = await jsonrpc('/unitrade/product/stock/validate', {
            product_id: Number(form.querySelector("input[name='product_id']").value),
            add_qty: form.querySelector("input[name='add_qty']").value,
        });
        if (result && result.valid === false) {
            this._showWarning(result.message);
            return;
        }
        form.submit(); // Submit form secara normal ke Odoo
    },
});
```

**Penjelasan:** Odoo secara otomatis melakukan "scan" ke seluruh elemen DOM setelah halaman dimuat. Jika menemukan elemen yang cocok dengan `selector: '#product_detail'`, widget langsung di-inisialisasi dan semua event listener terpasang.

---

## C. Contoh Alur Lengkap: Notifikasi Bell (Polling)

Ini adalah contoh interaksi frontend-backend yang cukup kompleks — notification bell yang melakukan polling setiap 60 detik.

### 1. JavaScript Service (`notification_service.js`)
```javascript
// Konstanta polling interval (60 detik sesuai requirement)
const DEFAULT_POLL_INTERVAL_MS = 60000;

export const notificationService = {
    // Fetch jumlah notifikasi belum dibaca
    async fetchUnreadCount() {
        const res = await _jsonPost('/my/notifications/unread_count');
        return res && typeof res.count === 'number' ? res.count : 0;
    },

    // Fetch 5 notifikasi terbaru untuk dropdown
    async fetchRecent() {
        const res = await _jsonPost('/my/notifications/recent');
        return Array.isArray(res) ? res : [];
    },

    // Tandai notifikasi sebagai sudah dibaca
    async markRead(id) {
        return await _jsonPost(`/my/notifications/${id}/read`);
    },

    // Mulai polling otomatis setiap 60 detik
    startPolling(callback, intervalMs = DEFAULT_POLL_INTERVAL_MS) {
        this.stopPolling();
        _pollHandle = window.setInterval(() => {
            if (_pollInFlight) return; // Skip jika request sebelumnya belum selesai
            _pollInFlight = Promise.resolve(callback())
                .finally(() => { _pollInFlight = null; });
        }, intervalMs);
        return _pollHandle;
    },
};
```

### 2. Python Controller (Menerima Request dari JS)
```python
# unitrade_notification/controllers/main.py: L368-393
@http.route('/my/notifications/unread_count', type='json', auth='user')
def unread_count(self, **kwargs):
    """
    Endpoint yang dipanggil oleh notificationService.fetchUnreadCount()
    setiap 60 detik dari browser.
    """
    user = request.env.user

    # Cek jika user adalah public user (belum login)
    if user._is_public():
        return {'count': 0}

    # Query ke database untuk hitung notifikasi belum dibaca
    # Record rule ir.rule otomatis memfilter hanya notifikasi milik user ini
    count = request.env['unitrade.notification'].sudo().search_count([
        ('user_id', '=', user.id),
        ('is_read', '=', False),
    ])

    return {'count': count}  # Dikembalikan ke JS sebagai result
```

### 3. Alur Lengkap (Sequence)
```
[Browser dimuat] → Odoo menginisialisasi publicWidget
    → startPolling() dipanggil → setInterval(60000ms)
    → Setiap 60 detik:
        JS: fetchUnreadCount()
            → _jsonPost('/my/notifications/unread_count', {})
            → fetch('/my/notifications/unread_count', {method: POST, body: JSON-RPC})
        Python: unread_count()
            → query PostgreSQL: SELECT COUNT(*) FROM unitrade_notification WHERE user_id=? AND is_read=False
            → return {'count': 3}
        JS: response.result = {'count': 3}
            → Update badge di bell icon: innerHTML = '3'
```

---

## D. Integrasi Form HTML → Controller (Submit Sinkronous)

### Contoh: Form Signup

```html
<!-- views/login_templates.xml (QWeb) -->
<!-- QWeb merender form ini sebagai HTML biasa -->
<form action="/web/signup" method="POST" class="tw-space-y-4">
    <!-- t-att-value = render value dari variabel Python ke attribute HTML -->
    <input type="hidden" name="csrf_token" t-att-value="request.csrf_token()"/>
    <input type="email" name="login" placeholder="Email Anda" required/>
    <input type="password" name="password" required/>
    <input type="checkbox" name="terms_accepted" value="1" required/>
    <button type="submit">Daftar</button>
</form>
```

```python
# unitrade_theme/controllers/controllers.py: L119-170
@http.route('/web/signup', type='http', auth='public', website=True)
def web_auth_signup(self, *args, **kw):
    """Menangani POST dari form signup HTML di atas."""
    qcontext = self.get_auth_signup_qcontext()  # Ambil data dari form

    if request.httprequest.method == 'POST':
        login_value = _normalize_login(qcontext.get('login'))

        # Validasi 1: Email harus valid
        if not _is_email(login_value):
            raise UserError("Masukkan email yang valid.")

        # Validasi 2: Email tidak di-blacklist
        if _is_unitrade_contact_blacklisted(email=login_value):
            raise UserError("Email ini tidak dapat digunakan.")

        # Validasi 3: Terms harus disetujui
        if request.params.get('terms_accepted') != '1':
            raise UserError("Anda harus menyetujui Syarat Ketentuan.")

        # Validasi 4: Google reCaptcha
        if not request.env['ir.http']._verify_request_recaptcha_token('signup'):
            raise UserError("Suspicious activity detected.")

        # Buat akun user via Odoo standard signup
        self.do_signup(qcontext)

        # Setelah signup: generate OTP dan redirect ke halaman verifikasi
        user_sudo = request.env['res.users'].sudo().search(
            [('login', '=', login_value)], limit=1
        )
        if user_sudo:
            # Simpan OTP ke session, kirim email
            return self._generate_and_redirect_otp(user_sudo, login_value)
```

---

## E. Data Binding QWeb (Template to Python)

QWeb menggunakan beberapa direktif khusus untuk binding data dari Python ke HTML:

| Direktif QWeb | Kegunaan | Contoh |
|---------------|----------|--------|
| `t-esc` | Render teks (aman dari XSS) | `<t t-esc="product.name"/>` |
| `t-raw` | Render HTML (HATI-HATI XSS) | `<t t-raw="description_html"/>` |
| `t-if` | Kondisional | `<div t-if="is_seller">` |
| `t-foreach` | Loop | `<t t-foreach="items" t-as="item">` |
| `t-att-src` | Attribute dinamis | `<img t-att-src="'/web/image/%s' % id"/>` |
| `t-call` | Include template lain | `<t t-call="website.layout"/>` |
| `t-set` | Set variabel lokal | `<t t-set="title" t-value="'Hello'"/>` |

```xml
<!-- Contoh penggunaan dalam product_templates.xml -->
<template id="product_detail_page">
    <!-- t-if: tampilkan hanya jika user adalah penjual produk ini -->
    <div t-if="env.user == product.seller_id.user_id" class="seller-actions">
        <a t-att-href="'/unitrade/seller/products/edit/%s' % product.id">
            Edit Produk
        </a>
    </div>

    <!-- t-foreach: loop semua gambar produk -->
    <t t-foreach="product.product_template_image_ids" t-as="img">
        <img t-att-src="'/web/image/product.template/%s/image_128' % product.id"
             class="tw-w-full tw-h-48 tw-object-cover"/>
    </t>
</template>
```
