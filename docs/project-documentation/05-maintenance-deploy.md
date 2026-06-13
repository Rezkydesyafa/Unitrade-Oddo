# 05. Maintenance, Integrations, Deploy

Dokumen ini berisi integrasi eksternal, konfigurasi, logging, testing, upgrade module, deploy, dan troubleshooting.

## Integrasi dan Service Eksternal

### Midtrans

Dipakai untuk pembayaran buyer.

Module: `unitrade_payment`

Data:

- `unitrade.payment.intent`
- `unitrade.payment.event`
- `sale.order`
- `unitrade.escrow.ledger`

Config parameter:

- `unitrade.midtrans.server_key`
- `unitrade.midtrans.client_key`
- `unitrade.midtrans.environment`

Hal penting:

- Credential wajib di `ir.config_parameter`.
- Webhook harus valid signature.
- Webhook harus idempotent karena provider bisa mengirim event lebih dari sekali.

### Escrow Internal

Escrow adalah logika internal, bukan provider eksternal. Dana seller ditahan di `unitrade.escrow.ledger` sampai order selesai.

State utama:

- `held`
- `releasable`
- `released`
- `refunded`

### Payout Manual

Payout saat ini manual oleh admin.

Flow:

1. Seller request payout.
2. Admin cek payout.
3. Admin transfer dana di luar sistem.
4. Admin mark paid di UniTrade.
5. Ledger menjadi released.

Model:

- `unitrade.seller.payout`
- `unitrade.escrow.ledger`

### OCR KTM

Dipakai untuk membaca NIM/nama dari foto KTM.

Module: `unitrade_seller`

Data:

- `unitrade.seller.verification`
- `unitrade.seller`
- `unitrade.university`
- `unisa.student`

Catatan:

- OCR membantu, bukan keputusan final.
- Admin tetap bisa approve/reject.
- Hasil OCR perlu disimpan untuk audit/debugging.

### Gemini AI

Dipakai untuk customer service AI.

Module: `unitrade_cs_ai`

Config parameter:

- `unitrade.gemini.api_key`
- `unitrade.gemini.model`
- `unitrade.cs.ai_enabled`
- `unitrade.cs.ai_rate_limit`

Catatan:

- AI bisa gagal atau tidak akurat.
- User harus punya opsi eskalasi ke CS/admin.

### Odoo Bus

Dipakai untuk realtime:

- Chat buyer-seller
- Customer service live chat
- Notification update

Jika realtime tidak berjalan, cek:

- Browser console
- Odoo bus
- Session/channel token
- Controller realtime endpoint

### Email dan OTP

Dipakai untuk:

- Kirim OTP
- Email notifikasi
- Template seller approval/rejection jika aktif

Jika email gagal:

1. Cek SMTP Odoo.
2. Cek `mail.mail`/log Odoo.
3. Cek template email.
4. Cek rate limit OTP.

## Config Parameter Penting

| Config | Fungsi |
| --- | --- |
| `unitrade.midtrans.server_key` | Server key Midtrans |
| `unitrade.midtrans.client_key` | Client key Midtrans |
| `unitrade.midtrans.environment` | Sandbox/production |
| `unitrade.escrow.auto_confirm_receipt_hours` | Batas auto-confirm diterima |
| `unitrade.seller.payout_release_hours` | Masa tunggu sebelum payout |
| `unitrade.payout.min` | Minimal payout jika diterapkan |
| `unitrade.payout.fee` | Biaya payout jika diterapkan |
| `unitrade.gemini.api_key` | API key Gemini |
| `unitrade.gemini.model` | Model Gemini |
| `unitrade.cs.ai_enabled` | Aktif/nonaktif CS AI |
| `unitrade.cs.ai_rate_limit` | Limit CS AI |

## Logging

Gunakan `_logger`, bukan `print()`.

Log yang penting:

| Area | Data yang sebaiknya dilog |
| --- | --- |
| Submit KTM | `verification_id`, `partner_id`, `user_id`, `state`, `nim` |
| Payment webhook | reference/order/status/event key |
| Escrow | ledger id, state, order id, seller id |
| Payout | payout id, seller, amount, admin |
| Refund | dispute id, state, actor |
| Chat/CS | conversation/session id, error ringkas |

Jangan log credential/API key.

## Upgrade Module Local

Contoh upgrade module local Windows:

```powershell
& 'C:\Program Files\Odoo 17.0.20260217\python\python.exe' `
  'C:\Program Files\Odoo 17.0.20260217\server\odoo-bin' `
  -c 'C:\Program Files\Odoo 17.0.20260217\server\odoo.conf' `
  -d unitrade_db `
  -u unitrade_theme `
  --stop-after-init `
  --no-http `
  --logfile='D:\Unitrade_Oddo\logs\upgrade_unitrade_theme.log'
