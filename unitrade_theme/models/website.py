from odoo import models


class Website(models.Model):
    _inherit = 'website'

    def _unitrade_browser_title(self, path='', title='', default_title=''):
        """Return a UniTrade browser tab title without the Odoo default site name."""
        clean_path = (path or '/').split('?', 1)[0] or '/'
        forced_title = self._unitrade_browser_title_for_path(clean_path)
        if forced_title:
            return forced_title

        browser_title = str(title or default_title or '').strip()
        if 'My Website' in browser_title:
            browser_title = browser_title.replace('My Website', 'UniTrade')
        if not browser_title or browser_title == 'Odoo':
            browser_title = 'UniTrade'
        return browser_title

    @staticmethod
    def _unitrade_browser_title_for_path(path):
        exact_titles = {
            '/': 'Marketplace Mahasiswa Yogyakarta',
            '/shop': 'Belanja Produk | UniTrade',
            '/shop/cart': 'Keranjang Belanja | UniTrade',
            '/shop/checkout': 'Checkout | UniTrade',
            '/shop/address': 'Checkout | UniTrade',
            '/shop/payment': 'Checkout | UniTrade',
            '/customer-service': 'Customer Service | UniTrade',
            '/my/customer-service': 'Customer Service | UniTrade',
            '/faq': 'FAQ | UniTrade',
            '/help': 'FAQ | UniTrade',
            '/privacy-policy': 'Kebijakan Privasi | UniTrade',
            '/kebijakan-privasi': 'Kebijakan Privasi | UniTrade',
            '/terms': 'Syarat & Ketentuan | UniTrade',
            '/syarat-ketentuan': 'Syarat & Ketentuan | UniTrade',
            '/contactus': 'Kontak | UniTrade',
            '/seller-onboarding': 'Mulai Berjualan | UniTrade',
            '/seller-verification': 'Verifikasi Penjual | UniTrade',
            '/unitrade/seller/dashboard': 'Dashboard Penjual | UniTrade',
            '/seller/dashboard': 'Dashboard Penjual | UniTrade',
            '/my/seller/dashboard': 'Dashboard Penjual | UniTrade',
            '/unitrade/chat': 'Chat | UniTrade',
            '/unitrade/seller/chat': 'Chat | UniTrade',
            '/my/profile': 'Profil Saya | UniTrade',
            '/my/account': 'Profil Saya | UniTrade',
            '/my/security': 'Keamanan Akun | UniTrade',
            '/my/settings': 'Pengaturan Akun | UniTrade',
            '/web/login': 'Masuk | UniTrade',
            '/web/signup': 'Daftar Akun | UniTrade',
            '/web/reset_password': 'Reset Password | UniTrade',
            '/web/verify-otp': 'Verifikasi OTP | UniTrade',
        }
        if path in exact_titles:
            return exact_titles[path]

        prefix_titles = (
            ('/customer-service/tickets', 'Tiket Bantuan | UniTrade'),
            ('/my/customer-service/tickets', 'Tiket Bantuan | UniTrade'),
            ('/unitrade/checkout', 'Checkout | UniTrade'),
            ('/unitrade/sponsorship', 'Sponsorship | UniTrade'),
            ('/unitrade/seller/orders', 'Pesanan Penjual | UniTrade'),
            ('/seller/orders', 'Pesanan Penjual | UniTrade'),
            ('/my/seller/orders', 'Pesanan Penjual | UniTrade'),
            ('/unitrade/seller/products', 'Produk Penjual | UniTrade'),
            ('/seller/products', 'Produk Penjual | UniTrade'),
            ('/my/seller/products', 'Produk Penjual | UniTrade'),
            ('/unitrade/seller/payouts', 'Pencairan Penjual | UniTrade'),
            ('/seller/payouts', 'Pencairan Penjual | UniTrade'),
            ('/my/seller/payouts', 'Pencairan Penjual | UniTrade'),
            ('/unitrade/seller/refunds', 'Refund Penjual | UniTrade'),
            ('/unitrade/seller/settings', 'Pengaturan Toko | UniTrade'),
            ('/seller/settings', 'Pengaturan Toko | UniTrade'),
            ('/my/seller/settings', 'Pengaturan Toko | UniTrade'),
            ('/unitrade/order/status', 'Status Pesanan | UniTrade'),
            ('/unitrade/payment/instructions', 'Instruksi Pembayaran | UniTrade'),
            ('/unitrade/payment/success', 'Pembayaran Berhasil | UniTrade'),
            ('/my/orders', 'Pesanan Saya | UniTrade'),
        )
        for prefix, browser_title in prefix_titles:
            if path.startswith(prefix):
                return browser_title
        return ''
