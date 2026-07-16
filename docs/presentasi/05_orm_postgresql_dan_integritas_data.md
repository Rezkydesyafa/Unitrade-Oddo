# 05 — ORM ke PostgreSQL & Integritas Data

## Cara Odoo ORM Mengabstraksi PostgreSQL

Odoo ORM adalah lapisan yang **menerjemahkan kode Python** ke SQL secara otomatis. Developer tidak perlu menulis SQL untuk operasi CRUD standar.

```
Python Model Class  ────────────────►  Tabel PostgreSQL
───────────────────                    ──────────────────
class UnitradeSeller(models.Model):    CREATE TABLE unitrade_seller (
    _name = 'unitrade.seller'              id SERIAL PRIMARY KEY,
    name = fields.Char()         ──►       name VARCHAR,
    nim = fields.Char(index=True)──►       nim VARCHAR,
    user_id = Many2one('res.users')──►     user_id INT REFERENCES res_users(id),
    status = fields.Selection(...)──►      status VARCHAR,
    is_verified = fields.Boolean()──►      is_verified BOOLEAN,
    create_date = fields.Datetime()──►     create_date TIMESTAMPTZ
)                                      );
```

> 💡 **Penjelasan:** Diagram ini menunjukkan hubungan langsung antara definisi Python di kode dan tabel yang dibuat di PostgreSQL. Setiap `fields.Char()` menjadi kolom `VARCHAR`, `fields.Boolean()` menjadi `BOOLEAN`, dan `fields.Many2one()` menjadi kolom `INTEGER` dengan foreign key constraint. Odoo secara otomatis menambahkan kolom `id SERIAL PRIMARY KEY` (auto-increment) ke setiap model. Developer cukup mendefinisikan tipe field di Python — Odoo mengurus pembuatan tabel, kolom, index, dan foreign key di PostgreSQL tanpa perlu menulis SQL DDL sama sekali.

---

## A. Operasi CRUD via ORM (Lengkap)

### 1. CREATE — Membuat Data Baru

```python
# unitrade_payment/models/sale_order.py: L1081-1099
# Membuat payment intent baru
intent = self.env['unitrade.payment.intent'].sudo().create({
    'name': order_id,                      # Nama / kode unik
    'provider': 'midtrans',                # String sederhana
    'state': 'draft',                      # Selection field
    'amount': total_amount,                # Float
    'currency_id': self.currency_id.id,   # Many2one → foreign key INTEGER
    'sale_order_id': self.id,             # Many2one → foreign key INTEGER
    'partner_id': self.partner_id.id,     # Many2one → foreign key INTEGER
    'midtrans_order_id': order_id,
    'expires_at': expires_at,             # Datetime
})

# SQL yang di-generate Odoo:
# INSERT INTO unitrade_payment_intent
#   (name, provider, state, amount, currency_id, sale_order_id, ...)
# VALUES
#   ('UT-2026-001', 'midtrans', 'draft', 50000, 12, 88, ...)
# RETURNING id;
```

> 💡 **Penjelasan:** Method `create()` di Odoo menerima sebuah dictionary Python dan mengonversinya menjadi perintah `INSERT INTO` SQL. Perhatikan field Many2one seperti `currency_id` dan `sale_order_id` — nilai yang diisi adalah `.id` (integer), bukan objek record-nya. Di database, kolom ini menyimpan integer foreign key biasa. Odoo juga menambahkan `RETURNING id` agar ID yang baru dibuat langsung dikembalikan — hasilnya disimpan dalam variabel `intent` sebagai Odoo recordset yang bisa langsung dipakai. Setelah `create()`, Odoo otomatis memanggil constraint check (`@api.constrains`) jika ada, memastikan data yang baru dibuat valid.

---

### 2. READ — Mencari Data

```python
# Contoh A: Search dengan domain filter
orders = self.env['sale.order'].sudo().search([
    ('x_payment_status', '=', 'paid'),          # WHERE x_payment_status = 'paid'
    ('state', 'in', ('sale', 'done')),           # AND state IN ('sale', 'done')
], order='id asc', limit=100)
# SQL: SELECT * FROM sale_order WHERE x_payment_status='paid' AND state IN ('sale','done')
#      ORDER BY id ASC LIMIT 100

# Contoh B: Search dengan Many2one filter
seller_products = self.env['product.template'].sudo().search([
    ('x_seller_id', '=', seller_id),  # WHERE x_seller_id = ?
    ('active', '=', True),
    ('website_published', '=', True),
])
# SQL: SELECT * FROM product_template WHERE x_seller_id=42 AND active=True AND website_published=True

# Contoh C: search_count untuk hitung tanpa ambil data
unread_count = self.env['unitrade.notification'].sudo().search_count([
    ('user_id', '=', request.env.uid),
    ('is_read', '=', False),
])
# SQL: SELECT COUNT(*) FROM unitrade_notification WHERE user_id=5 AND is_read=False
```