```

Upgrade beberapa module:

```powershell
-u unitrade_theme,unitrade_seller,unitrade_payment
```

## Module Yang Umum Di-upgrade

| Perubahan | Upgrade module |
| --- | --- |
| Navbar, shop, cart, checkout, profile | `unitrade_theme` |
| Seller dashboard, KTM | `unitrade_seller` |
| Product marketplace field | `unitrade_product_ext` |
| Payment, escrow, payout | `unitrade_payment` |
| Delivery | `unitrade_delivery` |
| Refund/dispute | `unitrade_dispute` |
| Chat | `unitrade_chat` |
| Notifikasi | `unitrade_notification` |
| Review | `unitrade_review` |
| Wishlist | `unitrade_wishlist` |
| CS AI | `unitrade_cs_ai` |
| Admin dashboard | `unitrade_admin` |

## Testing Yang Disarankan

| Area | Test |
| --- | --- |
| KTM | Submit KTM, manual review, approve, reject, revoke seller |
| Cart | Empty cart, add item, update qty, checkout |
| Payment | Payment intent, webhook success, webhook duplicate |
| Escrow | held, releasable, released, refunded |
| Payout | request payout, admin mark paid, prevent duplicate payout |
| Chat | create conversation, send message, presence, report |
| Notification | unread count, mark read, redirect order shipped |
| Review | create review, helpful toggle, report once |
| CS AI | session, AI reply, escalate, admin reply |
| Refund | create dispute, evidence, admin action |

## Debug Data Tidak Tampil

Pola umum:

1. Cek model sumber data.
2. Cek domain search.
3. Cek state/status data.
4. Cek ACL/record rule.
5. Cek controller mengirim variable ke template.
6. Cek JS/CSS jika hanya masalah tampilan.
7. Cek log Odoo.

Contoh KTM pending tidak tampil:

1. Cek `unitrade.seller.verification`.
2. Cek state `pending/manual_review`.
3. Cek `get_ktm_verification_queue`.
4. Cek filter halaman admin.
5. Cek group admin.

## Debug Asset Tidak Muncul

1. Cek file ada di repository.
2. Cek file terdaftar di `__manifest__.py`.
3. Upgrade module terkait.
4. Clear browser cache jika perlu.
5. Cek bundle asset di devtools.

## Deploy dan CI/CD

Catatan penting untuk production:

- Jika `docker-compose.yml` di VPS bind mount `/root/unitrade` ke `/mnt/extra-addons`, isi folder VPS bisa menimpa isi addon dari image.
- Jika file tidak ada di VPS, validasi seperti `grep /mnt/extra-addons/.../seller_dashboard.css` bisa gagal meskipun image sudah benar.
- Pastikan repo di VPS sinkron atau jangan gunakan bind mount yang menimpa addon image production.

## Error Umum CI/CD

### CSS Tidak Ada

Contoh:

```text
grep: /mnt/extra-addons/unitrade_seller/static/src/css/seller_dashboard.css: No such file or directory
```

Kemungkinan:

- File tidak ada di VPS.
- Bind mount menimpa isi image.
- Workflow masih mengecek path lama.

Solusi:

- Sinkronkan repo di VPS.
- Update path check workflow.
- Evaluasi bind mount production.

### Curl Production Gagal

Contoh:

```text
curl: (28) Failed to connect to unitrade.web.id port 443
```

Kemungkinan:

- Server belum selesai restart/deploy.
- Domain/HTTPS sedang down.
- Nginx/container belum siap.
- Firewall/port bermasalah.
- Health check terlalu cepat.

Solusi:

- Tambahkan retry dan timeout.
- Cek service di VPS.
- Cek Nginx dan Docker container.

## Checklist Sebelum Push

1. `git status`
2. Pastikan hanya file yang dimaksud berubah.
3. Jalankan test/validasi sesuai perubahan.
4. Jika mengubah XML, cek ID template/view.
5. Jika mengubah model, cek access CSV.
6. Jika mengubah assets, cek manifest.
7. Tulis commit message jelas.

## Checklist Setelah Deploy

1. Cek halaman utama.
2. Cek login.
3. Cek fitur yang berubah.
4. Cek log Odoo/container.
5. Cek public asset jika CI memverifikasi asset.
6. Cek admin/notification jika fitur backend.

## Production DB Check

Untuk kasus data production, jangan menebak hanya dari UI.

Contoh cek KTM:

1. Cari berdasarkan NIM.
2. Cari berdasarkan email/user.
3. Cek `unitrade.seller.verification`.
4. Cek `unitrade.seller`.
5. Cek state terbaru: pending, manual_review, approved, rejected.

Hindari update data langsung di DB kecuali benar-benar jelas dan ada backup.
