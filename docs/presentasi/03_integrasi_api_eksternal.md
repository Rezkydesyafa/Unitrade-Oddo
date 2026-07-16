# 03 — Integrasi API Eksternal

UniTrade mengintegrasikan **3 layanan API eksternal**:
- **Midtrans** → Gateway pembayaran (Virtual Account, QRIS, E-Wallet)
- **Google Cloud Vision** → OCR otomatis untuk membaca teks pada foto KTM
- **Google Gemini AI** → Chatbot Customer Service berbasis LLM

> **Pola yang sama digunakan di ketiga integrasi:**
> API key TIDAK pernah ditulis langsung di kode (hardcode).
> Semua key disimpan di tabel `ir.config_parameter` di database,
> sehingga bisa diubah melalui panel admin tanpa menyentuh kode.

---

## A. Integrasi Midtrans (Payment Gateway)

### File Utama
- `unitrade_payment/models/sale_order.py` — logika pembuatan payment
- `unitrade_payment/controllers/main.py` — webhook handler

---

### 1. Mengambil API Key dari Database

```python
# unitrade_payment/models/sale_order.py: L96-104

def _get_midtrans_param(self, key_name, default=''):
    """
    Ambil satu parameter konfigurasi dari tabel ir.config_parameter.
    
    Mengapa pakai ir.config_parameter, bukan hardcode?
    → Supaya admin bisa ganti API key dari panel admin tanpa edit kode.
    → Key tidak terekspos di git repository / source code.
    
    self.env['ir.config_parameter']  = akses model konfigurasi Odoo
    .sudo()   = bypass security karena tabel ini hanya bisa dibaca admin,
                tapi kita butuh akses dari kode yang dijalankan user biasa
    .get_param(key_name, default)  = SELECT value FROM ir_config_parameter
                                     WHERE key = key_name
    """
    return self.env['ir.config_parameter'].sudo().get_param(key_name, default=default)

def _midtrans_api_base_url(self):
    """
    Tentukan URL Midtrans: Sandbox (testing) atau Production (nyata).
    
    Mengapa ada dua URL?
    → Saat development: pakai Sandbox agar tidak bayar uang nyata
    → Saat production: pakai Production agar transaksi nyata berjalan
    
    Parameter 'unitrade.midtrans.is_production' diset oleh admin
    di Settings → System Parameters.
    """
    is_production = str(
        self._get_midtrans_param('unitrade.midtrans.is_production', 'False')
    ).lower() in ('true', '1', 'yes', 'y')
    
    # Kembalikan URL yang sesuai
    return 'https://api.midtrans.com' if is_production else 'https://api.sandbox.midtrans.com'
    #       ↑ Production (transaksi nyata)   ↑ Sandbox (testing, gratis)
```

**Cara membacanya di database:**
```sql
-- Tabel ir_config_parameter di PostgreSQL
SELECT key, value FROM ir_config_parameter 
WHERE key LIKE 'unitrade.midtrans%';

-- Hasil:
-- unitrade.midtrans.server_key    | SB-Mid-server-xxxxx
-- unitrade.midtrans.is_production | False
```

---

### 2. Membuat Transaksi Pembayaran (POST ke Midtrans)

