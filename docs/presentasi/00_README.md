# Dokumentasi Presentasi UniTrade — Panduan Navigasi

Folder ini berisi dokumentasi lengkap implementasi sistem UniTrade Marketplace (Odoo 17) yang disusun untuk keperluan presentasi dan penilaian akademis.

---

## Daftar Dokumen (8 File)

| No | File | Topik | Panjang |
|----|------|-------|---------|
| 01 | [01_studi_kasus_dan_kebutuhan_sistem.md](./01_studi_kasus_dan_kebutuhan_sistem.md) | Latar belakang, kebutuhan F/NF, alur bisnis lengkap, arsitektur | Detail |
| 02 | [02_modul_odoo_dan_integrasi.md](./02_modul_odoo_dan_integrasi.md) | Cara Odoo memuat modul, pola `_inherit`, peta integrasi | Detail |
| 03 | [03_integrasi_api_eksternal.md](./03_integrasi_api_eksternal.md) | Midtrans, Google Vision OCR, Gemini AI — kode line-by-line | Detail |
| 04 | [04_keamanan_dan_hak_akses.md](./04_keamanan_dan_hak_akses.md) | 5 lapisan keamanan: OTP, Groups, ACL, Record Rules, Signature | Detail |
| 05 | [05_orm_postgresql_dan_integritas_data.md](./05_orm_postgresql_dan_integritas_data.md) | ORM CRUD, relasi tabel, escrow state machine, constraint | Detail |
| 06 | [06_ketersediaan_dan_kerahasiaan.md](./06_ketersediaan_dan_kerahasiaan.md) | Docker, retry logic, anonimisasi, pengujian availability | Detail |
| 07 | [07_integrasi_frontend_backend.md](./07_integrasi_frontend_backend.md) | QWeb, JSON-RPC, publicWidget, polling, form submit | **BARU** |
| 08 | [08_pertanyaan_dan_jawaban.md](./08_pertanyaan_dan_jawaban.md) | 16 Q&A teknis yang mungkin ditanyakan saat presentasi | **BARU** |

---

## Pemetaan Topik ke Aspek Penilaian

| Aspek Penilaian | Bobot | Dokumen Utama |
|-----------------|-------|---------------|
| Analisis Kebutuhan & Perancangan Sistem | 15% | 01 |
| Implementasi Modul Odoo | 20% | 02 |
| Integrasi Antar Modul | 15% | 02, 07 |
| Implementasi Keamanan | 20% | 04, 08 (Q12-Q16) |
| Integritas Data | 10% | 05, 08 (Q9-Q11) |
| Ketersediaan Sistem | 5% | 06, 08 (Q4-Q8) |
| Kerahasiaan Data | 5% | 04, 06, 08 (Q14-Q15) |
| Demonstrasi & Q&A | 10% | 08 |

---

## Pertanyaan Kunci yang Mungkin Ditanyakan

| No | Pertanyaan | Dokumen |
|----|-----------|---------|
| Q1 | Bagaimana modul-modul saling berkomunikasi? | 02, 08-A |
| Q2 | Bagaimana dependency antar modul dikelola? | 02, 08-A |
| Q3 | Bagaimana cara backend di-override tanpa edit Odoo core? | 02 (_inherit) |
| Q4 | Bagaimana Midtrans terintegrasi? | 03-A, 08-B |
| Q5 | Kenapa webhook perlu validasi signature? | 03-A, 08-B |
| Q6 | Bagaimana Google Vision API dipanggil? | 03-B, 08-B |
| Q7 | Bagaimana Gemini menjaga konteks percakapan? | 03-C, 08-B |
| Q8 | Bagaimana frontend berkomunikasi ke backend? | 07, 08-C |
| Q9 | Apa itu ORM? Bagaimana mapping ke PostgreSQL? | 05, 08-C |
| Q10 | Kapan perlu raw SQL? | 05, 08-C |
| Q11 | Bagaimana sistem escrow menjaga integritas dana? | 05, 08-C |
| Q12 | Bagaimana role (RBAC) diimplementasikan? | 04, 08-D |
| Q13 | Apa beda auth=none/public/user di controller? | 04, 08-D |
| Q14 | Bagaimana API key dijaga keamanannya? | 03, 04, 08-D |
| Q15 | Bagaimana data user dilindungi saat akun dihapus? | 04, 08-D |
| Q16 | Bagaimana sistem mencegah spam OTP? | 04, 08-D |

---

## Referensi File Kode Kunci

| Fitur | File Source | Baris |
|-------|------------|-------|
| **Login override + OTP** | `unitrade_theme/controllers/controllers.py` | L60-117 |
| **Signup validation** | `unitrade_theme/controllers/controllers.py` | L119-175 |
| **OTP controller** | `unitrade_theme/controllers/controllers.py` | L490-510 |
| **Midtrans charge** | `unitrade_payment/models/sale_order.py` | L904-919 |
| **Midtrans webhook** | `unitrade_payment/controllers/main.py` | L1450-1531 |
| **Signature SHA-512** | `unitrade_payment/controllers/main.py` | L1285-1301 |
| **Google Vision OCR** | `unitrade_seller/services/ocr_service.py` | L35-97 |
| **KTM pipeline** | `unitrade_seller/services/ocr_service.py` | L449-530 |
| **Gemini API call** | `unitrade_cs_ai/models/cs_ai_service.py` | L78-133 |
| **Gemini system prompt** | `unitrade_cs_ai/models/cs_ai_service.py` | L49-58 |
| **Security Groups** | `unitrade_seller/security/security.xml` | L13-50 |
| **ACL CSV** | `unitrade_seller/security/ir.model.access.csv` | — |
| **Record Rules** | `unitrade_seller/security/security.xml` | L32-50 |
| **Row locking** | `unitrade_payment/models/sale_order.py` | L780 |
| **Raw SQL migration** | `unitrade_seller/models/seller_verification.py` | L196-209 |
| **NIM unique index** | `unitrade_seller/models/seller.py` | L306-324 |
| **Audit trail** | `unitrade_theme/models/security_activity.py` | L8-47 |
| **Privacy deletion** | `unitrade_theme/models/res_users.py` | L91-135 |
| **Notif polling** | `unitrade_notification/static/src/js/notification_service.js` | L36-176 |
| **Notif controller** | `unitrade_notification/controllers/main.py` | L368-430 |
| **Mapbox geocode proxy** | `unitrade_theme/controllers/controllers.py` | L741-804 |
| **Savepoint** | `unitrade_payment/models/sale_order.py` | L222-248 |
| **Escrow state sync** | `unitrade_payment/models/escrow_ledger.py` | — |
| **Service fee calc** | `unitrade_theme/models/sale_order.py` | L34-49 |
