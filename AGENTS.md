# UniTrade Marketplace — AI Context (AGENTS.md / AI Instructions)

> File ini digunakan sebagai context untuk AI coding assistant seperti Cursor, Codex, Copilot.
> Letakkan di root folder project agar AI selalu punya konteks yang benar.

## Apa itu UniTrade?
UniTrade adalah marketplace C2C berbasis Odoo 17 untuk mahasiswa UNISA Yogyakarta.
Penjual harus verifikasi KTM (mahasiswa aktif), pembeli adalah semua user terdaftar.
Transaksi menggunakan Midtrans, pengiriman via GoSend, OCR KTM via PaddleOCR.

## Aturan saat generate kode:

1. **Selalu gunakan prefix `tw-`** untuk class Tailwind
2. **Odoo model** harus inherit dari `models.Model` dengan `_name` yang benar
3. **Controller** harus gunakan `@http.route` decorator dengan parameter yang sesuai
4. **Jangan hardcode** credential API — ambil dari `ir.config_parameter`
5. **Setiap model baru** wajib ada entry di `security/ir.model.access.csv`
6. **Setiap folder** `models/` dan `controllers/` harus ada `__init__.py`
7. Gunakan **`_logger`** untuk logging, bukan `print()`
8. Gunakan **`sudo()`** dengan bijak — hanya jika benar-benar perlu bypass security

## Struktur file yang diharapkan saat generate module baru:
```
module_name/
├── __init__.py          (import models, controllers)
├── __manifest__.py      (metadata, depends, assets, data)
├── models/
│   ├── __init__.py
│   └── model_name.py
├── controllers/
│   ├── __init__.py
│   └── main.py
├── views/
│   └── template.xml
└── security/
    └── ir.model.access.csv
```

## Contoh pola kode yang BENAR:

### Model
```python
from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class UnitradeExample(models.Model):
    _name = 'unitrade.example'
    _description = 'UniTrade Example Model'

    name = fields.Char(string='Nama', required=True)
    user_id = fields.Many2one('res.users', string='User', required=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
    ], default='draft')
```

### Controller
```python
from odoo import http
from odoo.http import request

class UnitradeController(http.Controller):

    @http.route('/unitrade/example', type='http', auth='public', website=True)
    def example_page(self, **kwargs):
        values = {'title': 'UniTrade Example'}
        return request.render('unitrade_example.template_id', values)

    @http.route('/unitrade/webhook', type='json', auth='none', csrf=False, methods=['POST'])
    def webhook_handler(self, **kwargs):
        data = request.jsonrequest
        # process...
        return {'status': 'ok'}
```

### QWeb Template
```xml
<template id="unitrade_page" name="UniTrade Page">
    <t t-call="website.layout">
        <div class="tw-max-w-7xl tw-mx-auto tw-px-4 tw-py-8">
            <h1 class="tw-text-3xl tw-font-bold tw-text-text-main">
                <t t-esc="title"/>
            </h1>
        </div>
    </t>
</template>
```
