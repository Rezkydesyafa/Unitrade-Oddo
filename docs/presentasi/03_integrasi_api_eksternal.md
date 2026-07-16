# 03 — Integrasi API Eksternal

UniTrade mengintegrasikan 3 layanan API eksternal: **Midtrans** (pembayaran), **Google Cloud Vision** (OCR KTM), dan **Google Gemini** (AI Customer Service).

---

## A. Integrasi Midtrans (Payment Gateway)

### File Utama
- `unitrade_payment/models/sale_order.py` — logika pembuatan payment
- `unitrade_payment/controllers/main.py` — webhook handler

### 1. Mengambil Konfigurasi API Key (dari `ir.config_parameter`)

> **Prinsip**: API key TIDAK pernah di-hardcode. Selalu diambil dari parameter sistem database.

```python
# unitrade_payment/models/sale_order.py: L96-104
def _get_midtrans_param(self, key_name, default=''):
    # Mengambil konfigurasi dari tabel ir.config_parameter di PostgreSQL
    return self.env['ir.config_parameter'].sudo().get_param(key_name, default=default)

def _midtrans_api_base_url(self):
    is_production = str(
        self._get_midtrans_param('unitrade.midtrans.is_production', 'False')
    ).lower() in ('true', '1', 'yes', 'y')
    # Sandbox vs Production URL
    return 'https://api.midtrans.com' if is_production else 'https://api.sandbox.midtrans.com'
```

### 2. Membuat Transaksi Pembayaran (POST ke Midtrans API)

```python
# unitrade_payment/models/sale_order.py: L904-919
def _midtrans_send_charge_request(self, server_key, payload):
    response = requests.post(
        self._midtrans_api_base_url().rstrip('/') + '/v2/charge',
        data=json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8'),
        headers={
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        },
        auth=(server_key, ''),  # Basic Auth: server_key sebagai username
        timeout=30,
    )
    try:
        response_payload = response.json()
    except ValueError:
        response_payload = {'raw_response': response.text}
    return response.status_code, response_payload, response.text
```

### 3. Menerima Notifikasi Webhook dari Midtrans

```python
# unitrade_payment/controllers/main.py: L1450-1531
@http.route('/unitrade/payment/midtrans/webhook', type='http', auth='none', csrf=False, methods=['POST'])
def midtrans_webhook(self, **kwargs):
    body = request.httprequest.get_data() or b''
    payload = json.loads(body.decode('utf-8') or '{}')

    # VALIDASI KEAMANAN: Verifikasi signature SHA-512
    if not self._validate_midtrans_signature(payload):
        return self._json_response({'status': 'error', 'message': 'invalid signature'}, status=401)

    # Proses status pembayaran
    status = self._normalize_midtrans_status(payload)
    if status == 'paid':
        intent.sale_order_id.sudo()._unitrade_mark_midtrans_paid(intent.sudo(), payload)
    elif status in ('expired', 'failed'):
        intent.sudo().write({'state': status})

    return self._json_response({'status': 'ok'})
```

### 4. Validasi Signature Keamanan Webhook

```python
# unitrade_payment/controllers/main.py: L1285-1301
def _validate_midtrans_signature(self, payload):
    server_key = self._get_midtrans_param('unitrade.midtrans.server_key')
    signature = payload.get('signature_key')
    # Raw string untuk hashing: order_id + status_code + gross_amount + server_key
    raw = '%s%s%s%s' % (
        payload.get('order_id') or '',
        payload.get('status_code') or '',
        payload.get('gross_amount') or '',
        server_key,
    )
    expected = hashlib.sha512(raw.encode('utf-8')).hexdigest()
    return str(signature).lower() == expected.lower()
```

### Metode Pembayaran yang Didukung
| Kode | Label | Tipe |
|------|-------|------|
| `bca_va` | BCA Virtual Account | Bank Transfer |
| `bni_va` | BNI Virtual Account | Bank Transfer |
| `bri_va` | BRI Virtual Account | Bank Transfer |
| `gopay` | GoPay | E-Wallet |
| `shopeepay` | ShopeePay | E-Wallet |
| `qris` | QRIS | QR Code |