```python
# unitrade_payment/models/sale_order.py: L904-919

def _midtrans_send_charge_request(self, server_key, payload):
    """
    Kirim request ke Midtrans untuk membuat tagihan pembayaran.
    
    Midtrans menggunakan HTTP Basic Authentication:
    - Username = server_key
    - Password = (kosong/string kosong)
    
    Contoh payload yang dikirim:
    {
        "payment_type": "bank_transfer",
        "transaction_details": {
            "order_id": "UT-2026-001",
            "gross_amount": 75000
        },
        "bank_transfer": {"bank": "bca"}
    }
    """
    response = requests.post(
        self._midtrans_api_base_url().rstrip('/') + '/v2/charge',
        # '/v2/charge' = endpoint Midtrans untuk membuat tagihan
        
        data=json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8'),
        # json.dumps()    = ubah dict Python ke string JSON
        # .encode('utf-8') = ubah string ke bytes (format yang dibutuhkan HTTP)
        # separators=(',',':') = JSON tanpa spasi → lebih kecil ukurannya
        
        headers={
            'Accept': 'application/json',         # Kita minta respons dalam JSON
            'Content-Type': 'application/json',   # Kita kirim data dalam JSON
        },
        
        auth=(server_key, ''),
        # Midtrans Basic Auth: server_key sebagai username, password kosong ''
        # requests otomatis encode ke format: "Authorization: Basic <base64>"
        
        timeout=30,
        # Batas tunggu 30 detik — jika Midtrans tidak respons, lempar exception
    )
    
    try:
        response_payload = response.json()   # Parse respons JSON dari Midtrans
    except ValueError:
        # Jika respons bukan JSON (error jaringan dll), simpan teks mentah
        response_payload = {'raw_response': response.text}
    
    # Kembalikan 3 nilai: status_code, data_json, teks_mentah
    return response.status_code, response_payload, response.text
```

**Respons dari Midtrans (contoh Virtual Account BCA):**
```json
{
    "status_code": "201",
    "transaction_id": "abc123",
    "order_id": "UT-2026-001",
    "payment_type": "bank_transfer",
    "va_numbers": [
        {"bank": "bca", "va_number": "1234567890"}
    ]
}
```

---

### 3. Menerima Notifikasi Webhook dari Midtrans

```python
# unitrade_payment/controllers/main.py: L1450-1531

@http.route(
    '/unitrade/payment/midtrans/webhook',  # URL endpoint webhook
    type='http',          # Tipe request: HTTP biasa (bukan JSON-RPC)
    auth='none',          # Tidak perlu login — yang memanggil adalah SERVER Midtrans
    csrf=False,           # Nonaktifkan CSRF token — request dari server eksternal
    methods=['POST']      # Hanya menerima HTTP POST
)
def midtrans_webhook(self, **kwargs):
    """
    Handler untuk notifikasi status pembayaran dari Midtrans.
    
    MENGAPA auth='none' dan csrf=False?
    → Karena yang mengirim request ini adalah server Midtrans (bukan browser user).
    → Server Midtrans tidak punya cookie sesi Odoo dan tidak tahu CSRF token kita.
    → Keamanan dijaga dengan SIGNATURE VALIDATION (lihat poin 4 di bawah).
    
    Alur:
    1. Midtrans kirim POST → /unitrade/payment/midtrans/webhook
    2. Kita baca body request (JSON)
    3. Validasi signature (pastikan benar-benar dari Midtrans)
    4. Update status order di database
    """
    # Baca raw body dari HTTP request
    body = request.httprequest.get_data() or b''
    
    # Parse JSON — jika body kosong, gunakan dict kosong {}
    payload = json.loads(body.decode('utf-8') or '{}')

    # LANGKAH KEAMANAN PERTAMA: Verifikasi signature
    # Jika signature tidak valid → tolak dengan 401 Unauthorized
    if not self._validate_midtrans_signature(payload):
        return self._json_response(
            {'status': 'error', 'message': 'invalid signature'},
            status=401  # HTTP 401 = Unauthorized
        )

    # Normalisasi status Midtrans ke format internal UniTrade
    # Midtrans: 'settlement', 'capture' → UniTrade: 'paid'
    # Midtrans: 'expire'               → UniTrade: 'expired'
    status = self._normalize_midtrans_status(payload)
    
    if status == 'paid':
        # Tandai order sebagai sudah dibayar, pindahkan ke escrow
        intent.sale_order_id.sudo()._unitrade_mark_midtrans_paid(intent.sudo(), payload)
    elif status in ('expired', 'failed'):
        # Update status intent tanpa memproses pembayaran
        intent.sudo().write({'state': status})

    return self._json_response({'status': 'ok'})
    # Respons 'ok' HARUS dikembalikan — jika tidak, Midtrans akan retry terus
```

