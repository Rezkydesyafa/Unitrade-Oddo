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

**Pengujian:**
- Kirim webhook dengan `gross_amount: "55000"` padahal intent amount adalah `50000`
- Expected: HTTP 400 error, event dicatat sebagai `failed`, order tidak berubah

### Test 2: Unique NIM Constraint

```sql
-- Pengujian langsung di PostgreSQL:
INSERT INTO unitrade_seller (nim, user_id, name, active)
VALUES ('2023001001', 99, 'Test Seller B', true);
-- Expected: ERROR: duplicate key value violates unique constraint "unitrade_seller_nim_unique"
-- DETAIL: Key (nim)=(2023001001) already exists.
```

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