> 💡 **Penjelasan:** `search()` di Odoo menggunakan "domain" — list of tuples dengan format `(field_name, operator, value)`. Domain ini diterjemahkan menjadi klausa `WHERE` di SQL. Operator yang tersedia antara lain `=`, `!=`, `in`, `not in`, `like`, `ilike` (case-insensitive like), `>`, `<`, `>=`, `<=`. Parameter `order` menjadi `ORDER BY`, dan `limit` menjadi `LIMIT` di SQL. Penting: `search()` mengembalikan **recordset** (koleksi record), bukan list biasa — ini memungkinkan chaining operation seperti `orders.filtered(lambda o: o.amount > 100000)`. Untuk keperluan hitungan saja, gunakan `search_count()` agar lebih efisien karena Odoo hanya menjalankan `SELECT COUNT(*)` tanpa mengambil semua data kolom.

---

### 3. UPDATE — Mengubah Data

```python
# Contoh A: Update satu record
order.write({
    'x_payment_status': 'paid',
    'x_unitrade_order_state': 'paid_escrow',
    'x_midtrans_transaction_id': payload.get('transaction_id'),
    'x_paid_at': fields.Datetime.now(),
})
# SQL: UPDATE sale_order SET x_payment_status='paid', x_unitrade_order_state='paid_escrow',
#      x_midtrans_transaction_id='...' WHERE id = ?

# Contoh B: Update banyak record sekaligus
ledgers.write({'state': 'released', 'released_at': fields.Datetime.now()})
# SQL: UPDATE unitrade_escrow_ledger SET state='released', released_at=NOW()
#      WHERE id IN (1, 2, 3, 4, 5)  ← semua ID dari recordset 'ledgers'

# Contoh C: sudo().write() untuk bypass security sementara
intent.sudo().write({'state': status, 'raw_response': json.dumps(payload)})
```

> 💡 **Penjelasan:** Method `write()` menerima dictionary field yang ingin diubah dan menghasilkan perintah `UPDATE` SQL. Keunggulan ORM: jika `ledgers` adalah recordset yang berisi 10 record, Odoo cukup menjalankan satu `UPDATE ... WHERE id IN (...)` — bukan 10 UPDATE terpisah. Ini jauh lebih efisien. Odoo juga otomatis menjalankan `@api.onchange` dan `@api.constrains` setelah `write()` — jika ada constraint yang dilanggar, perubahan dibatalkan dan exception dilempar. Field dengan `tracking=True` akan dicatat perubahannya di "chatter" (log perubahan field) secara otomatis, berguna untuk audit trail tanpa perlu kode tambahan.

---

### 4. DELETE — Menghapus Data

```python
# Contoh A: Hapus berdasarkan search
stale_intents = self.env['unitrade.payment.intent'].sudo().search([
    ('sale_order_id', '=', self.id),
    ('state', '=', 'draft'),
    ('create_date', '<', fields.Datetime.now() - timedelta(hours=1)),
])
stale_intents.unlink()
# SQL: DELETE FROM unitrade_payment_intent WHERE id IN (...)

# Contoh B: Hapus satu record
item.unlink()
# SQL: DELETE FROM unitrade_wishlist WHERE id = ?
```

> 💡 **Penjelasan:** `unlink()` adalah method untuk menghapus record dari database. Sebelum menghapus, Odoo otomatis memeriksa constraint `ondelete` dari field Many2one yang merujuk ke record ini. Jika ada record lain yang punya `ondelete='restrict'` ke record yang akan dihapus, Odoo akan melempar error dan mencegah penghapusan. Jika `ondelete='cascade'`, record turunannya ikut dihapus. Contoh di atas menghapus payment intent yang sudah lebih dari 1 jam dalam status draft — ini adalah proses pembersihan (garbage collection) untuk data yang tidak terpakai, menjaga tabel tetap bersih dan query tetap cepat.

---

## B. Relasi Antar Tabel (Field Relasi ORM)