---

### 4. Validasi Signature SHA-512 (Anti-Pemalsuan)

```python
# unitrade_payment/controllers/main.py: L1285-1301

def _validate_midtrans_signature(self, payload):
    """
    Verifikasi bahwa webhook ini benar-benar dikirim oleh Midtrans, bukan pihak lain.
    
    MENGAPA PENTING?
    → Tanpa validasi ini, siapapun bisa kirim POST palsu ke webhook kita
      dan memalsukan status pembayaran (misalnya: klaim sudah bayar padahal belum).
    
    CARA KERJA:
    → Midtrans dan kita sama-sama tahu 'server_key' (rahasia bersama).
    → Midtrans membuat hash: SHA512(order_id + status_code + gross_amount + server_key)
    → Kita buat hash yang sama dan bandingkan.
    → Jika cocok → webhook asli dari Midtrans ✅
    → Jika tidak cocok → webhook palsu, tolak! ❌
    """
    # Ambil server key dari database (ini yang menjadi "rahasia bersama")
    server_key = self._get_midtrans_param('unitrade.midtrans.server_key')
    
    # Ambil signature yang dikirim Midtrans di body webhook
    signature = payload.get('signature_key')
    
    # Susun string yang akan di-hash (urutan HARUS persis seperti ini)
    raw = '%s%s%s%s' % (
        payload.get('order_id') or '',      # ID order
        payload.get('status_code') or '',   # Kode status (200, 201, dst)
        payload.get('gross_amount') or '',  # Jumlah transaksi
        server_key,                          # Server key (rahasia)
    )
    
    # Hitung SHA-512 dari string tersebut
    expected = hashlib.sha512(raw.encode('utf-8')).hexdigest()
    
    # Bandingkan signature dari Midtrans dengan hasil hash kita
    # .lower() memastikan perbandingan tidak case-sensitive
    return str(signature).lower() == expected.lower()
    #      ↑ dari Midtrans              ↑ dari kalkulasi kita
```

**Ilustrasi:**
```
Midtrans hitung:
  SHA512("UT-2026-001" + "200" + "75000.00" + "SB-Mid-server-xxx")
  = "a3f9d2..." (64 karakter hex)

Kita hitung hal yang sama → hasilnya harus identik.
Jika server_key bocor ke pihak lain → sistem terkompromi!
Itulah mengapa server_key TIDAK BOLEH di-hardcode di kode.
```

---

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

> **OCR** = Optical Character Recognition = kemampuan membaca teks dari gambar.
> Google Cloud Vision memiliki OCR yang sangat akurat untuk berbagai font dan kondisi foto.

### File Utama
- `unitrade_seller/services/ocr_service.py`

---

### 1. Memanggil Google Vision API

