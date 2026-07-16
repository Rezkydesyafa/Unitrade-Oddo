from odoo import http
from odoo.http import request


FAQ_ITEMS = [
    {
        "id": "what-is-unitrade",
        "question": "Apa itu UniTrade?",
        "answer": (
            "UniTrade adalah platform marketplace yang ditujukan untuk mahasiswa dalam melakukan jual beli "
            "produk dan jasa. Melalui UniTrade, mahasiswa dapat menjual kebutuhan akademik, barang bekas "
            "layak pakai, maupun jasa, dengan sistem yang terstruktur, transparan, dan mudah digunakan. "
            "Fitur verifikasi penjual mahasiswa juga disediakan untuk meningkatkan keamanan dan kepercayaan "
            "dalam transaksi."
        ),
    },
    {
        "id": "ktm-verification",
        "question": "Kenapa saya wajib verifikasi KTM untuk jualan?",
        "answer": (
            "Verifikasi KTM diperlukan untuk memastikan bahwa penjual adalah mahasiswa aktif. Ini membantu "
            "menjaga keamanan dan kepercayaan antar pengguna. Data KTM hanya digunakan untuk verifikasi dan "
            "tidak ditampilkan ke publik."
        ),
    },
    {
        "id": "privacy",
        "question": "Data pribadi saya aman? Siapa yang bisa lihat alamat saya?",
        "answer": (
            "Kami melindungi data pribadi kamu. Nomor HP dan alamat hanya akan dibagikan kepada pihak "
            "terkait setelah transaksi dikonfirmasi atau dibayar, sehingga mengurangi risiko penyalahgunaan data."
        ),
    },
    {
        "id": "dispute",
        "question": "Bagaimana kalau saya tertipu atau barang tidak sesuai?",
        "answer": (
            "Dana akan ditahan sementara oleh sistem hingga transaksi selesai. Jika terjadi masalah, laporkan "
            "melalui Helpdesk maksimal 2x24 jam setelah barang diterima."
        ),
    },
    {
        "id": "payment-methods",
        "question": "Metode pembayaran apa saja yang tersedia?",
        "answer": (
            "Semua pembayaran diproses otomatis melalui Midtrans dan mendukung QRIS, e-wallet, serta Virtual "
            "Account. Tidak perlu upload bukti transfer manual."
        ),
    },
    {
        "id": "become-seller",
        "question": "Bagaimana cara menjadi penjual di UniTrade?",
        "answer": (
            "Pengguna dapat mengajukan aktivasi akun penjual melalui menu Daftar sebagai Penjual, lalu "
            "mengunggah KTM untuk verifikasi. Setelah disetujui admin, akun akan aktif sebagai penjual dan "
            "siap digunakan untuk menjual produk atau jasa."
        ),
    },
    {
        "id": "transaction-escrow",
        "question": "Bagaimana mekanisme transaksi dan perlindungan dana di UniTrade?",
        "answer": (
            "Semua transaksi dalam UniTrade menggunakan mekanisme Escrow internal. Saat pembeli melakukan pembayaran, dana tidak langsung diteruskan kepada penjual, melainkan ditahan dalam sistem escrow. Dana baru akan dilepaskan kepada penjual setelah status pesanan berubah menjadi 'Selesai' atau 'Dikonfirmasi Selesai' oleh sistem, atau mengikuti kebijakan khusus yang berlaku saat itu. Mekanisme ini bertujuan melindungi kedua belah pihak: pembeli mendapatkan jaminan bahwa penjual hanya akan menerima dana setelah pesanan selesai, sementara penjual mendapatkan kepastian bahwa pembayaran telah diverifikasi dan diamankan oleh sistem."
        ),
    },
]