### Many2one (N ke 1) — Foreign Key

```python
# Banyak order → satu user
class SaleOrder(models.Model):
    partner_id = fields.Many2one(
        'res.partner',          # Model yang direferensikan
        string='Customer',
        required=True,
        ondelete='restrict',    # Jika partner dihapus: error (tidak boleh hapus)
        index=True,             # Buat INDEX di PostgreSQL untuk performa
    )
# PostgreSQL: partner_id INTEGER REFERENCES res_partner(id)
# Cara akses: order.partner_id.name → SELECT name FROM res_partner WHERE id = ?
```

> 💡 **Penjelasan:** `Many2one` adalah tipe relasi paling umum di Odoo, setara dengan foreign key di SQL. `ondelete='restrict'` berarti jika seseorang mencoba menghapus `res.partner` yang masih dirujuk oleh order, PostgreSQL akan melempar error — ini menjaga integritas referensial data. `index=True` membuat Odoo menambahkan `CREATE INDEX` di kolom ini, yang sangat penting untuk performa karena kolom foreign key sering digunakan dalam query JOIN dan filter (`WHERE partner_id = ?`). Cara akses `order.partner_id.name` di Python secara internal melakukan query SQL terpisah (lazy loading) — jika banyak record perlu diakses, gunakan `prefetch_fields` untuk optimasi.

---

### One2many (1 ke N) — Virtual Relasi

```python
# Satu tiket CS → banyak pesan
class UnitradeCustomerTicket(models.Model):
    message_ids = fields.One2many(
        'unitrade.customer.ticket.message',  # Model anak
        'ticket_id',                          # Field Many2one di model anak
        string='Thread Bantuan',
        readonly=True,
    )
# Tidak ada kolom di tabel ini, Odoo join ke tabel anak
# Cara akses: ticket.message_ids → SELECT * FROM unitrade_customer_ticket_message WHERE ticket_id = ?
```

> 💡 **Penjelasan:** `One2many` disebut "virtual" karena tidak ada kolom fisik di tabel `unitrade_customer_ticket`. Relasinya terdefinisi di sisi lain — tabel `unitrade_customer_ticket_message` yang punya kolom `ticket_id` (Many2one ke tiket). Odoo hanya "membaca" relasi ini dari arah sebaliknya. Ketika kita mengakses `ticket.message_ids`, Odoo menjalankan `SELECT * FROM ... WHERE ticket_id = ?`. Ini pola yang sangat umum untuk relasi parent-child: satu tiket punya banyak pesan, satu order punya banyak order line, satu seller punya banyak produk, dll.

---

### Many2many (N ke N) — Junction Table

```python
# Satu user → banyak group, satu group → banyak user
class ResGroups(models.Model):
    users = fields.Many2many(
        'res.users',         # Model kedua
        'res_groups_users_rel',  # Nama junction table
        'gid',               # Kolom FK ke tabel ini
        'uid',               # Kolom FK ke res_users
    )
# PostgreSQL:
# CREATE TABLE res_groups_users_rel (gid INTEGER, uid INTEGER, PRIMARY KEY (gid, uid))
```

> 💡 **Penjelasan:** `Many2many` digunakan ketika dua entitas saling terhubung banyak ke banyak. Di SQL, ini memerlukan "junction table" (tabel perantara) yang menyimpan pasangan ID. Odoo membuat junction table ini secara otomatis. Dalam konteks security UniTrade: setiap user bisa punya banyak group (role), dan setiap group bisa punya banyak user — inilah yang membuat sistem role Odoo fleksibel. Saat admin menambahkan user ke group Seller, Odoo menyisipkan baris baru ke `res_groups_users_rel`. Saat dicek dengan `user.has_group(...)`, Odoo melakukan JOIN ke junction table ini.

---

## C. Integritas Data: Sistem Escrow (Detail)

### Model Escrow Ledger

