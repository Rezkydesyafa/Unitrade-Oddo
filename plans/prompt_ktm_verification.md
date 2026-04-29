# Prompt: Implementasi Fitur Verifikasi KTM — `unitrade_seller`

> **Role:** Kamu adalah Odoo 17 developer expert.
> Implementasikan fitur **Verifikasi KTM** pada modul `unitrade_seller` yang sudah ada.
> UI halaman `/seller-verification` sudah dibuat — **JANGAN diubah atau dibuat ulang**.
> Fokus hanya pada backend.

---

## 📌 Informasi Proyek

| Key | Value |
|-----|-------|
| Platform | Odoo 17 Community |
| Modul | `unitrade_seller` (sudah ada) |
| Halaman | `/seller-verification` (UI sudah ada) |
| Library Eksternal | `paddleocr`, `Pillow` |
| Odoo Native | `mail`, `ir.attachment`, `res.partner`, `http.Controller` |

### Format NIM UNISA

```
Pola   : 2 digit tahun + 8 digit angka
Regex  : r'\b(22|23|24|25)\d{8}\b'
Contoh : 2411501044
```

---

## 📂 Struktur File

```
unitrade_seller/
├── __init__.py                          ← update import
├── __manifest__.py                      ← update dependencies & data
├── models/
│   ├── __init__.py                      ← tambah import
│   └── seller_verification.py          ← BUAT BARU
├── services/
│   ├── __init__.py                      ← BUAT BARU
│   └── ocr_service.py                  ← BUAT BARU
├── controllers/
│   ├── __init__.py                      ← tambah import
│   └── seller_verification.py          ← BUAT BARU
├── views/
│   └── seller_verification_views.xml   ← BUAT BARU (admin only)
├── security/
│   └── ir.model.access.csv             ← BUAT BARU
└── data/
    └── demo_students.xml               ← BUAT BARU
```

---

## 📋 Task 1 — Model

**File:** `models/seller_verification.py`

### Model 1: `unisa.student`
Tabel referensi mahasiswa UNISA.

| Field | Tipe | Keterangan |
|-------|------|-----------|
| `nim` | Char | required, unique, index=True |
| `name` | Char | required |
| `faculty` | Char | — |
| `active` | Boolean | default=True |

### Model 2: `unitrade.seller.verification`
Inherit `mail.thread`.

| Field | Tipe | Keterangan |
|-------|------|-----------|
| `partner_id` | Many2one `res.partner` | required, tracking=True |
| `ktm_image` | Binary | — |
| `ktm_filename` | Char | — |
| `attachment_id` | Many2one `ir.attachment` | — |
| `ocr_raw_text` | Text | hasil mentah OCR |
| `nim_extracted` | Char | NIM hasil regex |
| `nim_valid` | Boolean | hasil validasi regex |
| `nim_registered` | Boolean | hasil cek database |
| `name_confidence` | Float | digits=(4,3), skor 0.0–1.0 |
| `confidence_flag` | Selection | `low` / `high` |
| `state` | Selection | `draft → pending → approved → rejected`, tracking=True |

**Methods:**
```python
def action_approve(self): self.state = 'approved'
def action_reject(self):  self.state = 'rejected'
```

---

## 📋 Task 2 — OCR Service

**File:** `services/ocr_service.py`

### Ketentuan Umum

```python
# Konstanta
NIM_REGEX = re.compile(r'\b(22|23|24|25)\d{8}\b')
THRESHOLD = 0.70

# Import Guard — wajib
try:
    from paddleocr import PaddleOCR
    from PIL import Image, ImageEnhance, ImageFilter
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    # log warning, jangan crash

# Singleton — di luar class, level module
_ocr_instance = None
def get_ocr_instance(): ...  # inisialisasi sekali saja
```

### Methods `KTMOCRService`

#### `preprocess_image(image_bytes) → np.ndarray`
1. Buka dengan Pillow → convert grayscale
2. Resize proporsional, lebar max 1600px
3. Tingkatkan kontras: `ImageEnhance.Contrast(factor=1.5)`
4. Sharpen: `ImageFilter.SHARPEN`
5. Return numpy array

#### `run_ocr(image_array) → str`
1. Panggil `get_ocr_instance()`
2. `PaddleOCR(use_angle_cls=True, lang='en', show_log=False)`
3. Gabungkan semua baris teks → return string penuh

#### `extract_nim(text) → str | None`
- Gunakan `NIM_REGEX.finditer(text)`
- Return match pertama atau `None`

#### `check_nim_in_database(env, nim) → dict`
```python
student = env['unisa.student'].search([('nim', '=', nim)], limit=1)
return {'found': bool(student), 'student': student or None}
```

#### `check_name_confidence(ocr_text, partner_name) → float`
- Normalize: `.lower().strip()` keduanya
- `difflib.SequenceMatcher(None, a, b).ratio()`
- Return float `0.0–1.0`

#### `process_ktm(env, image_bytes, partner_name) → dict`
Jalankan semua method secara berurutan. Tangkap exception dengan `_logger.exception()`.

```python
return {
    'ocr_text'        : str,
    'nim'             : str | None,
    'nim_valid'       : bool,
    'nim_registered'  : bool,
    'student_name'    : str | None,
    'name_confidence' : float,
    'confidence_flag' : 'high' if score >= 0.70 else 'low'
}
```