---

## B. Integrasi Google Cloud Vision API (OCR KTM)

### File Utama
- `unitrade_seller/services/ocr_service.py`

### 1. Memanggil Google Vision API

```python
# unitrade_seller/services/ocr_service.py: L35-97
GOOGLE_VISION_API_KEY_PARAM = 'unitrade.google_vision.api_key'

@staticmethod
def call_google_vision_api(env, image_bytes):
    """
    Mengirim gambar KTM ke Google Cloud Vision API untuk TEXT_DETECTION.
    """
    # 1. Ambil API key dari database (tidak hardcode)
    api_key = env['ir.config_parameter'].sudo().get_param(
        GOOGLE_VISION_API_KEY_PARAM, ''
    )
    if not api_key or api_key == 'INSERT_YOUR_API_KEY_HERE':
        raise RuntimeError("Google Vision API Key is not configured.")

    url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"

    # 2. Encode gambar ke Base64
    encoded_image = base64.b64encode(image_bytes).decode('utf-8')

    # 3. Bangun payload request
    payload = {
        "requests": [{
            "image": {"content": encoded_image},
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }

    # 4. Kirim request POST ke Google
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()

    # 5. Ambil teks hasil OCR
    data = response.json()
    text_annotations = data['responses'][0].get('textAnnotations', [])
    full_text = text_annotations[0].get('description', '')
    return full_text.replace('\n', ' ').strip()  # Normalisasi newline
```

### 2. Pipeline Verifikasi KTM (7 Langkah)

```python
# unitrade_seller/services/ocr_service.py: L449-530
@classmethod
def run_full_pipeline(cls, env, image_bytes):
    # Step 1: Panggil Google Vision API → dapat raw_text
    raw_text = cls.call_google_vision_api(env, image_bytes)

    # Step 2: Validasi apakah gambar mengandung kata kunci KTM
    is_ktm, _ = cls.validate_ktm_keywords(raw_text)
    # KTM_KEYWORDS = ['KARTU', 'MAHASISWA', 'UNISA', 'NIM', 'FAKULTAS', ...]
    if not is_ktm:
        return {'reason': 'no_ktm_keywords', 'verification_status': 'rejected'}

    # Step 3: Ekstrak NIM menggunakan regex
    nim = cls.extract_nim(raw_text, normalized_text)
    # NIM_REGEX = re.compile(r'\d{8,12}')
    if not nim:
        return {'reason': 'nim_not_extracted', 'verification_status': 'manual_review'}

    # Step 4: Cocokkan NIM dengan database mahasiswa UNISA
    student = env['unisa.student'].sudo().search([('nim', '=', nim)], limit=1)
    if not student:
        return {'reason': 'nim_not_in_db', 'verification_status': 'manual_review'}

    # Step 5: Fuzzy matching nama pada KTM vs nama di database
    name_match_score = SequenceMatcher(None, extracted_name, student.name).ratio()
    if name_match_score < 0.6:
        return {'reason': 'name_token_not_matched', 'verification_status': 'rejected'}

    # Semua validasi LULUS
    return {'verification_status': 'approved', 'nim': nim}
```

### Kode Penolakan Otomatis

| Kode Alasan | Kondisi | Aksi |
|-------------|---------|------|
| `ocr_empty` | Tidak ada teks terdeteksi | Ditolak |
| `no_ktm_keywords` | Bukan gambar KTM | Ditolak |
| `nim_not_extracted` | NIM tidak terbaca | Review manual admin |
| `nim_not_in_db` | NIM tidak di database UNISA | Review manual admin |
| `name_token_not_matched` | Nama tidak cocok | Ditolak |
| `vision_api_failed` | Error API Google | Masuk review manual |

---

## C. Integrasi Google Gemini AI (Customer Service Chatbot)

### File Utama
- `unitrade_cs_ai/models/cs_ai_service.py`

### 1. Konfigurasi Gemini