```python
# unitrade_payment/models/escrow_ledger.py (ringkasan)
class UnitradeEscrowLedger(models.Model):
    _name = 'unitrade.escrow.ledger'
    _description = 'UniTrade Escrow Ledger'

    order_id = fields.Many2one('sale.order', required=True, index=True, ondelete='restrict')
    seller_id = fields.Many2one('unitrade.seller', required=True, index=True)
    amount = fields.Monetary(required=True)  # Jumlah dana yang ditahan
    state = fields.Selection([
        ('held', 'Ditahan'),
        ('releasable', 'Siap Rilis'),
        ('released', 'Dirilis'),
        ('disputed', 'Disengketakan'),
        ('refunded', 'Direfund'),
    ], default='held', required=True, index=True, tracking=True)

    # Timestamps untuk audit trail
    seller_confirmed_at = fields.Datetime(string='Penjual Konfirmasi Kirim', readonly=True)
    buyer_confirmed_at = fields.Datetime(string='Pembeli Konfirmasi Terima', readonly=True)
    released_at = fields.Datetime(string='Dirilis Pada', readonly=True)

    def _sync_order_escrow_state(self):
        """Sinkronkan status escrow di tabel sale_order berdasarkan ledger ini."""
        for ledger in self:
            order = ledger.order_id.sudo()
            if ledger.state == 'released':
                order.write({'x_escrow_state': 'released'})
            elif ledger.state == 'disputed':
                order.write({'x_escrow_state': 'disputed'})
            elif ledger.state == 'refunded':
                order.write({'x_escrow_state': 'refunded'})
```

> 💡 **Penjelasan:** Model `unitrade.escrow.ledger` adalah "buku kas" sistem escrow UniTrade. Setiap baris mewakili satu transaksi dana yang sedang ditahan. Field `tracking=True` pada `state` berarti Odoo otomatis mencatat setiap perubahan status ke chatter — ini penting untuk audit: kita bisa melihat kapan tepatnya dana berpindah dari 'held' ke 'released'. `ondelete='restrict'` pada `order_id` memastikan order yang masih punya escrow ledger aktif tidak bisa dihapus. Timestamps `seller_confirmed_at`, `buyer_confirmed_at`, dan `released_at` mencatat waktu pasti setiap tahap — bukti yang bisa digunakan jika ada sengketa dikemudian hari.

---

### State Machine Escrow

```
                  Webhook Midtrans 'paid'
[Order Dibuat] ─────────────────────────► [HELD]
                                              │
                              Pembeli konfirmasi terima barang
                                              │
                                              ▼
                                       [RELEASABLE]
                                              │
                           Cron job harian (atau manual admin)
                                              │
                                              ▼
                                        [RELEASED] ─── Dana ke saldo penjual
                              ┌────────────── │ (jika ada dispute sebelum released)
                              ▼               │
                          [DISPUTED] ─────────┘
                              │
                    Admin putuskan: refund/release
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
               [REFUNDED]         [RELEASED]
             Dana ke pembeli    Dana ke penjual
```

> 💡 **Penjelasan:** State machine ini mendefinisikan siklus hidup dana escrow. Tidak ada lompatan status yang tidak sah — misalnya, tidak mungkin langsung dari HELD ke REFUNDED tanpa melalui DISPUTED terlebih dahulu. Ini dijamin oleh kode Python yang hanya mengizinkan transisi tertentu. Status RELEASABLE berarti "pembeli sudah konfirmasi terima barang, dana aman untuk dirilis ke penjual" — tapi rilis sebenarnya menunggu cron job harian atau approval manual admin. Jeda ini memberi jendela waktu untuk pembeli melaporkan masalah setelah konfirmasi jika ternyata barang bermasalah.

---

## D. Validasi Data via `@api.constrains`

Odoo memungkinkan validasi data **sebelum data disimpan ke database**:

```python
# unitrade_theme/models/customer_service.py: L106-122
@api.constrains('partner_id', 'order_id')
def _check_order_owner(self):
    """
    Validasi: Pembeli hanya boleh buat tiket untuk pesanan MILIKNYA sendiri.
    Ini mencegah user A membuat tiket untuk pesanan user B.
    """
    for ticket in self:
        if not ticket.order_id or not ticket.partner_id:
            continue
        buyer_commercial = ticket.partner_id.commercial_partner_id
        order_commercial = ticket.order_id.partner_id.commercial_partner_id
        if buyer_commercial != order_commercial:
            _logger.warning(
                'Blocked customer ticket %s with non-owned order %s for partner %s',
                ticket.name, ticket.order_id.name, ticket.partner_id.id,
            )
            raise ValidationError(
                'Nomor pesanan tidak ditemukan atau bukan milik akun Anda.'
            )

# Validasi ini dijalankan OTOMATIS setiap kali create() atau write() dipanggil
# Jika gagal: ValidationError dilempar, transaksi di-rollback, data tidak tersimpan
```