```python
# unitrade_seller/services/ocr_service.py: L35-97

GOOGLE_VISION_API_KEY_PARAM = 'unitrade.google_vision.api_key'
# Konstanta untuk nama kunci di ir.config_parameter
# Dipusatkan sebagai konstanta agar mudah diubah jika nama key berubah

@staticmethod
def call_google_vision_api(env, image_bytes):
    """
    Kirim foto KTM ke Google Cloud Vision dan dapatkan semua teks di dalamnya.
    
    Parameter:
    - env         : Odoo environment (untuk akses database)
    - image_bytes : Konten file gambar dalam format bytes (raw data)
    
    Return: String teks mentah hasil OCR (semua teks yang terbaca di gambar)
    """
    
    # LANGKAH 1: Ambil API key dari database
    api_key = env['ir.config_parameter'].sudo().get_param(
        GOOGLE_VISION_API_KEY_PARAM, ''
    )
    if not api_key or api_key == 'INSERT_YOUR_API_KEY_HERE':
        # Jika belum dikonfigurasi, lempar error yang deskriptif
        raise RuntimeError("Google Vision API Key is not configured.")

    url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
    # URL endpoint Google Vision API, key ditambahkan sebagai query parameter

    # LANGKAH 2: Encode gambar ke Base64
    encoded_image = base64.b64encode(image_bytes).decode('utf-8')
    # base64.b64encode() = konversi binary bytes → string base64
    # .decode('utf-8')   = konversi bytes base64 → string Python
    # Kenapa base64? Karena JSON tidak bisa menyimpan binary data langsung

    # LANGKAH 3: Bangun payload (body request) sesuai format Google Vision API
    payload = {
        "requests": [{                          # Bisa kirim banyak gambar sekaligus
            "image": {
                "content": encoded_image        # Gambar dalam base64
            },
            "features": [{
                "type": "TEXT_DETECTION"        # Minta deteksi & ekstrak semua teks
                # Alternatif lain: LABEL_DETECTION (deteksi objek), FACE_DETECTION, dll
            }]
        }]
    }

    # LANGKAH 4: Kirim request ke Google
    response = requests.post(url, json=payload, timeout=30)
    # json=payload  = requests otomatis set Content-Type: application/json
    #                 dan serialize dict ke JSON string
    # timeout=30    = maksimal 30 detik menunggu respons
    
    response.raise_for_status()
    # Jika status code bukan 2xx (sukses), lempar exception
    # Misalnya: 403 = API key tidak valid, 429 = quota habis

    # LANGKAH 5: Ambil teks dari respons JSON
    data = response.json()
    text_annotations = data['responses'][0].get('textAnnotations', [])
    # textAnnotations[0] = item pertama = SEMUA teks yang terdeteksi (paling lengkap)
    # textAnnotations[1:] = per-kata/per-kalimat yang terdeteksi (lebih granular)
    
    full_text = text_annotations[0].get('description', '')
    # 'description' berisi semua teks yang terbaca, dipisahkan newline '\n'
    
    return full_text.replace('\n', ' ').strip()
    # Ganti newline dengan spasi agar mudah diproses regex selanjutnya
```

**Contoh respons Google Vision API:**
```json
{
    "responses": [{
        "textAnnotations": [{
            "description": "UNIVERSITAS AISYIYAH YOGYAKARTA\nKARTU TANDA MAHASISWA\nNIM: 2023001001\nNama: Budi Santoso\nFakultas: Ilmu Kesehatan"
        }]
    }]
}
```

---

### 2. Pipeline Verifikasi KTM (7 Langkah Berurutan)