```python
# unitrade_cs_ai/models/cs_ai_service.py: L12-17
GEMINI_API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models'
GEMINI_TIMEOUT_SECONDS = 20
GEMINI_MAX_RETRIES = 3       # Retry otomatis jika server busy
GEMINI_RETRY_BACKOFF = 1.2   # Jeda antar retry (detik)
GEMINI_RETRYABLE_STATUS = (500, 502, 503, 504)

class UnitradeCsAiService(models.AbstractModel):
    _name = 'unitrade.cs.ai.service'

    def _api_key(self):
        # Ambil API key dari database, tidak hardcode
        return (self.env['ir.config_parameter'].sudo()
                .get_param('unitrade.gemini.api_key', '') or '').strip()

    def _model_name(self):
        # Default model: gemini-2.5-flash, bisa diubah via config
        return (self.env['ir.config_parameter'].sudo()
                .get_param('unitrade.gemini.model', 'gemini-2.5-flash') or 'gemini-2.5-flash').strip()
```

### 2. Membangun Konteks Percakapan (5 Pesan Terakhir)

```python
# unitrade_cs_ai/models/cs_ai_service.py: L60-73
AI_HISTORY_LIMIT = 5

def _build_contents(self, session, user_message):
    """Bangun array `contents` Gemini dari 5 pesan terakhir + pesan baru."""
    history = session.message_ids.sorted('id')[-AI_HISTORY_LIMIT:]
    contents = []
    for message in history:
        # Map role Odoo ke format Gemini (user / model)
        role = 'user' if message.author_type == 'user' else 'model'
        contents.append({'role': role, 'parts': [{'text': message.body or ''}]})
    if not contents or contents[-1]['role'] != 'user':
        contents.append({'role': 'user', 'parts': [{'text': user_message or ''}]})
    return contents
```

### 3. Memanggil Gemini API dengan Retry Logic

```python
# unitrade_cs_ai/models/cs_ai_service.py: L78-133
def generate_reply(self, session, user_message):
    api_key = self._api_key()
    payload = {
        'system_instruction': {'parts': [{'text': self._build_system_prompt(session)}]},
        'contents': self._build_contents(session, user_message),
        'generationConfig': {'temperature': 0.4, 'maxOutputTokens': 512},
    }
    url = '%s/%s:generateContent?key=%s' % (GEMINI_API_BASE, self._model_name(), api_key)
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json'}

    # Retry loop untuk menangani server busy
    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        try:
            response = requests.post(url, data=body, headers=headers, timeout=GEMINI_TIMEOUT_SECONDS)
        except requests.RequestException as error:
            if attempt < GEMINI_MAX_RETRIES:
                time.sleep(GEMINI_RETRY_BACKOFF * attempt)
                continue
            raise UserError(_('Gagal menghubungi layanan AI.')) from error

        if response.status_code in GEMINI_RETRYABLE_STATUS:
            if attempt < GEMINI_MAX_RETRIES:
                time.sleep(GEMINI_RETRY_BACKOFF * attempt)
                continue
            raise UserError(_('Layanan AI sedang sibuk.'))
        break

    if response.status_code == 429:
        raise UserError(_('Batas pemakaian AI tercapai.'))

    data = response.json()
    return self._extract_text(data)  # Ambil teks dari candidates[0]
```

### System Prompt Gemini

```python
# unitrade_cs_ai/models/cs_ai_service.py: L49-58
def _build_system_prompt(self, session):
    return _(
        "Kamu adalah asisten Customer Service UniTrade, marketplace jual-beli C2C "
        "untuk mahasiswa UNISA Yogyakarta. Jawab dengan ramah, ringkas, dan dalam "
        "Bahasa Indonesia. Bantu pertanyaan seputar cara belanja, pembayaran (Midtrans), "
        "pengiriman (Ambil Sendiri / GoSend), status escrow, dan kebijakan umum. "
        "Jika pertanyaan menyangkut data pribadi, pembatalan kompleks, refund, sengketa, "
        "atau hal yang tidak kamu ketahui, sarankan customer menekan tombol "
        "'Chat dengan Customer Service'."
    )
```