> 💡 **Penjelasan:** `@api.constrains` adalah decorator Odoo untuk mendefinisikan validasi bisnis tingkat model. Berbeda dari validasi di controller (yang hanya melindungi satu endpoint), constraint ini melindungi **setiap cara** data bisa diubah — baik via controller web, API JSON-RPC, import CSV, maupun bahkan perintah Python langsung di shell Odoo. Ini memastikan aturan bisnis "user hanya boleh buka tiket untuk pesanannya sendiri" tidak bisa dilewati dengan cara apapun. Ketika `ValidationError` dilempar, Odoo otomatis melakukan rollback seluruh transaksi database — data yang sudah sebagian tersimpan akan dibatalkan, menjaga konsistensi data.

---

## E. Unique Constraint via Raw SQL

```python
# unitrade_seller/models/seller.py: L306-324
def init(self):
    """
    Dijalankan saat modul di-install atau di-upgrade.
    Membuat constraint dan index unik di PostgreSQL langsung.
    """
    super().init()

    # Hapus constraint lama jika ada (aman untuk upgrade)
    self.env.cr.execute(
        "ALTER TABLE unitrade_seller DROP CONSTRAINT IF EXISTS unitrade_seller_nim_unique"
    )

    # Buat index unik: satu NIM hanya boleh satu seller AKTIF
    self.env.cr.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS unitrade_seller_nim_unique
        ON unitrade_seller (nim)
        WHERE nim IS NOT NULL AND active = true
    """)
    # "WHERE nim IS NOT NULL AND active = true" = Partial Index
    # Seller yang sudah di-soft-delete (active=false) boleh punya NIM yang sama
    # tapi dua seller aktif tidak boleh punya NIM yang sama

    # Index untuk query pencarian berdasarkan user_id
    self.env.cr.execute("""
        CREATE INDEX IF NOT EXISTS unitrade_seller_user_id_idx
        ON unitrade_seller (user_id)
    """)
```

> 💡 **Penjelasan:** Odoo ORM memang bisa membuat unique constraint via `_sql_constraints`, tapi untuk kasus kompleks seperti **Partial Index**, kita perlu turun ke raw SQL. Partial index `WHERE nim IS NOT NULL AND active = true` adalah fitur PostgreSQL yang memungkinkan constraint unik hanya berlaku untuk subset data — dalam hal ini, hanya untuk seller yang aktif. Mengapa perlu? Karena skenario "seller dihapus (soft-delete) lalu mahasiswa yang sama mendaftar ulang sebagai seller baru" harus tetap diizinkan — NIM yang sama boleh muncul dua kali asalkan hanya satu yang `active = true`. Tanpa partial index, kita tidak bisa membuat constraint yang cukup fleksibel ini. `DROP CONSTRAINT IF EXISTS` sebelum CREATE memastikan upgrade modul tidak error meskipun constraint sudah ada.

---

## F. Transaksi Database & Savepoint

```python
# unitrade_payment/models/sale_order.py: L222-248
@api.model
def _unitrade_backfill_missing_escrow_ledgers(self, limit=None):
    """
    Backfill escrow ledger untuk order lama yang belum punya ledger.
    Setiap order diproses dalam savepoint terpisah.
    """
    orders = self.sudo().search([
        ('x_payment_status', '=', 'paid'),
        ('state', 'in', ('sale', 'done')),
    ], limit=limit)

    repaired = 0
    for order in orders:
        try:
            # SAVEPOINT per order: jika gagal, rollback hanya order ini
            # Order lain yang sudah selesai tidak ikut di-rollback
            with self.env.cr.savepoint():
                intent = order._unitrade_repair_payment_intent()
                ledgers = Ledger._create_for_order(order, intent)

                if order.x_unitrade_order_state == 'completed' and ledgers:
                    ledgers.write({'state': 'releasable'})

                if ledgers:
                    ledgers._sync_order_escrow_state()
                    repaired += len(ledgers)

        except Exception:
            # Error pada satu order tidak menghentikan pemrosesan order lain
            _logger.exception(
                'Failed to backfill escrow ledger for order %s', order.name
            )
            # Savepoint di-rollback otomatis untuk order ini, lanjut ke order berikutnya

    if repaired:
        _logger.info('Backfilled %s missing escrow ledger(s).', repaired)
```