```python
# unitrade_seller/services/ocr_service.py: L449-530

@classmethod
def run_full_pipeline(cls, env, image_bytes):
    """
    Pipeline lengkap verifikasi KTM. Setiap langkah bisa menghentikan proses.
    
    Return: dict dengan kunci:
    - verification_status: 'approved' | 'rejected' | 'manual_review'
    - reason: kode alasan jika tidak approved
    - nim: NIM yang diekstrak (jika berhasil)
    """
    
    # ── LANGKAH 1: Panggil Google Vision API ──────────────────────────────
    try:
        raw_text = cls.call_google_vision_api(env, image_bytes)
        # raw_text = semua teks di foto KTM (satu string panjang)
    except Exception as e:
        _logger.exception('[PIPELINE] Google Vision API failed: %s', e)
        # Jika API gagal → JANGAN crash, masuk review manual saja
        return {
            'reason': f'vision_api_failed: {str(e)}',
            'verification_status': 'manual_review'
            # Admin akan review secara manual di dashboard
        }

    # ── LANGKAH 2: Cek apakah gambar mengandung kata kunci KTM ────────────
    is_ktm, _ = cls.validate_ktm_keywords(raw_text)
    # KTM_KEYWORDS yang dicari:
    # ['KARTU', 'MAHASISWA', 'UNISA', 'AISYIYAH', 'NIM', 'FAKULTAS', 'YOGYAKARTA']
    # Minimal beberapa keyword harus ada agar dianggap gambar KTM
    
    if not is_ktm:
        return {
            'reason': 'no_ktm_keywords',
            'verification_status': 'rejected'
            # Gambar yang di-upload bukan KTM UNISA → langsung ditolak
        }

    # ── LANGKAH 3: Ekstrak NIM dengan regex ───────────────────────────────
    nim = cls.extract_nim(raw_text, normalized_text)
    # NIM_REGEX = re.compile(r'\d{8,12}')
    # Mencari angka berurutan 8-12 digit → kemungkinan besar itu NIM
    
    if not nim:
        return {
            'reason': 'nim_not_extracted',
            'verification_status': 'manual_review'
            # NIM tidak terbaca jelas (foto buram dll) → review manual
        }

    # ── LANGKAH 4: Cocokkan NIM ke database mahasiswa UNISA ───────────────
    student = env['unisa.student'].sudo().search(
        [('nim', '=', nim)], limit=1
    )
    # unisa.student = tabel data mahasiswa aktif UNISA yang di-import dari SiAkad
    
    if not student:
        return {
            'reason': 'nim_not_in_db',
            'verification_status': 'manual_review'
            # NIM terbaca tapi tidak ada di database mahasiswa aktif
            # Kemungkinan: alumni, mahasiswa non-aktif, atau NIM salah baca OCR
        }

    # ── LANGKAH 5: Fuzzy matching nama ───────────────────────────────────
    name_match_score = SequenceMatcher(
        None,
        extracted_name,   # Nama dari teks KTM (hasil OCR)
        student.name      # Nama dari database mahasiswa
    ).ratio()
    # ratio() menghasilkan nilai 0.0 (tidak mirip) sampai 1.0 (identik)
    # SequenceMatcher = algoritma Levenshtein yang toleran terhadap typo
    
    if name_match_score < 0.6:
        # Threshold 0.6 = nama harus minimal 60% mirip
        return {
            'reason': 'name_token_not_matched',
            'verification_status': 'rejected'
            # Nama di KTM tidak cocok dengan nama di database → ditolak
        }

    # ── SEMUA LANGKAH LULUS ───────────────────────────────────────────────
    return {
        'verification_status': 'approved',   # ✅ Otomatis disetujui
        'nim': nim,                           # NIM yang terverifikasi
        'student_name': student.name,         # Nama dari database
        'name_match_score': name_match_score, # Skor kemiripan nama
    }
```

### Tabel Kode Penolakan Otomatis

| Kode Alasan | Kondisi | Status | Aksi Selanjutnya |
|-------------|---------|--------|-----------------|
| `ocr_empty` | Foto terlalu gelap / blur | `rejected` | Upload ulang foto |
| `no_ktm_keywords` | Bukan foto KTM UNISA | `rejected` | Upload KTM yang benar |
| `nim_not_extracted` | NIM tidak terbaca OCR | `manual_review` | Admin review manual |
| `nim_not_in_db` | NIM tidak di database | `manual_review` | Admin verifikasi manual |
| `name_token_not_matched` | Nama < 60% cocok | `rejected` | Upload ulang / hubungi admin |
| `vision_api_failed` | Error koneksi ke Google | `manual_review` | Admin review manual |

---

## C. Integrasi Google Gemini AI (Customer Service Chatbot)

> **LLM** = Large Language Model = AI yang dilatih dengan teks besar dan bisa menjawab pertanyaan alami.
> Gemini 2.5 Flash dipilih karena **cepat dan hemat kuota** untuk chatbot CS.

### File Utama
- `unitrade_cs_ai/models/cs_ai_service.py`

---

### 1. Konfigurasi Gemini (Konstanta & API Key)