---

## 📋 Task 3 — Controller

**File:** `controllers/seller_verification.py`

### Route 1 — `GET /seller-verification`
```
auth='user', website=True
```
- Cari record verifikasi milik partner saat ini
- Render template `unitrade_seller.seller_verification_page`
- Kirim context: `partner`, `verification` (atau `False`)

### Route 2 — `POST /unitrade/seller/verify-ktm`
```
auth='user', type='http', csrf=True, methods=['POST']
```

**Validasi — return JSON error jika gagal:**
- ✗ Ekstensi bukan `.jpg` / `.jpeg` / `.png`
- ✗ Ukuran file > 5 MB (`5 * 1024 * 1024` bytes)

**Pipeline jika valid:**

| Step | Aksi |
|------|------|
| 1 | Baca file bytes dari `ktm_file` |
| 2 | Simpan ke `ir.attachment.sudo()` linked ke partner |
| 3 | Panggil `KTMOCRService.process_ktm()` |
| 4 | Create atau update record `unitrade.seller.verification` |
| 5 | Jika `confidence_flag == 'low'` → `record.message_post()` ke admin |
| 6 | Set `state = 'pending'` |
| 7 | Return JSON response |

**JSON Response:**
```json
{
  "status"          : "success | error",
  "nim"             : "string",
  "nim_valid"       : true,
  "nim_registered"  : true,
  "name_confidence" : 0.85,
  "confidence_flag" : "high",
  "message"         : "string"
}
```

### Route 3 — `GET /unitrade/seller/verification-status`
```
auth='user', type='json'
```
Return `{state, nim_extracted, confidence_flag}` milik user aktif.

---

## 📋 Task 4 — Admin Views (Backend)

**File:** `views/seller_verification_views.xml`

### Form View (`unitrade.seller.verification`)
- Semua field ditampilkan
- `ktm_image`: `widget="image"`
- Statusbar: `draft → pending → approved → rejected`
- Tombol header: **[Approve]** **[Reject]** **[Kirim Email ke Seller]**

### List View
Kolom: `partner_id`, `nim_extracted`, `nim_valid`, `nim_registered`, `name_confidence`, `confidence_flag`, `state`

### Search View
- **Filter:** By State (`draft` / `pending` / `approved` / `rejected`)
- **Filter:** Low Confidence / High Confidence
- **Group By:** Confidence Flag, State

### Menu
`Unitrade > Verifikasi Seller` — akses: `group_system`

---

## 📋 Task 5 — Security

**File:** `security/ir.model.access.csv`

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_unisa_student_admin,unisa.student admin,model_unisa_student,base.group_system,1,1,1,1
access_seller_verif_user,seller.verif user,model_unitrade_seller_verification,base.group_user,1,1,1,0
access_seller_verif_admin,seller.verif admin,model_unitrade_seller_verification,base.group_system,1,1,1,1
```

---

## 📋 Task 6 — Demo Data

**File:** `data/demo_students.xml`

5 record `unisa.student`:

| NIM | Nama | Fakultas |
|-----|------|---------|
| `2411501044` | Budi Santoso | Teknik Informatika |
| `2411201078` | Dewi Lestari | Teknik Informatika |
| `2310201055` | Siti Rahayu | Ilmu Kesehatan |
| `2210301001` | Ahmad Fauzi | Farmasi |
| `2312401033` | Rizky Pratama | Psikologi |

---

## 📋 Task 7 — Manifest & Init

**File:** `__manifest__.py` — update, **jangan hapus yang sudah ada**

```python
{
    'name': 'Unitrade Seller',
    'version': '17.0.1.0.0',
    'depends': ['base', 'mail', 'website'],  # tambahkan jika belum ada
    'external_dependencies': {'python': ['paddleocr', 'Pillow']},
    'data': [
        'security/ir.model.access.csv',
        'views/seller_verification_views.xml',
        'data/demo_students.xml',
    ],
}
```

**File:** `__init__.py` (root) — pastikan import `models`, `services`, `controllers`

---

## ⚙️ Aturan Wajib

1. Setiap file Python wajib pakai `_logger = logging.getLogger(__name__)`
2. Semua method wajib punya `try/except` + `_logger.exception()`
3. Gunakan `.sudo()` **hanya** untuk `ir.attachment` dan `mail.message` di controller
4. PaddleOCR gagal import → return JSON error, **bukan crash server**
5. **JANGAN** ubah atau buat ulang template QWeb yang sudah ada
6. Singleton OCR wajib di luar class (module-level variable)

---

## ✅ Done Criteria

- [ ] `GET /seller-verification` render tanpa error
- [ ] Upload JPG/PNG tersimpan di `ir.attachment`
- [ ] OCR berhasil ekstraksi teks dari gambar KTM
- [ ] Regex menangkap NIM format `2411501044`
- [ ] NIM dicek ke tabel `unisa.student` di database
- [ ] `state` berubah ke `pending` setelah upload
- [ ] Admin mendapat notifikasi jika `confidence_flag == 'low'`
- [ ] Semua endpoint return JSON error yang proper
- [ ] File > 5MB atau bukan JPG/PNG ditolak dengan pesan jelas