> 💡 **Penjelasan:** Savepoint adalah "checkpoint" di dalam sebuah transaksi database. Analoginya adalah fitur quicksave di video game — jika karakter mati setelah checkpoint, pemain kembali ke checkpoint, bukan ke awal permainan. Tanpa savepoint, jika satu order dari 100 order gagal diproses, seluruh batch 100 order akan di-rollback dan tidak ada yang berhasil. Dengan `with self.env.cr.savepoint()`, jika order ke-47 gagal, hanya perubahan untuk order ke-47 yang dibatalkan — order 1 sampai 46 yang sudah berhasil tetap tersimpan. Pola ini sangat berguna untuk operasi batch yang memproses banyak record sekaligus, memastikan kegagalan parsial tidak menghapus progress yang sudah dicapai.

---

## G. Contoh Pengujian Integritas Data

### Test 1: Amount Mismatch Detection

```python
# unitrade_payment/controllers/main.py: L1490-1496
# Jika jumlah yang di-report Midtrans berbeda dengan yang ada di database
payload_amount = self._midtrans_payload_amount(payload)
if payload_amount and payload_amount != int(round(intent.amount)):
    event.write({
        'state': 'failed',
        'error_message': 'Amount mismatch: webhook=%s intent=%s' % (
            payload_amount, int(round(intent.amount))
        ),
    })
    return self._json_response({'status': 'error', 'message': 'amount mismatch'}, status=400)
```

> 💡 **Penjelasan:** Pengecekan ini melindungi dari serangan manipulasi jumlah pembayaran. Skenario serangan: penyerang mengirimkan POST webhook palsu dengan amount yang sudah divalidasi signature-nya (misalnya menggunakan sandbox key) tapi dengan jumlah yang berbeda dari yang seharusnya. Dengan membandingkan `payload_amount` (jumlah dari webhook) dengan `intent.amount` (jumlah yang tersimpan di database saat checkout), kita memastikan tidak ada manipulasi jumlah. Jika berbeda, event dicatat sebagai `failed` dan order tidak diupdate — transaksi ditolak dengan HTTP 400.

**Pengujian:**
- Kirim webhook dengan `gross_amount: "55000"` padahal intent amount adalah `50000`
- Expected: HTTP 400 error, event dicatat sebagai `failed`, order tidak berubah

---

### Test 2: Unique NIM Constraint

```sql
-- Pengujian langsung di PostgreSQL:
INSERT INTO unitrade_seller (nim, user_id, name, active)
VALUES ('2023001001', 99, 'Test Seller B', true);
-- Expected: ERROR: duplicate key value violates unique constraint "unitrade_seller_nim_unique"
-- DETAIL: Key (nim)=(2023001001) already exists.
```

> 💡 **Penjelasan:** Ini adalah pengujian langsung di level database untuk memverifikasi bahwa partial index benar-benar berfungsi. Kita mencoba memasukkan seller kedua dengan NIM yang sama dan `active = true`. PostgreSQL seharusnya menolak insert ini dengan pesan error constraint violation. Pengujian ini penting karena membuktikan bahwa proteksi bukan hanya di level aplikasi (yang bisa dilewati jika seseorang akses database langsung) — tapi juga di level database itu sendiri. Defense in depth: validasi di controller, validasi di `@api.constrains`, DAN constraint di database.

---

### Test 3: Idempotency Webhook

```
Skenario: Midtrans kirim webhook 'paid' dua kali untuk order yang sama

Request 1: POST /unitrade/payment/midtrans/webhook {"order_id": "UT-001", "status": "paid"}
  → event_key = "midtrans:UT-001:settlement"
  → event belum ada → diproses → order.x_payment_status = 'paid'
  → event.state = 'processed'
  → Response: {"status": "ok"}

Request 2: POST /unitrade/payment/midtrans/webhook (webhook yang sama)
  → event_key = "midtrans:UT-001:settlement"
  → event SUDAH ADA dengan state='processed' → skip
  → Response: {"status": "ok", "duplicate": true}
  → Status order: TIDAK berubah (tetap 'paid', tidak ada duplikasi)
```

> 💡 **Penjelasan:** Skenario ini mensimulasikan perilaku nyata Midtrans ketika server kita tidak merespons tepat waktu (misalnya restart, high load). Midtrans akan mengirim webhook yang sama beberapa kali sampai mendapat respons HTTP 200. Tanpa mekanisme idempotency, order bisa ter-paid dua kali, escrow ledger dibuat dua kali, notifikasi dikirim dua kali. Dengan cek `event_key` sebelum proses, request kedua langsung merespons HTTP 200 tanpa memproses apapun — Midtrans "puas" dan berhenti retry, tapi database tidak berubah ganda.