```python
# unitrade_cs_ai/models/cs_ai_service.py: L12-17

# URL base API Gemini (versi v1beta = terbaru)
GEMINI_API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models'

GEMINI_TIMEOUT_SECONDS = 20   # Batas tunggu respons AI: 20 detik
GEMINI_MAX_RETRIES = 3        # Coba ulang maksimal 3x jika server busy
GEMINI_RETRY_BACKOFF = 1.2    # Jeda antar percobaan: 1.2s, 2.4s, 3.6s
GEMINI_RETRYABLE_STATUS = (500, 502, 503, 504)
# Status kode yang berarti "server AI lagi sibuk, coba lagi nanti"

class UnitradeCsAiService(models.AbstractModel):
    _name = 'unitrade.cs.ai.service'
    # AbstractModel = tidak buat tabel di PostgreSQL, hanya kumpulan method

    def _api_key(self):
        """Ambil Gemini API key dari database (bukan dari kode)."""
        return (self.env['ir.config_parameter'].sudo()
                .get_param('unitrade.gemini.api_key', '') or '').strip()

    def _model_name(self):
        """
        Tentukan model Gemini yang digunakan.
        Default: gemini-2.5-flash (cepat dan murah).
        Admin bisa ganti ke gemini-1.5-pro jika butuh kualitas lebih tinggi.
        """
        return (self.env['ir.config_parameter'].sudo()
                .get_param('unitrade.gemini.model', 'gemini-2.5-flash') or 'gemini-2.5-flash').strip()
```

---

### 2. Membangun Konteks Percakapan (Riwayat 5 Pesan Terakhir)

```python
# unitrade_cs_ai/models/cs_ai_service.py: L60-73

AI_HISTORY_LIMIT = 5
# Hanya kirim 5 pesan terakhir ke Gemini (bukan seluruh history)
# Kenapa dibatasi?
# → Setiap request ke Gemini dibayar berdasarkan jumlah token (kata)
# → Semakin panjang context, semakin mahal dan lambat
# → 5 pesan sudah cukup untuk menjaga konteks percakapan

def _build_contents(self, session, user_message):
    """
    Bangun array 'contents' yang dikirim ke Gemini.
    Format Gemini mengharapkan array pesan bergantian user/model:
    [
        {"role": "user",  "parts": [{"text": "pertanyaan 1"}]},
        {"role": "model", "parts": [{"text": "jawaban AI 1"}]},
        {"role": "user",  "parts": [{"text": "pertanyaan 2"}]},  ← pesan terbaru
    ]
    """
    # Ambil 5 pesan terakhir dari database, diurutkan dari yang terlama
    history = session.message_ids.sorted('id')[-AI_HISTORY_LIMIT:]
    
    contents = []
    for message in history:
        # Odoo menyimpan author_type: 'user' atau 'ai'
        # Gemini membutuhkan: 'user' atau 'model'
        role = 'user' if message.author_type == 'user' else 'model'
        contents.append({
            'role': role,
            'parts': [{'text': message.body or ''}]
        })
    
    # Pastikan pesan terbaru user ada di akhir array
    # (Gemini tidak boleh diakhiri dengan role 'model')
    if not contents or contents[-1]['role'] != 'user':
        contents.append({
            'role': 'user',
            'parts': [{'text': user_message or ''}]
        })
    return contents
```

---

### 3. Memanggil Gemini API dengan Retry Logic

