#!/bin/bash
# ============================================================
#  UniTrade GitHub Issues Creator
#  Jalankan di Git Bash:
#  bash setup_github.sh Rezkydesyafa/unitrade
# ============================================================

REPO=${1}

if [ -z "$REPO" ]; then
  echo ""
  echo "❌ ERROR: Masukkan nama repo!"
  echo "   Usage: bash setup_github.sh Rezkydesyafa/unitrade"
  echo ""
  exit 1
fi

echo ""
echo "======================================================"
echo "  UniTrade GitHub Setup"
echo "  Repo: $REPO"
echo "======================================================"
echo ""

# ── CEK gh CLI ────────────────────────────────────────────
if ! command -v gh &> /dev/null; then
  echo "❌ GitHub CLI belum terinstall!"
  echo "   Download di: https://cli.github.com"
  exit 1
fi

# ── CEK LOGIN ─────────────────────────────────────────────
echo "🔐 Mengecek status login..."
gh auth status &> /dev/null
if [ $? -ne 0 ]; then
  echo "⚠️  Belum login. Menjalankan gh auth login..."
  gh auth login
fi
echo "✅ Sudah login!"
echo ""

# ══════════════════════════════════════════════════════════
# STEP 1 — BUAT LABELS
# ══════════════════════════════════════════════════════════
echo "🏷️  [1/3] Membuat Labels..."
echo ""

create_label() {
  gh label create "$1" --color "$2" --description "$3" --repo "$REPO" --force 2>/dev/null
  echo "   ✅ Label: $1"
}

create_label "priority:critical" "EF4444" "Blocker, harus selesai duluan"
create_label "priority:high"     "F59E0B" "Penting, dikerjakan setelah critical"
create_label "priority:medium"   "3B82F6" "Perlu tapi tidak blocker"
create_label "priority:low"      "94A3B8" "Nice to have"
create_label "setup"             "6366F1" "Environment dan konfigurasi"
create_label "auth"              "8B5CF6" "Autentikasi dan profil"
create_label "seller"            "EC4899" "Fitur penjual"
create_label "product"           "F43F5E" "Produk dan katalog"
create_label "payment"           "10B981" "Pembayaran"
create_label "delivery"          "06B6D4" "Pengiriman GoSend"
create_label "chat"              "F59E0B" "Chat real-time"
create_label "notification"      "0EA5E9" "Notifikasi"
create_label "review"            "D97706" "Rating dan ulasan"
create_label "admin"             "1E293B" "Dashboard admin"
create_label "frontend"          "0284C7" "Custom UI dan QWeb"
create_label "backend"           "475569" "Python dan model Odoo"
create_label "ui"                "7DD3FC" "Desain dan styling Figma"
create_label "ocr"               "F97316" "PaddleOCR verifikasi KTM"
create_label "location"          "16A34A" "GPS dan Google Places"
create_label "qa"                "7C3AED" "Quality Assurance testing"
create_label "security"          "DC2626" "Security testing"
create_label "performance"       "CA8A04" "Performance testing"
create_label "deploy"            "059669" "Production deployment"
create_label "devops"            "0F172A" "Server dan infrastruktur"

echo ""
echo "✅ Semua labels berhasil dibuat!"
echo ""

# ══════════════════════════════════════════════════════════
# STEP 2 — BUAT MILESTONES
# ══════════════════════════════════════════════════════════
echo "🎯 [2/3] Membuat Milestones..."
echo ""

create_milestone() {
  gh api repos/$REPO/milestones \
    -f title="$1" \
    -f description="$2" \
    -f due_on="$3" \
    --silent 2>/dev/null
  echo "   ✅ Milestone: $1"
}

create_milestone "Phase 1 - Setup & Foundation"        "Odoo 17 install, konfigurasi, unitrade_theme"          "2026-04-28T00:00:00Z"
create_milestone "Phase 2 - Auth & Profil"             "Registrasi, OTP, login, profil, wishlist"              "2026-05-02T00:00:00Z"
create_milestone "Phase 3 - Verifikasi Seller"         "Aktivasi seller, KTM OCR, status verifikasi"           "2026-05-05T00:00:00Z"
create_milestone "Phase 4 - Produk & Katalog"          "Detail produk, keranjang, search, filter, sort"        "2026-05-08T00:00:00Z"
create_milestone "Phase 5 - Transaksi & Komunikasi"    "Chat, payment, status transaksi, GoSend"               "2026-05-12T00:00:00Z"
create_milestone "Phase 6 - Notifikasi"                "Notif in-app, email, pengaturan notifikasi"            "2026-05-13T00:00:00Z"
create_milestone "Phase 7 - Dashboard Seller"          "Dashboard, pesanan, produk, chat, earnings"            "2026-05-16T00:00:00Z"
create_milestone "Phase 8 - Dashboard Admin"           "GMV, moderasi, monitoring, pengaturan sistem"          "2026-05-18T00:00:00Z"
create_milestone "Phase 9 - Lokasi & Bantuan"          "GPS, Google Places, rating, FAQ, helpdesk"             "2026-05-20T00:00:00Z"
create_milestone "Phase 10 - QA & Deploy"              "Security test, UAT, production deploy Nginx+SSL"       "2026-05-22T00:00:00Z"

echo ""
echo "✅ Semua milestones berhasil dibuat!"
echo ""

# ══════════════════════════════════════════════════════════
# STEP 3 — BUAT ISSUES
# ══════════════════════════════════════════════════════════
echo "📋 [3/3] Membuat 45 Issues..."
echo ""

create_issue() {
  local num=$1
  local title=$2
  local body=$3
  local labels=$4
  local milestone=$5

  gh issue create \
    --repo "$REPO" \
    --title "$title" \
    --body "$body" \
    --label "$labels" \
    --milestone "$milestone" \
    --silent 2>/dev/null

  echo "   [$num/45] ✅ $title" | cut -c1-80
  sleep 0.3
}

