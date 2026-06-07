# Setting Odoo Server Production UniTrade

Dokumen ini berisi checklist konfigurasi Odoo production untuk UniTrade. Target setup:

- Domain website: `https://unitrade.web.id`
- Email domain: `unitrade.web.id`
- OTP dikirim lewat email
- Payment gateway: Midtrans
- OCR KTM: Google Vision API
- Peta/alamat: Mapbox
- Payout: manual
- Tidak memakai reCAPTCHA
- Tidak memakai Xendit

Jangan menyimpan API key, SMTP password, atau secret lain di file project. Simpan melalui Odoo UI atau `ir.config_parameter` di database production.

## 1. Konfigurasi Server Odoo

Jika Odoo berjalan di belakang Nginx, Cloudflare, atau reverse proxy lain, aktifkan proxy mode.

Contoh konfigurasi Odoo production:

```ini
proxy_mode = True
list_db = False
dbfilter = ^unitrade_db$
```

Pastikan website public mengarah ke:

```text
https://unitrade.web.id
```

Di Odoo, set system parameter:

```text
web.base.url = https://unitrade.web.id
```

Jika memakai Docker Compose di VPS, upgrade module setelah deploy tetap wajib dijalankan. Workflow deploy project sudah diarahkan untuk menjalankan:

```bash
docker compose run --rm web odoo -d unitrade_db -u unitrade_theme,unitrade_notification,unitrade_admin,unitrade_seller,unitrade_dispute,unitrade_payment,unitrade_review,unitrade_product_ext --stop-after-init
```

## 2. Email Domain unitrade.web.id

UniTrade memakai email untuk OTP, reset password, dan notifikasi. Email tidak dikirim langsung dari kode custom ke provider tertentu; email dikirim lewat mail system Odoo (`mail.mail`) dan Outgoing Mail Server Odoo.

Rekomendasi mailbox:

```text
noreply@unitrade.web.id
info@unitrade.web.id
postmaster@unitrade.web.id
```

Gunakan satu mailbox utama untuk pengiriman sistem:

```text
noreply@unitrade.web.id
```

### 2.1 Pilih Penyedia Email

Gunakan penyedia email yang mendukung SMTP dan DNS authentication. Contoh:

- Email hosting dari provider domain/hosting
- Google Workspace
- Zoho Mail
- Titan Mail
- Mailgun, SendGrid, atau SMTP transactional lain

Untuk production, lebih aman memakai managed email provider daripada self-hosted mail server, karena deliverability, SPF, DKIM, DMARC, dan reputasi IP lebih mudah dijaga.

### 2.2 Buat Mailbox

Di panel email provider, buat mailbox:

```text
noreply@unitrade.web.id
```

Simpan data berikut:

```text
SMTP host     = dari provider email
SMTP port     = 465 untuk SSL, atau 587 untuk STARTTLS
SMTP username = noreply@unitrade.web.id
SMTP password = password mailbox atau app password
Encryption    = SSL/TLS atau STARTTLS sesuai provider
```

Jika memakai Google Workspace, biasanya gunakan app password atau SMTP relay sesuai kebijakan akun Workspace. Jangan memakai password akun utama jika provider meminta app password.

### 2.3 Setting DNS Email

Di DNS `unitrade.web.id`, tambahkan record yang diberikan provider email.

Record yang umumnya wajib:

```text
MX    = server penerima email dari provider
TXT   = SPF
TXT   = DKIM
TXT   = DMARC
```

Contoh SPF. Pilih sesuai provider, jangan aktifkan semuanya sekaligus:

```text
Jika memakai Google Workspace:
v=spf1 include:_spf.google.com ~all

Jika memakai email hosting/cPanel dengan mail.unitrade.web.id:
v=spf1 mx a:mail.unitrade.web.id ~all

Jika memakai provider lain:
pakai SPF yang diberikan provider tersebut.
```

Contoh DMARC awal:

```text
Name  = _dmarc
Type  = TXT
Value = v=DMARC1; p=quarantine; rua=mailto:postmaster@unitrade.web.id; adkim=s; aspf=s
```

DKIM harus diambil dari provider email karena setiap provider membuat selector dan value DKIM yang berbeda.