```python
# unitrade_cs_ai/models/cs_ai_service.py: L78-133

def generate_reply(self, session, user_message):
    """
    Panggil Gemini API dan kembalikan teks jawaban AI.
    Dilengkapi retry logic agar tidak langsung gagal jika server busy.
    """
    api_key = self._api_key()
    
    # Bangun payload lengkap untuk dikirim ke Gemini
    payload = {
        # System instruction = "kepribadian" dan aturan untuk AI
        # Ini TIDAK terlihat oleh user, hanya digunakan sebagai panduan AI
        'system_instruction': {
            'parts': [{'text': self._build_system_prompt(session)}]
        },
        
        # Riwayat percakapan (5 pesan terakhir + pesan baru)
        'contents': self._build_contents(session, user_message),
        
        # Pengaturan generasi teks
        'generationConfig': {
            'temperature': 0.4,
            # temperature 0.0 = sangat deterministik (selalu jawaban sama)
            # temperature 1.0 = sangat kreatif/acak
            # 0.4 = sedikit variasi tapi tetap konsisten untuk CS
            
            'maxOutputTokens': 512,
            # Batasi panjang respons AI (≈ 300-400 kata)
            # Agar jawaban tidak terlalu panjang dan cepat di-render
        },
    }
    
    # Bangun URL dengan nama model dan API key
    url = '%s/%s:generateContent?key=%s' % (
        GEMINI_API_BASE,      # https://generativelanguage.googleapis.com/v1beta/models
        self._model_name(),   # gemini-2.5-flash
        api_key               # API key dari database
    )
    # URL akhir: https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=xxx
    
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json'}

    # ── RETRY LOOP ─────────────────────────────────────────────────────────
    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        # attempt = 1, 2, atau 3
        
        try:
            response = requests.post(url, data=body, headers=headers,
                                     timeout=GEMINI_TIMEOUT_SECONDS)
        except requests.RequestException as error:
            # Gagal koneksi (timeout, DNS error, dll)
            if attempt < GEMINI_MAX_RETRIES:
                time.sleep(GEMINI_RETRY_BACKOFF * attempt)
                # attempt=1: tunggu 1.2 detik
                # attempt=2: tunggu 2.4 detik
                continue   # Coba lagi
            raise UserError(_('Gagal menghubungi layanan AI.')) from error

        if response.status_code in GEMINI_RETRYABLE_STATUS:
            # Server Gemini busy (500/502/503/504)
            if attempt < GEMINI_MAX_RETRIES:
                time.sleep(GEMINI_RETRY_BACKOFF * attempt)
                continue   # Coba lagi
            raise UserError(_('Layanan AI sedang sibuk.'))
        
        break   # Request sukses, keluar dari loop
    # ── AKHIR RETRY LOOP ────────────────────────────────────────────────────

    if response.status_code == 429:
        # 429 = Too Many Requests = quota API habis
        raise UserError(_('Batas pemakaian AI tercapai.'))

    data = response.json()
    return self._extract_text(data)
    # _extract_text() mengambil teks dari: data['candidates'][0]['content']['parts'][0]['text']
```

---

### 4. System Prompt (Kepribadian AI)

```python
# unitrade_cs_ai/models/cs_ai_service.py: L49-58

def _build_system_prompt(self, session):
    return _(
        # System prompt mendefinisikan "siapa" AI ini dan batasannya
        
        "Kamu adalah asisten Customer Service UniTrade, marketplace jual-beli C2C "
        "untuk mahasiswa UNISA Yogyakarta. "
        # → AI tahu konteks platform (UniTrade, UNISA, C2C)
        
        "Jawab dengan ramah, ringkas, dan dalam Bahasa Indonesia. "
        # → AI harus pakai Bahasa Indonesia, tidak formal berlebihan
        
        "Bantu pertanyaan seputar cara belanja, pembayaran (Midtrans), "
        "pengiriman (Ambil Sendiri / GoSend), status escrow, dan kebijakan umum. "
        # → Daftar topik yang boleh dijawab AI secara mandiri
        
        "Jika pertanyaan menyangkut data pribadi, pembatalan kompleks, refund, sengketa, "
        "atau hal yang tidak kamu ketahui, sarankan customer menekan tombol "
        "'Chat dengan Customer Service'."
        # → Batasan: hal sensitif/kompleks harus dieskalasi ke human CS
    )
```

**Mengapa System Prompt penting?**

Tanpa system prompt, Gemini bisa saja:
- Menjawab dalam Bahasa Inggris
- Membahas topik di luar UniTrade
- Mengklaim bisa memproses refund (padahal hanya AI, tidak punya akses database)
- Memberikan informasi yang tidak relevan

System prompt mengunci perilaku AI agar sesuai kebutuhan bisnis.