# ── PHASE 1: SETUP ────────────────────────────────────────────────────────────

create_issue 1 \
"SETUP-01: Install & konfigurasi Odoo 17 + odoo.conf" \
"## Deskripsi
Install Odoo 17, konfigurasi odoo.conf, setup PostgreSQL, aktifkan path custom-addons.

## Acceptance Criteria
- [ ] Odoo berjalan di localhost:8069
- [ ] Database unitrade_db terbuat
- [ ] Path custom-addons terbaca
- [ ] Login admin berhasil

## Konfigurasi odoo.conf
\`\`\`ini
[options]
addons_path = C:\\Program Files\\Odoo 17\\addons,D:\\UniTrade\\custom-addons
db_name = unitrade_db
http_port = 8069
\`\`\`" \
"setup,backend,priority:critical" \
"Phase 1 - Setup & Foundation"

create_issue 2 \
"SETUP-02: Install semua native Odoo module yang diperlukan" \
"## Deskripsi
Install semua modul native Odoo via menu Apps.

## Modul yang Diinstall
- [ ] website
- [ ] website_sale
- [ ] sale
- [ ] account
- [ ] stock
- [ ] portal
- [ ] auth_signup
- [ ] im_livechat
- [ ] mail
- [ ] helpdesk
- [ ] payment
- [ ] delivery
- [ ] website_sale_wishlist
- [ ] rating

## Acceptance Criteria
- [ ] Semua modul terinstall tanpa error
- [ ] /shop bisa diakses
- [ ] Portal /my bisa diakses" \
"setup,backend,priority:critical" \
"Phase 1 - Setup & Foundation"

create_issue 3 \
"SETUP-03: Buat modul unitrade_theme - Tailwind + layout custom" \
"## Deskripsi
Buat custom module unitrade_theme sebagai base tampilan semua halaman UniTrade.

## Struktur Folder
\`\`\`
unitrade_theme/
├── __manifest__.py
├── static/src/css/unitrade.css
├── static/src/js/unitrade.js
└── views/layout.xml
\`\`\`

## Acceptance Criteria
- [ ] Tailwind CSS ter-compile dan ter-load
- [ ] Token warna Figma terimplementasi
- [ ] Override website.layout berhasil
- [ ] Semua halaman pakai font dan warna UniTrade

## Odoo Module
website (inherit)" \
"setup,frontend,ui,priority:critical" \
"Phase 1 - Setup & Foundation"

# ── PHASE 2: AUTH ─────────────────────────────────────────────────────────────

create_issue 4 \
"F-01: Registrasi & Login - form + field No WhatsApp" \
"## Deskripsi
Form registrasi dan login dengan field wajib. Extend res.partner dengan no_whatsapp.

## Odoo Native yang Dipakai
auth_signup, portal, res.users — handle session, password hashing Bcrypt

## Yang Perlu Dicustom
- [ ] Tambah field no_whatsapp di res.partner
- [ ] Override template /web/login sesuai Figma
- [ ] Override template /web/signup sesuai Figma
- [ ] Validasi client-side form

## Acceptance Criteria
- [ ] User bisa daftar dengan Email, Password, Nama, No WA
- [ ] User bisa login dengan Email/Password
- [ ] Password tersimpan Bcrypt
- [ ] Redirect ke OTP setelah register

## Custom Module: unitrade_auth
## Estimasi: 2 hari" \
"auth,frontend,backend,priority:critical" \
"Phase 2 - Auth & Profil"

create_issue 5 \
"F-02: OTP Verifikasi - 6 digit, expired 5 menit, rate limit 3x" \
"## Deskripsi
Sistem OTP untuk verifikasi akun baru. Kode 6 digit, expired 5 menit, max 3x resend.

## Odoo Native yang Dipakai
mail — kirim email via SMTP queue

## Yang Perlu Dicustom
- [ ] Field OTP di res.users: otp_code, otp_expiry, otp_attempt, is_verified
- [ ] Controller /unitrade/auth/verify-otp
- [ ] Logic rate limiting max 3x resend
- [ ] Logic expired 5 menit
- [ ] Template email OTP
- [ ] Halaman input OTP sesuai Figma

## Acceptance Criteria
- [ ] OTP 6 digit terkirim ke email
- [ ] OTP expired setelah 5 menit
- [ ] Max 3x resend, setelah itu locked
- [ ] Akun aktif setelah OTP benar

## Custom Module: unitrade_auth
## Estimasi: 2 hari" \
"auth,frontend,backend,priority:critical" \
"Phase 2 - Auth & Profil"

create_issue 6 \
"F-03: Lupa Password - reset via email, token 30 menit" \
"## Deskripsi
Reset password via email. Token unik, single-use, expired 30 menit.

## Odoo Native yang Dipakai
auth_signup — SUDAH ADA fitur reset password native!

## Yang Perlu Dicustom
- [ ] Override template halaman reset password sesuai Figma
- [ ] Pastikan token expiry 30 menit terkonfigurasi

## Acceptance Criteria
- [ ] User input email → link reset terkirim
- [ ] Link expired setelah 30 menit
- [ ] Token single-use
- [ ] Password berhasil direset

## Custom Module: unitrade_theme (styling only)
## Estimasi: 1 hari" \
"auth,frontend,priority:high" \
"Phase 2 - Auth & Profil"

create_issue 7 \
"F-04: Manajemen Profil - extend res.partner + Google Places alamat" \
"## Deskripsi
Halaman edit profil lengkap. Extend res.partner dengan field tambahan dan Google Places autocomplete.

## Odoo Native yang Dipakai
portal, res.partner — halaman /my/account sudah ada

## Yang Perlu Dicustom
- [ ] Field tambahan: username (unique), gender, birth_date
- [ ] Alamat lengkap: Provinsi, Kota, Kecamatan, Kode Pos, Detail
- [ ] Google Places API autocomplete untuk input alamat
- [ ] Upload foto profil max 2MB dengan validasi
- [ ] Override template /my/account sesuai Figma

## Acceptance Criteria
- [ ] User bisa edit semua field profil
- [ ] Username unique tervalidasi
- [ ] Autocomplete alamat Jogja berfungsi
- [ ] Foto profil tersimpan

## Custom Module: unitrade_auth
## Estimasi: 2 hari" \
"auth,frontend,backend,priority:high" \
"Phase 2 - Auth & Profil"

create_issue 8 \
"F-05: Wishlist - toggle ikon hati, halaman favorit" \
"## Deskripsi
Fitur simpan produk ke wishlist. Ikon hati di katalog, toggle AJAX, halaman daftar favorit.

## Odoo Native yang Dipakai
website_sale_wishlist — SUDAH ADA modul wishlist native!

## Yang Perlu Dicustom
- [ ] Override template ikon hati sesuai Figma (warna, animasi)
- [ ] Override halaman /shop/wishlist sesuai Figma
- [ ] Pastikan ikon berubah warna saat produk sudah di-wishlist

## Acceptance Criteria
- [ ] Klik ikon hati → produk masuk wishlist
- [ ] Klik lagi → keluar wishlist
- [ ] Ikon hati menyala jika sudah di wishlist
- [ ] Halaman favorit tampil semua produk tersimpan

## Custom Module: unitrade_theme (styling only)
## Estimasi: 1 hari" \
"frontend,ui,priority:medium" \
"Phase 2 - Auth & Profil"

create_issue 9 \
"F-06: Monitoring Transaksi - Pesanan Saya dengan filter status" \
"## Deskripsi
Halaman Pesanan Saya dengan filter status lengkap dan detail item pesanan.

## Odoo Native yang Dipakai
portal, sale — halaman /my/orders sudah ada!

## Yang Perlu Dicustom
- [ ] Label status Indonesia: Draft/Confirmed/Shipped/Done/Cancelled
- [ ] Filter status di UI
- [ ] Override template /my/orders sesuai Figma
- [ ] Tampilkan No. Invoice, Tanggal, Rincian Item

## Acceptance Criteria
- [ ] Semua pesanan tampil dengan status benar
- [ ] Filter per status berfungsi
- [ ] Detail pesanan bisa dibuka

## Custom Module: unitrade_theme
## Estimasi: 1 hari" \
"frontend,ui,priority:critical" \
"Phase 2 - Auth & Profil"

create_issue 10 \
"F-07/08: Pengaturan Akun - notifikasi, keamanan, ganti password" \
"## Deskripsi
Halaman pengaturan akun multi-tab: notifikasi, keamanan, aktivitas, hapus akun, ganti password.

## Odoo Native yang Dipakai
portal, res.users — base settings ada

## Yang Perlu Dicustom
- [ ] Layout multi-tab pengaturan
- [ ] Tab keamanan: ganti password, cek aktivitas login
- [ ] Tab notifikasi: toggle per jenis
- [ ] Tab hapus akun: form konfirmasi
- [ ] UI sesuai Figma

## Acceptance Criteria
- [ ] User bisa ganti password dengan input password lama
- [ ] Toggle notifikasi tersimpan
- [ ] Hapus akun menonaktifkan (active=False)

## Custom Module: unitrade_auth
## Estimasi: 2.5 hari" \
"auth,frontend,backend,priority:medium" \
"Phase 2 - Auth & Profil"

create_issue 11 \
"F-09: Penghapusan Akun + Halaman Kebijakan Privasi" \
"## Deskripsi
Form pengajuan hapus akun dan halaman statis kebijakan privasi UniTrade.

## Odoo Native yang Dipakai
res.users (active=False), website (static page)

## Yang Perlu Dicustom
- [ ] Controller hapus akun: set active=False
- [ ] Form konfirmasi dengan input password
- [ ] Halaman statis /privacy-policy
- [ ] Konten kebijakan privasi UniTrade

## Acceptance Criteria
- [ ] Akun terhapus (nonaktif) setelah konfirmasi
- [ ] Halaman kebijakan privasi dapat diakses tanpa login

## Custom Module: unitrade_auth
## Estimasi: 1 hari" \
"auth,frontend,backend,priority:medium" \
"Phase 2 - Auth & Profil"

# ── PHASE 3: SELLER ───────────────────────────────────────────────────────────

create_issue 12 \
"F-11: Aktivasi Akun Penjual - model unitrade.seller + 1 tombol upgrade" \
"## Deskripsi
Mahasiswa upgrade akun jadi penjual dengan 1 tombol. Buat model unitrade.seller.

## Odoo Native yang Dipakai
res.users, res.groups — group management

## Yang Perlu Dicustom
- [ ] Model unitrade.seller: user_id, status, ktm_image, nim, rejection_reason
- [ ] Tombol Aktivasi Penjual di halaman profil
- [ ] Controller create seller record
- [ ] Assign user ke group Seller setelah verified

## Acceptance Criteria
- [ ] User klik tombol → record seller terbuat
- [ ] Status awal draft
- [ ] UNIQUE constraint user_id (1 user = 1 seller)

## Custom Module: unitrade_seller
## Estimasi: 2 hari" \
"seller,backend,priority:critical" \
"Phase 3 - Verifikasi Seller"

create_issue 13 \
"F-12: Verifikasi KTM - PaddleOCR + regex NIM + confidence check" \
"## Deskripsi
Verifikasi KTM otomatis menggunakan OCR dan regex validasi NIM UNISA.

## Odoo Native yang Dipakai
mail (notif), ir.attachment (simpan file)

## Yang Perlu Dicustom
- [ ] Form upload KTM (JPG/PNG, max 5MB)
- [ ] PaddleOCR pipeline: preprocessing → OCR → ekstraksi teks
- [ ] Regex NIM format UNISA
- [ ] Confidence check: cocokkan nama profil vs OCR (threshold 70%)
- [ ] Controller /unitrade/seller/verify-ktm

## Library Eksternal
\`\`\`bash
pip install paddleocr Pillow
\`\`\`

## Acceptance Criteria
- [ ] File KTM ter-upload dan tersimpan
- [ ] OCR berhasil ekstraksi teks
- [ ] NIM tervalidasi dengan regex
- [ ] Status berubah ke pending setelah upload

## Custom Module: unitrade_seller
## Estimasi: 3 hari" \
"seller,backend,ocr,priority:critical" \
"Phase 3 - Verifikasi Seller"

create_issue 14 \
"F-13: Status Verifikasi Penjual - approve/reject admin + notif email" \
"## Deskripsi
Status verifikasi: draft → pending → verified/rejected. Admin approve/reject dari backend.

## Odoo Native yang Dipakai
mail — email template dan notifikasi otomatis

## Yang Perlu Dicustom
- [ ] Backend view KTM untuk admin (XML form view)
- [ ] Tombol Approve dan Reject di form backend
- [ ] Field rejection_reason wajib saat reject
- [ ] Email template: approved & rejected
- [ ] Halaman status verifikasi di portal seller

## Acceptance Criteria
- [ ] Admin bisa lihat foto KTM + data OCR
- [ ] Admin approve → status verified, seller bisa listing
- [ ] Admin reject → wajib isi alasan → email terkirim
- [ ] User bisa lihat status dan alasan penolakan

## Custom Module: unitrade_seller
## Estimasi: 2 hari" \
"seller,backend,admin,priority:critical" \
"Phase 3 - Verifikasi Seller"

# ── PHASE 4: PRODUK ───────────────────────────────────────────────────────────

create_issue 15 \
"F-14: Halaman Detail Produk - slider gambar, badge kondisi, tombol chat & beli" \
"## Deskripsi
Override halaman detail produk dengan desain Figma: slider, badge kondisi baru/bekas, info penjual.

## Odoo Native yang Dipakai
website_sale — halaman /shop/{product} sudah ada

## Yang Perlu Dicustom
- [ ] Extend product.template: condition (baru/bekas), seller_id, location_city
- [ ] Slider multi-gambar dengan arrow navigation
- [ ] Badge kondisi Baru/Bekas
- [ ] Info lokasi penjual
- [ ] Tombol Chat (link ke im_livechat)
- [ ] Override template product_detail sesuai Figma

## Acceptance Criteria
- [ ] Gambar slider berfungsi
- [ ] Badge kondisi tampil
- [ ] Stok real-time tampil
- [ ] Tombol Chat membuka livechat

## Custom Module: unitrade_product
## Estimasi: 2 hari" \
"product,frontend,ui,priority:critical" \
"Phase 4 - Produk & Katalog"

create_issue 16 \
"F-15: Manajemen Keranjang - cek stok real-time sebelum checkout" \
"## Deskripsi
Keranjang belanja dengan pengecekan stok real-time.

## Odoo Native yang Dipakai
website_sale — add to cart, update qty, hapus item, kalkulasi total SUDAH ADA!

## Yang Perlu Dicustom
- [ ] Cek stok real-time sebelum lanjut checkout
- [ ] Alert jika stok tidak cukup
- [ ] Override template keranjang sesuai Figma

## Acceptance Criteria
- [ ] Add/update/hapus item di keranjang
- [ ] Total harga terhitung otomatis
- [ ] Error jika stok tidak cukup saat checkout

## Custom Module: unitrade_product
## Estimasi: 1 hari" \
"product,frontend,priority:critical" \
"Phase 4 - Produk & Katalog"

create_issue 17 \
"F-16/17: Sorting ulasan + Halaman profil toko penjual" \
"## Deskripsi
Sorting ulasan produk dan halaman profil toko penjual dengan statistik kinerja.

## Yang Perlu Dicustom
- [ ] Sort ulasan: terbaru, rating tertinggi, rating terendah
- [ ] Halaman /seller/{id} — profil toko
- [ ] Tampilkan: rating avg, jumlah terjual, produk aktif
- [ ] Tombol Chat di profil toko

## Acceptance Criteria
- [ ] Sort ulasan berfungsi
- [ ] Halaman profil toko accessible tanpa login

## Custom Module: unitrade_review, unitrade_seller
## Estimasi: 2 hari" \
"product,frontend,priority:medium" \
"Phase 4 - Produk & Katalog"

create_issue 18 \
"F-18: Pencarian & Filter Terpadu - tambah filter kondisi Baru/Bekas" \
"## Deskripsi
Extend filter pencarian Odoo dengan filter Kondisi produk.

## Odoo Native yang Dipakai
website_sale — search, filter kategori, filter harga SUDAH ADA!

## Yang Perlu Dicustom
- [ ] Tambah filter Kondisi (Radio: Baru/Bekas)
- [ ] Styling sidebar filter sesuai Figma
- [ ] URL parameter untuk kondisi filter

## Acceptance Criteria
- [ ] Filter kondisi berfungsi dan update hasil
- [ ] Filter bisa dikombinasikan

## Custom Module: unitrade_product
## Estimasi: 1.5 hari" \
"product,frontend,priority:critical" \
"Phase 4 - Produk & Katalog"

create_issue 19 \
"F-19: Sortir Produk Dinamis - tambah sort Populer by sales_count" \
"## Deskripsi
Tambahkan opsi sort Populer berdasarkan sales_count.

## Odoo Native yang Dipakai
website_sale — sort by price & newest sudah ada

## Yang Perlu Dicustom
- [ ] Tambah opsi sort Populer (order by sales_count DESC)
- [ ] Dropdown sort sesuai Figma (4 opsi: Terbaru, Termurah, Termahal, Populer)

## Acceptance Criteria
- [ ] 4 opsi sort tersedia dan berfungsi

## Custom Module: unitrade_product
## Estimasi: 0.5 hari" \
"product,frontend,priority:medium" \
"Phase 4 - Produk & Katalog"

create_issue 20 \
"F-20: Rekomendasi Produk - kategori sama + riwayat session" \
"## Deskripsi
Blok rekomendasi produk di halaman detail. Logic: kategori sama + riwayat session.

## Odoo Native yang Dipakai
website_sale — Alternative Products sudah ada!

## Yang Perlu Dicustom
- [ ] Logic: prioritaskan kategori sama
- [ ] Fallback: riwayat session user
- [ ] Blok UI rekomendasi (horizontal scroll cards)

## Acceptance Criteria
- [ ] Minimal 4 produk rekomendasi tampil
- [ ] Produk kategori sama diprioritaskan

## Custom Module: unitrade_product
## Estimasi: 1 hari" \
"product,frontend,priority:medium" \
"Phase 4 - Produk & Katalog"

# ── PHASE 5: TRANSAKSI ────────────────────────────────────────────────────────

create_issue 21 \
"F-21: Chat Real-Time - im_livechat + simpan product_id di channel" \
"## Deskripsi
Chat real-time buyer-seller. Extend discuss.channel dengan product_id.

## Odoo Native yang Dipakai
im_livechat — chat window, history, notifikasi SUDAH ADA!

## Yang Perlu Dicustom
- [ ] Extend discuss.channel: tambah field product_id FK
- [ ] Tombol Chat di halaman produk membuka channel dengan konteks produk
- [ ] Badge nama produk di window chat
- [ ] Seller bisa lihat produk mana yang ditanyakan

## Acceptance Criteria
- [ ] Chat terbuka dari halaman produk
- [ ] Channel tersimpan dengan product_id
- [ ] History chat persisten

## Custom Module: unitrade_chat
## Estimasi: 2 hari" \
"chat,backend,frontend,priority:critical" \
"Phase 5 - Transaksi & Komunikasi"

create_issue 22 \
"F-22: Payment Gateway - Midtrans/Xendit Snap + webhook + Account Move otomatis" \
"## Deskripsi
Integrasi payment gateway. Odoo payment module menyediakan framework.

## Odoo Native yang Dipakai
payment, account — framework provider & Account Move otomatis

## Yang Perlu Dicustom
- [ ] Custom payment provider (Midtrans direkomendasikan)
- [ ] Controller webhook /unitrade/payment/webhook
- [ ] Verifikasi signature webhook
- [ ] Update status order setelah payment callback
- [ ] Halaman checkout + konfirmasi pembayaran sesuai Figma

## Catatan
Midtrans lebih mudah dari Xendit karena ada referensi modul komunitas Odoo.

## Acceptance Criteria
- [ ] Pembayaran berhasil diproses
- [ ] Webhook mengupdate status order
- [ ] Invoice/Account Move terbuat otomatis

## Custom Module: unitrade_payment
## Estimasi: 3 hari" \
"payment,backend,priority:critical" \
"Phase 5 - Transaksi & Komunikasi"

create_issue 23 \
"F-23: Status Transaksi - label Bahasa Indonesia + progress bar timeline" \
"## Deskripsi
Tampilan status transaksi dengan label Indonesia dan progress bar visual.

## Odoo Native yang Dipakai
sale, portal — status order & /my/orders sudah ada

## Yang Perlu Dicustom
- [ ] Label status: Menunggu Bayar, Sedang Dikemas, Dikirim, Selesai, Dibatalkan
- [ ] Progress bar / timeline visual
- [ ] Badge warna per status

## Custom Module: unitrade_theme
## Estimasi: 1 hari" \
"frontend,ui,priority:high" \
"Phase 5 - Transaksi & Komunikasi"

create_issue 24 \
"F-24: Integrasi GoSend API - kalkulasi ongkir + booking pengiriman" \
"## Deskripsi
Integrasi GoSend untuk kalkulasi ongkir berdasarkan koordinat GPS dan booking pengiriman.

## Odoo Native yang Dipakai
delivery, stock — framework delivery carrier & stock.picking

## Yang Perlu Dicustom
- [ ] utils/gosend_api.py: wrapper GoSend API
- [ ] Kalkulasi ongkir berdasarkan lat/lng origin & destination
- [ ] Ambil berat dari product.template
- [ ] Simpan booking_id di dokumen pengiriman
- [ ] Halaman pilih pengiriman di checkout

## Acceptance Criteria
- [ ] Ongkir terhitung berdasarkan lokasi
- [ ] Order GoSend berhasil dibuat
- [ ] booking_id tersimpan di database

## Custom Module: unitrade_delivery
## Estimasi: 3 hari" \
"delivery,backend,priority:critical" \
"Phase 5 - Transaksi & Komunikasi"

create_issue 25 \
"F-25: Status Pengiriman Real-time - webhook GoSend + nomor resi tracking" \
"## Deskripsi
Sinkronisasi status pengiriman real-time dari GoSend via webhook.

## Yang Perlu Dicustom
- [ ] Webhook controller /unitrade/delivery/webhook
- [ ] Update status pengiriman di unitrade.delivery
- [ ] Timeline tracking di halaman Pesanan Saya
- [ ] Nomor resi sebagai link ke GoSend tracking

## Acceptance Criteria
- [ ] Status pengiriman update real-time via webhook
- [ ] Nomor resi tampil dan bisa diklik

## Custom Module: unitrade_delivery
## Estimasi: 2 hari" \
"delivery,backend,frontend,priority:high" \
"Phase 5 - Transaksi & Komunikasi"

# ── PHASE 6: NOTIFIKASI ───────────────────────────────────────────────────────

create_issue 26 \
"F-26: Notifikasi Sistem - in-app bell icon + email otomatis" \
"## Deskripsi
Sistem notifikasi untuk: chat masuk, status pesanan, pembayaran, pengiriman.

## Odoo Native yang Dipakai
mail — mail.message, mail.notification, bus real-time SUDAH ADA!

## Yang Perlu Dicustom
- [ ] Trigger notif di setiap event UniTrade
- [ ] Bell icon notification dropdown di navbar
- [ ] Badge counter unread notifications
- [ ] UI notifikasi sesuai Figma

## 5 Jenis Notifikasi
1. Chat masuk dari buyer/seller
2. Status pesanan berubah
3. Pembayaran berhasil/gagal
4. Update status pengiriman
5. Verifikasi seller approved/rejected

## Custom Module: extend di unitrade_seller, unitrade_payment, unitrade_delivery
## Estimasi: 1.5 hari" \
"notification,frontend,backend,priority:high" \
"Phase 6 - Notifikasi"

create_issue 27 \
"F-27: Pengaturan Notifikasi - toggle per jenis notifikasi" \
"## Deskripsi
Halaman pengaturan notifikasi: user bisa aktif/nonaktifkan per jenis notifikasi.

## Yang Perlu Dicustom
- [ ] Model unitrade.notif.preference (One2one dengan res.users)
- [ ] Toggle switch per jenis notif di halaman pengaturan
- [ ] Simpan preferensi ke database

## 5 Jenis Notifikasi
1. Chat masuk
2. Status pesanan berubah
3. Pembayaran
4. Pengiriman
5. Promo & informasi

## Custom Module: unitrade_auth
## Estimasi: 1 hari" \
"notification,frontend,priority:medium" \
"Phase 6 - Notifikasi"

# ── PHASE 7: DASHBOARD SELLER ─────────────────────────────────────────────────

create_issue 28 \
"F-28: Dashboard Penjual - statistik visual + grafik penjualan Chart.js" \
"## Deskripsi
Dashboard penjual dengan kartu statistik dan grafik penjualan menggunakan Chart.js.

## Odoo Native yang Dipakai
sale, account, portal — data sudah ada di database

## Yang Perlu Dicustom
- [ ] Computed field: total revenue, total orders, total products
- [ ] Controller /my/seller/dashboard dengan data JSON
- [ ] Grafik Chart.js: penjualan mingguan & bulanan
- [ ] Kartu statistik: Revenue, Orders, Products, Rating
- [ ] Layout dashboard sesuai Figma

## Acceptance Criteria
- [ ] Dashboard tampil data real seller yang login
- [ ] Grafik update berdasarkan data transaksi
- [ ] Responsive di mobile

## Custom Module: unitrade_seller
## Estimasi: 3 hari" \
"seller,frontend,backend,priority:critical" \
"Phase 7 - Dashboard Seller"

create_issue 29 \
"F-29: Manajemen Pesanan Penjual - terima/tolak + update status" \
"## Deskripsi
Halaman daftar pesanan masuk untuk penjual. Bisa terima/tolak dan update status.

## Odoo Native yang Dipakai
sale, portal — data sale.order sudah ada

## Yang Perlu Dicustom
- [ ] Filter sale.order by seller_id
- [ ] Tombol Terima/Tolak pesanan
- [ ] Update status: Diproses → Siap Dikirim
- [ ] Notifikasi ke buyer saat status berubah
- [ ] Halaman pesanan masuk sesuai Figma

## Acceptance Criteria
- [ ] Hanya pesanan milik seller yang tampil
- [ ] Seller bisa update status pesanan

## Custom Module: unitrade_seller
## Estimasi: 2 hari" \
"seller,frontend,backend,priority:critical" \
"Phase 7 - Dashboard Seller"

create_issue 30 \
"F-31: Manajemen Produk Penjual - CRUD produk di portal frontend" \
"## Deskripsi
Form CRUD produk di frontend portal seller. Seller bisa tambah/edit/hapus produk dari website.

## Odoo Native yang Dipakai
website_sale, stock — model product sudah ada

## Yang Perlu Dicustom
- [ ] Halaman /my/seller/products — list produk seller
- [ ] Form tambah produk: nama, harga, stok, deskripsi, kondisi, multi-foto
- [ ] Form edit produk
- [ ] Konfirmasi hapus produk
- [ ] Upload multi-foto produk

## Acceptance Criteria
- [ ] Seller bisa CRUD produk dari frontend
- [ ] Produk tersinkron dengan modul Inventory
- [ ] Multi-foto ter-upload

## Custom Module: unitrade_seller, unitrade_product
## Estimasi: 2 hari" \
"seller,frontend,backend,priority:critical" \
"Phase 7 - Dashboard Seller"

create_issue 31 \
"F-32: Management Chat Penjual - inbox chat per produk di dashboard seller" \
"## Deskripsi
Inbox khusus penjual untuk merespon chat pembeli, terfilter per produk.

## Odoo Native yang Dipakai
im_livechat, discuss

## Yang Perlu Dicustom
- [ ] List percakapan di dashboard seller
- [ ] Filter percakapan by produk
- [ ] Quick reply interface

## Custom Module: unitrade_chat
## Estimasi: 1.5 hari" \
"seller,chat,frontend,priority:high" \
"Phase 7 - Dashboard Seller"

create_issue 32 \
"F-33: Penghasilan & Settlement - rincian pendapatan + pengajuan pencairan" \
"## Deskripsi
Halaman penghasilan penjual: total pendapatan, rincian per transaksi, pengajuan pencairan.

## Odoo Native yang Dipakai
account — data invoice & payment sudah tercatat

## Yang Perlu Dicustom
- [ ] Model unitrade.settlement untuk pencairan
- [ ] Halaman pendapatan: total bersih, rincian per order
- [ ] Form pengajuan pencairan dana
- [ ] Status pencairan: pending/processed/done

## Custom Module: unitrade_seller
## Estimasi: 2 hari" \
"seller,backend,priority:medium" \
"Phase 7 - Dashboard Seller"

create_issue 33 \
"F-34: Pengaturan Toko - nama toko, deskripsi, alamat pickup, foto banner" \
"## Deskripsi
Halaman pengaturan profil toko penjual.

## Yang Perlu Dicustom
- [ ] Form edit profil toko di portal seller
- [ ] Field: nama toko, deskripsi, alamat pickup, no kontak
- [ ] Upload foto banner toko

## Custom Module: unitrade_seller
## Estimasi: 1 hari" \
"seller,frontend,priority:medium" \
"Phase 7 - Dashboard Seller"

# ── PHASE 8: ADMIN ────────────────────────────────────────────────────────────

create_issue 34 \
"F-35: Dashboard Admin - GMV harian, total user, penjual, grafik transaksi" \
"## Deskripsi
Custom dashboard admin di backend Odoo dengan visualisasi data platform.

## Odoo Native yang Dipakai
sale, account — data sudah ada

## Yang Perlu Dicustom
- [ ] Custom menu UniTrade Dashboard di backend
- [ ] Kartu: Total User, Penjual Verified, GMV Harian, Laporan Masuk
- [ ] Grafik transaksi harian/mingguan
- [ ] Computed field GMV

## Custom Module: unitrade_admin
## Estimasi: 2 hari" \
"admin,backend,priority:high" \
"Phase 8 - Dashboard Admin"

create_issue 35 \
"F-36: Manajemen Pengguna Admin - moderasi KTM + pembekuan akun" \
"## Deskripsi
Admin kelola semua user: lihat, edit, nonaktifkan, dan moderasi verifikasi KTM penjual.

## Odoo Native yang Dipakai
res.users backend view sudah powerful!

## Yang Perlu Dicustom
- [ ] Custom list view seller dengan status verifikasi
- [ ] Form view KTM: foto KTM + hasil OCR + data NIM
- [ ] Tombol Approve/Reject dengan dialog alasan
- [ ] Action pembekuan akun (active=False)

## Custom Module: unitrade_seller (backend view)
## Estimasi: 1 hari" \
"admin,backend,priority:high" \
"Phase 8 - Dashboard Admin"

create_issue 36 \
"F-37/38: Reports pengaduan + Monitoring transaksi admin" \
"## Deskripsi
Menu laporan pengaduan dan monitoring semua transaksi platform.

## Odoo Native yang Dipakai
helpdesk (pengaduan), sale + account (transaksi) — sudah powerful!

## Yang Perlu Dicustom
- [ ] Tag helpdesk untuk kategori laporan UniTrade
- [ ] Custom filter transaksi UniTrade
- [ ] Dashboard laporan pengaduan

## Custom Module: unitrade_admin
## Estimasi: 1.5 hari" \
"admin,backend,priority:medium" \
"Phase 8 - Dashboard Admin"

create_issue 37 \
"F-39: Pengaturan Sistem Admin - API keys Midtrans, GoSend, Google Places" \
"## Deskripsi
Halaman pengaturan global: simpan API key pihak ketiga, manage kebijakan platform.

## Odoo Native yang Dipakai
ir.config_parameter — key-value config

## Yang Perlu Dicustom
- [ ] Form pengaturan UniTrade di backend
- [ ] Field: Midtrans API key, GoSend API key, Google Places API key
- [ ] Halaman kebijakan platform (editable)

## Custom Module: unitrade_admin
## Estimasi: 1 hari" \
"admin,backend,priority:medium" \
"Phase 8 - Dashboard Admin"

# ── PHASE 9: LOKASI & BANTUAN ─────────────────────────────────────────────────

create_issue 38 \
"F-40: Deteksi Lokasi GPS + Google Places autocomplete koordinat" \
"## Deskripsi
Deteksi lokasi user via GPS browser dan input alamat dengan Google Places autocomplete.

## Yang Perlu Dicustom
- [ ] JS: navigator.geolocation.getCurrentPosition()
- [ ] Google Places API autocomplete input alamat
- [ ] Simpan koordinat lat/lng ke user session
- [ ] Tampil di form checkout dan form profil

## Acceptance Criteria
- [ ] Tombol Deteksi Lokasi berfungsi
- [ ] Autocomplete alamat muncul saat mengetik
- [ ] Koordinat tersimpan untuk kalkulasi GoSend

## Custom Module: unitrade_product (static JS)
## Estimasi: 1.5 hari" \
"location,frontend,priority:high" \
"Phase 9 - Lokasi & Bantuan"

create_issue 39 \
"F-10/F-41: Rating & Ulasan - bintang 1-5 + form ulasan + moderasi admin" \
"## Deskripsi
Sistem rating dan ulasan. Hanya aktif jika pesanan berstatus Done. Admin bisa moderasi.

## Odoo Native yang Dipakai
rating — model rating.rating SUDAH ADA!

## Yang Perlu Dicustom
- [ ] Form ulasan: hanya muncul di order dengan status done
- [ ] Komponen bintang rating (1-5) interaktif
- [ ] Tampil ulasan di halaman produk + profil penjual
- [ ] Sort ulasan: terbaru, tertinggi, terendah
- [ ] Backend admin: moderasi/hapus ulasan

## Acceptance Criteria
- [ ] Form ulasan hanya muncul di order selesai
- [ ] Rating tersimpan dan mempengaruhi avg_rating
- [ ] Admin bisa hapus ulasan dari backend

## Custom Module: unitrade_review
## Estimasi: 2 hari" \
"review,frontend,backend,priority:high" \
"Phase 9 - Lokasi & Bantuan"

create_issue 40 \
"F-42: FAQ & Panduan - halaman accordion per kategori bantuan" \
"## Deskripsi
Halaman FAQ statis dengan accordion per kategori untuk panduan pembeli dan penjual.

## Odoo Native yang Dipakai
website — static page CMS

## Yang Perlu Dicustom
- [ ] Halaman /faq dengan layout accordion
- [ ] Kategori: Cara Beli, Cara Jual, Pembayaran, Pengiriman, Akun
- [ ] Konten FAQ diisi

## Custom Module: unitrade_theme
## Estimasi: 1 hari" \
"frontend,ui,priority:low" \
"Phase 9 - Lokasi & Bantuan"

create_issue 41 \
"F-43: Formulir Bantuan → Helpdesk Ticket otomatis" \
"## Deskripsi
Form bantuan di frontend yang otomatis membuat tiket helpdesk di backend admin.

## Odoo Native yang Dipakai
helpdesk — FULLY FUNCTIONAL! Form → ticket dashboard sudah ada

## Yang Perlu Dicustom
- [ ] Override styling form bantuan sesuai Figma
- [ ] Pilihan kategori masalah UniTrade

## Acceptance Criteria
- [ ] User submit form → tiket terbuat di helpdesk admin
- [ ] User dapat konfirmasi email tiket diterima

## Custom Module: unitrade_theme
## Estimasi: 0.5 hari" \
"frontend,ui,priority:low" \
"Phase 9 - Lokasi & Bantuan"

# ── PHASE 10: QA & DEPLOY ─────────────────────────────────────────────────────

create_issue 42 \
"QA-01: Security Testing - SQL injection, XSS, CSRF, role-based access" \
"## Deskripsi
Pengujian keamanan menyeluruh sebelum production deploy.

## Checklist
- [ ] SQL Injection test di semua input form
- [ ] XSS test di field teks (ulasan, deskripsi produk)
- [ ] CSRF token tervalidasi di semua POST request
- [ ] Role-based access: guest tidak bisa akses halaman seller/buyer
- [ ] Seller tidak bisa akses data seller lain
- [ ] Admin endpoint tidak accessible tanpa login admin

## Tools
- OWASP ZAP atau Burp Suite
- Manual testing per endpoint

## Estimasi: 2 hari" \
"qa,security,priority:critical" \
"Phase 10 - QA & Deploy"

create_issue 43 \
"QA-02: Performance Testing - 100 concurrent users + query optimization" \
"## Deskripsi
Test performa sistem dengan 100 user bersamaan. Response time target <= 3 detik.

## Checklist
- [ ] Load test dengan Apache JMeter / Locust
- [ ] Response time homepage <= 3 detik
- [ ] Response time search produk <= 3 detik
- [ ] Response time checkout <= 3 detik
- [ ] Identifikasi query N+1 dan optimasi
- [ ] Tambah index database jika diperlukan

## Estimasi: 1.5 hari" \
"qa,performance,priority:high" \
"Phase 10 - QA & Deploy"

create_issue 44 \
"QA-03: UAT - User Acceptance Testing dengan mahasiswa UNISA" \
"## Deskripsi
User Acceptance Testing dengan minimal 5 mahasiswa UNISA sebagai real user.

## Skenario Test
- [ ] Registrasi → OTP → Login
- [ ] Cari produk → filter → beli → bayar
- [ ] Daftar seller → upload KTM → listing produk
- [ ] Chat dengan seller
- [ ] Review setelah transaksi selesai

## Acceptance Criteria
- [ ] Tidak ada critical bug saat UAT
- [ ] Semua skenario utama berhasil dijalankan user
- [ ] Feedback user didokumentasikan

## Estimasi: 2 hari" \
"qa,uat,priority:critical" \
"Phase 10 - QA & Deploy"

create_issue 45 \
"DEPLOY-01: Production Deploy - Nginx + SSL Let's Encrypt + systemd service" \
"## Deskripsi
Deploy UniTrade ke server production dengan Nginx reverse proxy, SSL, dan systemd.

## Checklist
- [ ] Setup VPS Ubuntu 22.04 (min 4GB RAM, 2 CPU, 50GB SSD)
- [ ] Install Nginx + certbot
- [ ] Konfigurasi Nginx reverse proxy ke port 8069
- [ ] SSL Let's Encrypt untuk domain
- [ ] Setup systemd service odoo17
- [ ] Tutup port 8069 dari publik (hanya Nginx)
- [ ] Setup cron backup PostgreSQL harian
- [ ] Test semua fitur di production

## Nginx Config
\`\`\`nginx
server {
    listen 443 ssl;
    server_name unitrade.com;

    ssl_certificate /etc/letsencrypt/live/unitrade.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/unitrade.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8069;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
\`\`\`

## Acceptance Criteria
- [ ] Akses via HTTPS dengan SSL valid
- [ ] Odoo auto-restart jika crash (systemd)
- [ ] Backup berjalan otomatis tiap malam

## Estimasi: 1 hari" \
"deploy,devops,priority:critical" \
"Phase 10 - QA & Deploy"

# ══════════════════════════════════════════════════════════
# SELESAI
# ══════════════════════════════════════════════════════════
echo ""
echo "======================================================"
echo "  ✅ SELESAI!"
echo "======================================================"
echo ""
echo "  📋 45 Issues berhasil dibuat"
echo "  🏷️  25 Labels terbuat"
echo "  🎯 10 Milestones terbuat"
echo ""
echo "  Buka GitHub Projects kamu:"
echo "  https://github.com/$REPO/issues"
echo ""
echo "  Lalu tambahkan issues ke Project:"
echo "  1. Buka GitHub Projects"
echo "  2. Klik '+' → ketik '#' → pilih semua issues"
echo "======================================================"