Setelah DNS dibuat, tunggu propagasi. Biasanya 5 menit sampai 24 jam, tergantung DNS provider.

### 2.4 Setting SMTP Di Odoo

Aktifkan developer mode di Odoo, lalu buka:

```text
Settings > Technical > Email > Outgoing Mail Servers
```

Buat server baru:

```text
Description  = UniTrade Mail
SMTP Server  = SMTP host provider
SMTP Port    = 465 atau 587
Connection Security = SSL/TLS untuk 465, STARTTLS untuk 587
Username     = noreply@unitrade.web.id
Password     = password/app password mailbox
From Filter  = unitrade.web.id
Active       = True
```

Klik `Test Connection`. Jika gagal, cek kembali:

- Host SMTP benar
- Port benar
- SSL/STARTTLS sesuai
- Username memakai alamat email lengkap
- Password memakai app password jika provider mewajibkan
- Firewall VPS tidak memblokir koneksi keluar ke port SMTP

### 2.5 Setting Email Company Dan Notifikasi

Set email perusahaan di Odoo:

```text
Settings > Companies > My Company
Email = noreply@unitrade.web.id
```

Set system parameter:

```text
unitrade.notification.email_from = noreply@unitrade.web.id
```

OTP UniTrade saat ini memakai:

```text
email_from = company.email atau noreply@unitrade.dev fallback
```

Jadi company email wajib diisi agar OTP tidak memakai fallback development.

### 2.6 Tes Email Dan OTP

Setelah SMTP tersimpan:

1. Klik `Test Connection` di Outgoing Mail Server.
2. Buat akun user baru di `/web/signup`.
3. Pastikan user menerima email OTP.
4. Cek menu email queue jika tidak terkirim:

```text
Settings > Technical > Email > Emails
```

Untuk production, pastikan system parameter ini kosong atau `False`:

```text
unitrade.otp.show_dev_code = False
```

Jika parameter itu `True`, kode OTP akan tampil di halaman verifikasi. Itu hanya boleh untuk development lokal.

## 3. System Parameter Wajib

Masuk ke:

```text
Settings > Technical > Parameters > System Parameters
```

Isi parameter berikut.

### 3.1 Base URL

```text
web.base.url = https://unitrade.web.id
```

### 3.2 OTP Dan Email

```text
unitrade.otp.show_dev_code = False
unitrade.notification.email_from = noreply@unitrade.web.id
unitrade.notification.broadcast_batch_size = 200
unitrade.notification.allowed_url_prefixes = /
unitrade.notification.retention_days = 180
```

### 3.3 Midtrans

Isi sesuai environment production Midtrans:

```text
unitrade.midtrans.server_key = <MIDTRANS_SERVER_KEY_PRODUCTION>
unitrade.midtrans.client_key = <MIDTRANS_CLIENT_KEY_PRODUCTION>
unitrade.midtrans.is_production = True
unitrade.midtrans.payment_expiry_minutes = 30
```

Webhook di dashboard Midtrans:

```text
https://unitrade.web.id/unitrade/payment/midtrans/webhook
```

Metode pembayaran default:

```text
unitrade.midtrans.method.bca_va.enabled = True
unitrade.midtrans.method.mandiri_bill.enabled = True
unitrade.midtrans.method.bni_va.enabled = True
unitrade.midtrans.method.bri_va.enabled = True
unitrade.midtrans.method.permata_va.enabled = True
unitrade.midtrans.method.cimb_va.enabled = False
unitrade.midtrans.method.qris.enabled = True
unitrade.midtrans.method.gopay.enabled = True
unitrade.midtrans.method.shopeepay.enabled = False
unitrade.midtrans.method.indomaret.enabled = False
unitrade.midtrans.method.alfamart.enabled = False
unitrade.midtrans.method.card.enabled = False
```

Aktifkan hanya channel yang memang sudah aktif di dashboard Midtrans.

### 3.4 Google Vision OCR KTM

```text
unitrade.google_vision.api_key = <GOOGLE_VISION_API_KEY>
```

Pastikan di Google Cloud:

- Cloud Vision API aktif
- Billing aktif
- API key dibatasi agar aman, minimal hanya untuk Vision API jika memungkinkan

### 3.5 Mapbox

Kode runtime membaca parameter ini:

```text
unitrade.mapbox_access_token = <MAPBOX_PUBLIC_TOKEN>
unitrade.mapbox_style_url = mapbox://styles/mapbox/streets-v12
```

Token untuk peta web harus public token yang diawali:

```text
pk.
```

Catatan: ada parameter lama `unitrade.mapbox.token`, tetapi halaman profile/alamat membaca `unitrade.mapbox_access_token`. Jadi isi `unitrade.mapbox_access_token`.

### 3.6 Fee Listing Produk

```text
unitrade.seller.listing_fee.enabled = True
unitrade.seller.listing_fee.threshold = 1000000
unitrade.seller.listing_fee.low_amount = 2000
unitrade.seller.listing_fee.high_amount = 5000
unitrade.seller.listing_fee.validity_days = 30
unitrade.seller.posting_admin_fee = 0
unitrade.seller.listing_duration_days = 30
```

### 3.7 Order, Refund, Dan Dispute

```text
unitrade.order.cancel_window_minutes = 30
unitrade.cancel_window_minutes = 10
unitrade.auto_complete_hours = 24
unitrade.refund_window_days = 2
unitrade.refund.max_upload_mb = 25
unitrade.refund.buyer_evidence_hours = 48
unitrade.dispute_response_hours = 48
unitrade.refund.decision_hours = 72
```

### 3.8 Payout Manual

Karena tidak memakai Xendit, payout production dilakukan manual oleh admin.

```text
unitrade.payout.mode = manual
unitrade.payout.min = 50000
unitrade.payout.fee = 2500
unitrade.payout.instructions = Admin memproses payout manual setelah escrow releasable.
```

Jangan gunakan action Xendit payout jika Xendit tidak dikonfigurasi.

### 3.9 Legal Dan Policy

```text
unitrade.legal.terms_url = https://unitrade.web.id/terms
unitrade.legal.refund_url = https://unitrade.web.id/refund-policy
unitrade.legal.protection_label = Transaksi terlindungi escrow UniTrade
unitrade.terms_privacy_version = 2026-05-17
```

## 4. Yang Tidak Dipakai

### 4.1 reCAPTCHA Tidak Dipakai

Biarkan parameter ini kosong:

```text
recaptcha_public_key =
recaptcha_private_key =
recaptcha_min_score =
```

Jika module `google_recaptcha` terinstall tetapi `recaptcha_private_key` kosong, Odoo menganggap reCAPTCHA tidak aktif dan verifikasi akan dilewati.

### 4.2 Xendit Tidak Dipakai

Biarkan parameter ini kosong atau `False`:

```text
unitrade.xendit.secret_key =
unitrade.xendit.webhook_token =
unitrade.xendit.is_production = False
unitrade.xendit.payment_expiry_minutes = 30
```

Tidak perlu memasang webhook Xendit:

```text
/unitrade/payment/xendit/webhook
```

Checkout UniTrade saat ini diarahkan ke Midtrans. Xendit hanya legacy/opsional dan tidak perlu disetting jika payout manual.

### 4.3 GoSend Belum Wajib

Saat ini module delivery masih manual/GPS estimate. GoSend credential belum menjadi integrasi runtime wajib.

Biarkan kosong jika belum memakai GoSend real:

```text
unitrade.gosend.client_id =
unitrade.gosend.client_secret =
unitrade.gosend.credential =
```

## 5. Command Cepat Set Parameter

Gunakan ini jika ingin mengisi parameter dari VPS lewat Odoo shell. Ganti value placeholder sebelum dijalankan.

