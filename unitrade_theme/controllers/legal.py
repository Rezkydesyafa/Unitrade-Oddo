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
]


POLICY_SECTIONS = [
    {
        "id": "general",
        "title": "Ketentuan Umum",
        "paragraphs": [
            "UniTrade adalah platform marketplace C2C. Dengan menggunakan layanan ini, pengguna dianggap "
            "telah membaca, memahami, dan menyetujui seluruh ketentuan yang berlaku."
        ],
    },
    {
        "id": "account-security",
        "title": "Akun dan Keamanan",
        "items": [
            "Pengguna wajib mendaftar menggunakan email atau nomor HP yang valid serta membuat username unik.",
            "Aktivasi akun dilakukan melalui verifikasi OTP yang dikirim ke email atau nomor HP pengguna.",
            "Pengguna bertanggung jawab penuh atas kerahasiaan akun dan password.",
            "UniTrade berhak melakukan penguncian akun sementara jika terdeteksi aktivitas login yang mencurigakan atau kegagalan login berulang.",
            "Pengguna dilarang menggunakan akun orang lain tanpa izin.",
        ],
    },
    {
        "id": "profile",
        "title": "Profil Pengguna",
        "items": [
            "Pengguna dapat mengubah data profil seperti nama lengkap, alamat, tanggal lahir, dan foto profil.",
            "Email dan nomor HP tidak dapat diubah langsung dan memerlukan proses verifikasi tambahan.",
            "Pengguna bertanggung jawab atas kebenaran data yang ditampilkan di profil.",
        ],
    },
    {
        "id": "seller-terms",
        "title": "Ketentuan Penjual",
        "items": [
            "Untuk menjadi penjual, pengguna wajib melakukan verifikasi identitas mahasiswa (KTM).",
            "Dokumen KTM harus asli, jelas, dan sesuai dengan identitas pengguna.",
            "UniTrade berhak menyetujui atau menolak verifikasi penjual berdasarkan hasil pemeriksaan.",
            "Penjual dilarang menjual barang terlarang, ilegal, atau melanggar hukum.",
            "Penjual bertanggung jawab atas keaslian produk, kesesuaian deskripsi produk, dan ketersediaan stok.",
        ],
    },
    {
        "id": "products-transactions",
        "title": "Produk dan Transaksi",
        "items": [
            "Semua transaksi dilakukan melalui sistem UniTrade.",
            "Status transaksi terdiri dari: Menunggu, Diproses, Dikirim, Selesai, atau Dibatalkan.",
            "Pembeli dapat membatalkan pesanan selama status masih Menunggu.",
            "Transaksi dianggap selesai setelah pembeli melakukan konfirmasi barang diterima.",
            "UniTrade tidak bertanggung jawab atas kesepakatan di luar sistem aplikasi.",
        ],
    },
    {
        "id": "seller-registration",
        "title": "Bagaimana cara menjadi penjual di UniTrade?",
        "paragraphs": [
            "Pengguna dapat mengajukan aktivasi akun penjual melalui menu Daftar sebagai Penjual, lalu "
            "mengunggah KTM untuk verifikasi. Setelah disetujui admin, akun akan aktif sebagai penjual dan "
            "siap digunakan untuk menjual produk atau jasa."
        ],
    },
    {
        "id": "chat-policy",
        "title": "Ketentuan Chat",
        "items": [
            "Fitur chat digunakan untuk komunikasi terkait transaksi.",
            "Pengguna dilarang mengirim konten pornografi, ujaran kebencian, penipuan, atau spam.",
            "UniTrade berhak menindak akun yang menyalahgunakan fitur chat.",
        ],
    },
    {
        "id": "ratings",
        "title": "Rating dan Ulasan",
        "paragraphs": [
            "Rating dan ulasan hanya dapat diberikan untuk transaksi yang telah selesai. Ulasan diharapkan "
            "bersifat jujur, objektif, dan relevan dengan pengalaman transaksi, baik berupa penilaian positif "
            "maupun kritik.",
            "Untuk menjaga kualitas dan keamanan interaksi, UniTrade menerapkan filter otomatis dan peninjauan "
            "manual terhadap ulasan yang terindikasi melanggar.",
        ],
        "bullets": [
            "UniTrade berhak menghapus ulasan yang mengandung ujaran kebencian atau diskriminasi.",
            "UniTrade berhak menghapus ulasan yang bersifat menyerang individu atau tidak relevan dengan transaksi.",
        ],
    },
    {
        "id": "wishlist-cart",
        "title": "Wishlist dan Keranjang",
        "items": [
            "Wishlist hanya dapat diakses oleh pengguna yang login.",
            "Produk di wishlist tidak menjamin ketersediaan stok.",
            "Produk di keranjang dapat berubah harga atau stok sewaktu-waktu.",
        ],
    },
    {
        "id": "account-deletion",
        "title": "Penghapusan Akun",
        "items": [
            "Pengguna dapat mengajukan penghapusan akun melalui menu pengaturan.",
            "Penghapusan akun bersifat soft delete.",
            "Setelah akun dihapus, pengguna tidak dapat mengakses layanan UniTrade.",
        ],
    },
    {
        "id": "liability",
        "title": "Pembatasan Tanggung Jawab",
        "paragraphs": [
            "UniTrade bertindak sebagai penyedia platform, bukan pihak dalam transaksi. Segala risiko transaksi "
            "menjadi tanggung jawab penjual dan pembeli."
        ],
    },
    {
        "id": "changes",
        "title": "Perubahan Ketentuan",
        "paragraphs": [
            "UniTrade berhak mengubah Syarat & Ketentuan sewaktu-waktu. Perubahan akan diberitahukan melalui aplikasi."
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
        return request.render(
            "unitrade_theme.unitrade_faq_terms_page",
            {
                "page_title": "FAQ & Syarat Kebijakan UniTrade",
                "active_anchor": active_anchor,
                "faq_items": FAQ_ITEMS,
                "policy_sections": POLICY_SECTIONS,
            },
        )