POLICY_SECTIONS = [
    {
        "id": "general",
        "title": "Ketentuan Umum",
        "paragraphs": [
            "UniTrade adalah marketplace C2C berbasis Odoo 17 untuk mempertemukan pengguna yang ingin membeli "
            "dan menjual produk atau jasa dalam lingkungan kampus. Dengan mendaftar, login, membeli, menjual, "
            "mengirim pesan, atau menggunakan fitur lain di UniTrade, pengguna dianggap telah membaca dan "
            "menyetujui syarat layanan serta kebijakan privasi ini.",
            "UniTrade berperan sebagai penyedia platform. Penjual dan pembeli tetap bertanggung jawab atas "
            "akurasi informasi, kualitas barang atau jasa, komunikasi, dan pemenuhan kewajiban transaksi masing-masing.",
        ],
    },
    {
        "id": "accounts",
        "title": "Akun, Login, dan OTP",
        "items": [
            "Pengguna wajib memakai data akun yang valid, termasuk nama, email, nomor WhatsApp atau nomor kontak, dan password yang aman.",
            "Sistem dapat menggunakan OTP untuk memverifikasi registrasi, login, aktivasi penjual, atau perubahan data penting.",
            "Pengguna bertanggung jawab menjaga kerahasiaan password, OTP, perangkat, dan sesi login miliknya.",
            "UniTrade dapat membatasi, mengunci sementara, atau meninjau akun jika terdeteksi percobaan login berulang, pola spam, penyalahgunaan, atau aktivitas tidak wajar.",
            "Pengguna dilarang memakai identitas orang lain, membuat akun untuk tujuan penipuan, atau memindahkan akun tanpa izin pemilik sah.",
        ],
    },
    {
        "id": "personal-data",
        "title": "Data yang Dikumpulkan",
        "paragraphs": [
            "UniTrade mengumpulkan data yang diperlukan agar marketplace dapat berjalan aman, terukur, dan dapat diaudit. Data tersebut dapat berasal dari input pengguna, aktivitas transaksi, proses verifikasi, serta integrasi layanan pendukung.",
        ],
        "items": [
            "Data profil: nama, email, nomor kontak, foto profil, alamat, kota, provinsi, dan preferensi akun.",
            "Data penjual: nama toko, deskripsi toko, alamat pickup, koordinat lokasi, rekening atau channel payout, dan status toko.",
            "Data verifikasi: foto KTM, universitas yang dipilih, NIM yang terbaca, hasil OCR, confidence score, catatan review admin, dan status verifikasi.",
            "Data produk: nama produk, kategori, harga, stok, kondisi, deskripsi, foto, lokasi, dan status listing.",
            "Data transaksi: keranjang, wishlist, order, pembayaran, pengiriman, refund, dispute, ulasan, dan riwayat status pesanan.",
            "Data teknis: alamat IP, user agent, waktu akses, log keamanan, riwayat persetujuan syarat dan privasi, serta aktivitas sistem yang relevan.",
        ],
    },
    {
        "id": "data-purpose",
        "title": "Tujuan Penggunaan Data",
        "items": [
            "Membuat dan mengamankan akun pengguna.",
            "Memproses OTP, login, pendaftaran, dan perubahan informasi akun.",
            "Memverifikasi penjual melalui KTM, OCR, dan review admin.",
            "Menampilkan produk, profil toko, rating, wishlist, chat, dan informasi transaksi.",
            "Memproses pembayaran, escrow internal, pengiriman, pembatalan, refund, dan dispute.",
            "Mengirim notifikasi terkait chat, pembayaran, pesanan, pengiriman, ulasan, dan status verifikasi.",
            "Mencegah penipuan, spam, duplikasi NIM, penyalahgunaan chat, dan pelanggaran kebijakan.",
            "Membuat laporan operasional, audit admin, dan peningkatan kualitas layanan.",
        ],
    },
    {
        "id": "seller-verification",
        "title": "Verifikasi Penjual, KTM, dan OCR",
        "paragraphs": [
            "Pengguna yang ingin menjadi penjual wajib melalui proses verifikasi. UniTrade dapat meminta foto KTM atau bukti identitas mahasiswa untuk memastikan akun penjual sesuai dengan konteks marketplace kampus.",
        ],
        "items": [
            "Foto KTM digunakan untuk membaca NIM, nama, universitas, dan indikator validitas lain melalui OCR serta review admin.",
            "Data KTM tidak ditampilkan ke publik dan hanya digunakan untuk verifikasi, audit keamanan, dan penyelesaian sengketa yang relevan.",
            "UniTrade dapat menolak pengajuan jika foto tidak jelas, data tidak cocok, NIM sudah digunakan, atau terdapat indikasi penyalahgunaan.",
            "Admin dapat melakukan review manual jika hasil OCR rendah, nama kurang terbaca, atau verifikasi otomatis belum memadai.",
            "Status penjual dapat dicabut jika kemudian ditemukan pelanggaran, data palsu, laporan serius, atau aktivitas yang merugikan pengguna lain.",
        ],
    },
    {
        "id": "products",
        "title": "Produk, Jasa, dan Listing",
        "items": [
            "Penjual wajib memastikan foto, deskripsi, harga, kondisi, stok, dan kategori produk sesuai dengan keadaan sebenarnya.",
            "Produk yang dilarang meliputi barang ilegal, berbahaya, palsu, melanggar hak cipta, mengandung unsur diskriminatif, atau tidak sesuai hukum yang berlaku.",
            "UniTrade dapat menurunkan, menyembunyikan, menolak, atau menghapus listing yang melanggar ketentuan atau menerima laporan valid.",
            "Penjual bertanggung jawab memperbarui stok, menyiapkan pesanan, dan menanggapi pembeli dengan informasi yang benar.",
            "Listing fee, masa aktif listing, atau aturan monetisasi lain dapat diterapkan sesuai konfigurasi platform yang berlaku.",
        ],
    },
    {
        "id": "transactions",
        "title": "Transaksi, Pembayaran, dan Escrow",
        "items": [
            "Transaksi sebaiknya dilakukan melalui sistem UniTrade agar status order, pembayaran, pengiriman, refund, dan dispute dapat dicatat.",
            "Pembayaran dapat diproses melalui Midtrans atau penyedia pembayaran lain yang dikonfigurasi oleh UniTrade, seperti QRIS, e-wallet, virtual account, atau metode yang tersedia.",
            "UniTrade dapat menahan dana secara internal sampai transaksi selesai, dibatalkan, atau masuk proses dispute sesuai status order.",
            "Pembeli wajib memeriksa ringkasan pesanan, biaya layanan, ongkir, voucher, dan total pembayaran sebelum menyelesaikan checkout.",
            "Penjual wajib memproses pesanan sesuai batas waktu dan informasi yang disepakati di sistem.",
            "Kesepakatan pembayaran di luar sistem menjadi risiko pengguna sendiri dan tidak selalu dapat dibantu oleh UniTrade.",
        ],
    },
    {
        "id": "delivery",
        "title": "Pengiriman dan COD",
        "items": [
            "Pengiriman dapat memakai kurir, pickup, atau metode serah terima yang tersedia di platform.",
            "Alamat, titik koordinat, nomor kontak, dan catatan pengiriman hanya digunakan untuk menyelesaikan transaksi dan koordinasi pengiriman.",
            "Pembeli wajib memberikan alamat yang akurat dan dapat dihubungi saat pengiriman berlangsung.",
            "Penjual wajib mengemas barang dengan layak dan menyerahkan barang sesuai detail pesanan.",
            "Risiko akibat alamat salah, pembeli tidak dapat dihubungi, atau kesepakatan pengiriman di luar sistem menjadi tanggung jawab pihak yang terkait.",
        ],
    },
    {
        "id": "chat-notifications",
        "title": "Chat, Notifikasi, dan Komunikasi",
        "items": [
            "Fitur chat digunakan untuk komunikasi yang relevan dengan produk, toko, dan transaksi.",
            "Pengguna dilarang mengirim spam, penipuan, link berbahaya, konten pornografi, ujaran kebencian, ancaman, atau data pribadi orang lain tanpa izin.",
            "UniTrade dapat menyimpan riwayat chat untuk kebutuhan operasional, keamanan, moderasi laporan, dan penyelesaian sengketa.",
            "Notifikasi dapat dikirim untuk aktivitas penting seperti chat masuk, status pesanan, pembayaran, refund, dispute, verifikasi seller, dan pengumuman sistem.",
            "Admin dapat meninjau laporan chat jika ada dugaan pelanggaran kebijakan atau sengketa transaksi.",
        ],
    },
    {
        "id": "reviews-disputes",
        "title": "Ulasan, Refund, dan Sengketa",
        "items": [
            "Ulasan hanya boleh diberikan berdasarkan pengalaman transaksi yang benar-benar terjadi.",
            "Ulasan yang mengandung fitnah, diskriminasi, pelecehan, spam, atau informasi pribadi dapat disembunyikan atau dihapus.",
            "Pembeli dapat mengajukan refund atau dispute sesuai alur dan batas waktu yang berlaku pada status transaksi.",
            "Bukti pendukung seperti foto, keterangan masalah, chat, dan riwayat order dapat digunakan admin untuk menilai sengketa.",
            "Keputusan penyelesaian sengketa mempertimbangkan bukti, status pembayaran, status pengiriman, respons penjual, dan riwayat transaksi.",
        ],
    },
    {
        "id": "sharing",
        "title": "Pembagian Data kepada Pihak Terkait",
        "paragraphs": [
            "UniTrade tidak menjual data pribadi pengguna. Data dapat dibagikan secara terbatas hanya jika diperlukan untuk menjalankan layanan, memenuhi kewajiban hukum, atau menyelesaikan transaksi dan sengketa.",
        ],
        "items": [
            "Kepada penjual atau pembeli terkait untuk kebutuhan transaksi, pengiriman, chat, dan konfirmasi pesanan.",
            "Kepada penyedia pembayaran seperti Midtrans untuk memproses pembayaran dan status transaksi.",
            "Kepada penyedia pengiriman atau kurir terkait untuk menghitung ongkir, pickup, dan pengantaran.",
            "Kepada admin UniTrade untuk verifikasi, moderasi, customer service, audit, refund, dispute, dan keamanan platform.",
            "Kepada pihak berwenang jika diwajibkan oleh hukum atau diperlukan untuk menanggapi dugaan penyalahgunaan serius.",
        ],
    },
    {
        "id": "security-retention",
        "title": "Keamanan, Penyimpanan, dan Retensi Data",
        "items": [
            "UniTrade menerapkan kontrol akses berbasis role, validasi form, pencatatan aktivitas penting, dan pembatasan akses data sesuai kebutuhan operasional.",
            "Data sensitif seperti KTM, hasil OCR, payout, log keamanan, dan catatan sengketa hanya dapat diakses oleh pihak yang memiliki kewenangan.",
            "Data transaksi dan audit dapat tetap disimpan setelah akun dinonaktifkan untuk kepentingan pembukuan, keamanan, dispute, dan kepatuhan.",
            "Data yang tidak lagi diperlukan dapat dianonimkan, disembunyikan, atau dihapus sesuai kebijakan internal dan batasan teknis sistem.",
            "Tidak ada sistem yang sepenuhnya bebas risiko; pengguna tetap wajib menjaga perangkat, password, OTP, dan akses akunnya.",
        ],
    },
    {
        "id": "user-rights",
        "title": "Hak Pengguna dan Penghapusan Akun",
        "items": [
            "Pengguna dapat memperbarui data profil yang tersedia di halaman akun.",
            "Pengguna dapat menghubungi customer service untuk koreksi data yang tidak dapat diubah sendiri, termasuk data kontak atau status tertentu.",
            "Pengguna dapat mengajukan penghapusan akun. UniTrade dapat melakukan deactivation, masking, atau anonymization terhadap data pribadi yang tidak lagi diperlukan.",
            "Sebagian data tetap dapat disimpan jika terkait transaksi, pembayaran, pengiriman, dispute, audit keamanan, kewajiban hukum, atau pencatatan operasional.",
            "Setelah akun dinonaktifkan, pengguna tidak dapat mengakses fitur yang membutuhkan login, termasuk wishlist, chat, order, dashboard seller, dan pengaturan akun.",
        ],
    },
    {
        "id": "liability",
        "title": "Pembatasan Tanggung Jawab",
        "paragraphs": [
            "UniTrade menyediakan sistem marketplace, tetapi tidak memproduksi, memiliki, atau menjamin seluruh produk dan jasa yang dijual oleh penjual. UniTrade dapat membantu moderasi, refund, dispute, dan penindakan akun sesuai bukti yang tersedia.",
            "UniTrade tidak bertanggung jawab atas kerugian akibat kelalaian pengguna, transaksi di luar sistem, informasi palsu yang diberikan pengguna, pelanggaran hukum oleh pengguna, atau gangguan layanan pihak ketiga seperti payment gateway dan pengiriman.",
        ],
    },
    {
        "id": "changes",
        "title": "Perubahan Kebijakan",
        "paragraphs": [
            "UniTrade dapat memperbarui syarat layanan dan kebijakan privasi ini untuk menyesuaikan fitur, kebutuhan operasional, integrasi pihak ketiga, atau perubahan aturan yang berlaku. Perubahan penting akan diinformasikan melalui website, notifikasi, atau media komunikasi UniTrade yang relevan.",
        ],
    },
]


class UnitradeLegalController(http.Controller):
    @http.route(
        ["/help", "/faq", "/terms", "/privacy-policy", "/syarat-ketentuan", "/kebijakan-privasi"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def legal_page(self, **kwargs):
        path = request.httprequest.path
        active_anchor = "terms" if path in ("/terms", "/privacy-policy", "/syarat-ketentuan", "/kebijakan-privasi") else "faq"
        if path in ("/privacy-policy", "/kebijakan-privasi"):
            page_title = "Kebijakan Privasi | UniTrade"
        elif path in ("/terms", "/syarat-ketentuan"):
            page_title = "Syarat & Ketentuan | UniTrade"
        else:
            page_title = "FAQ | UniTrade"
        return request.render(
            "unitrade_theme.unitrade_faq_terms_page",
            {
                "page_title": page_title,
                "active_anchor": active_anchor,
                "faq_items": FAQ_ITEMS,
                "policy_sections": POLICY_SECTIONS,
            },
        )