```bash
cd /root/unitrade

docker compose run --rm web odoo shell -d unitrade_db --no-http <<'PY'
ICP = env['ir.config_parameter'].sudo()

params = {
    'web.base.url': 'https://unitrade.web.id',
    'unitrade.otp.show_dev_code': 'False',
    'unitrade.notification.email_from': 'noreply@unitrade.web.id',
    'unitrade.notification.broadcast_batch_size': '200',
    'unitrade.notification.allowed_url_prefixes': '/',
    'unitrade.notification.retention_days': '180',

    'unitrade.midtrans.server_key': '<MIDTRANS_SERVER_KEY_PRODUCTION>',
    'unitrade.midtrans.client_key': '<MIDTRANS_CLIENT_KEY_PRODUCTION>',
    'unitrade.midtrans.is_production': 'True',
    'unitrade.midtrans.payment_expiry_minutes': '30',

    'unitrade.google_vision.api_key': '<GOOGLE_VISION_API_KEY>',
    'unitrade.mapbox_access_token': '<MAPBOX_PUBLIC_TOKEN_PK>',
    'unitrade.mapbox_style_url': 'mapbox://styles/mapbox/streets-v12',

    'unitrade.seller.listing_fee.enabled': 'True',
    'unitrade.seller.listing_fee.threshold': '1000000',
    'unitrade.seller.listing_fee.low_amount': '2000',
    'unitrade.seller.listing_fee.high_amount': '5000',
    'unitrade.seller.listing_fee.validity_days': '30',
    'unitrade.seller.posting_admin_fee': '0',
    'unitrade.seller.listing_duration_days': '30',

    'unitrade.order.cancel_window_minutes': '30',
    'unitrade.cancel_window_minutes': '10',
    'unitrade.auto_complete_hours': '24',
    'unitrade.refund_window_days': '2',
    'unitrade.refund.max_upload_mb': '25',
    'unitrade.refund.buyer_evidence_hours': '48',
    'unitrade.dispute_response_hours': '48',
    'unitrade.refund.decision_hours': '72',

    'unitrade.payout.mode': 'manual',
    'unitrade.payout.min': '50000',
    'unitrade.payout.fee': '2500',
    'unitrade.payout.instructions': 'Admin memproses payout manual setelah escrow releasable.',

    'unitrade.legal.terms_url': 'https://unitrade.web.id/terms',
    'unitrade.legal.refund_url': 'https://unitrade.web.id/refund-policy',
    'unitrade.legal.protection_label': 'Transaksi terlindungi escrow UniTrade',
    'unitrade.terms_privacy_version': '2026-05-17',

    # Not used in production setup.
    'recaptcha_public_key': '',
    'recaptcha_private_key': '',
    'recaptcha_min_score': '',
    'unitrade.xendit.secret_key': '',
    'unitrade.xendit.webhook_token': '',
    'unitrade.xendit.is_production': 'False',
    'unitrade.gosend.client_id': '',
    'unitrade.gosend.client_secret': '',
    'unitrade.gosend.credential': '',
}

for key, value in params.items():
    ICP.set_param(key, value)

env.cr.commit()
print('UniTrade production system parameters updated.')
PY
```

## 6. Google OAuth Login

Jika Google login tetap dipakai, buka Odoo:

```text
Settings > Technical > OAuth Providers
```

Provider `Google` harus aktif dan `Client ID` diisi dari Google Cloud.

Di Google Cloud Console, tambahkan redirect URI:

```text
https://unitrade.web.id/auth_oauth/signin
```

Jika Google login tidak ingin dipakai, nonaktifkan provider Google dari Odoo.

## 7. Data Mahasiswa KTM

Verifikasi seller memakai model:

```text
unisa.student
```

Pastikan data mahasiswa production sudah benar. Minimal field:

```text
name
nim
program_studi / prodi
```

Di project ini ada `unitrade_seller/data/demo_students.xml`. Untuk production, pastikan data dummy tidak menjadi sumber verifikasi utama jika data resmi sudah tersedia.

## 8. Checklist Go Live

Sebelum production dibuka:

- `web.base.url` sudah `https://unitrade.web.id`
- `proxy_mode = True`
- `list_db = False`
- SSL HTTPS aktif
- SMTP `noreply@unitrade.web.id` berhasil `Test Connection`
- Email OTP diterima user baru
- `unitrade.otp.show_dev_code = False`
- Midtrans production key sudah diisi
- Midtrans webhook sudah diarahkan ke `/unitrade/payment/midtrans/webhook`
- Xendit kosong karena tidak dipakai
- reCAPTCHA kosong karena tidak dipakai
- Google Vision API key aktif
- Mapbox public token aktif
- Data `unisa.student` production sudah ada
- Admin UniTrade punya akses dashboard admin
- Cron Odoo aktif untuk email queue, escrow, expiry payment, dan notifikasi
- Setelah deploy, module upgrade berjalan otomatis dari GitHub Actions

