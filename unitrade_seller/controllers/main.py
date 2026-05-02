from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class UnitradeSellerController(http.Controller):

    @http.route(['/unitrade/seller/register', '/seller/register'], type='http', auth='user', website=True)
    def seller_register_page(self, **kwargs):
        """Keep the old seller URL as an alias for the current verification flow."""
        return request.redirect('/seller-verification')

    @http.route('/unitrade/seller/register/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def seller_register_submit(self, **kwargs):
        """Keep the old submit URL from creating a second verification path."""
        return request.redirect('/seller-verification')

    @http.route('/unitrade/seller/dashboard', type='http', auth='user', website=True)
    def seller_dashboard(self, **kwargs):
        """Render seller dashboard."""
        user = request.env.user
        seller = request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', user.id),
            ('status', '=', 'verified'),
        ], limit=1)

        if not seller:
            return request.redirect('/seller-verification')

        values = {
            'seller': seller,
            'page_title': 'Dashboard Penjual - UniTrade',
        }
        return request.render('unitrade_seller.seller_dashboard_template', values)

    @http.route('/unitrade/otp/send', type='json', auth='user', methods=['POST'])
    def send_otp(self, **kwargs):
        """Send OTP through the shared unitrade.otp model."""
        try:
            request.env.user.action_send_otp()
            return {'status': 'success', 'message': 'OTP berhasil dikirim ke email Anda.'}
        except Exception as e:
            _logger.exception('Failed to generate OTP for user %s', request.env.uid)
            return {'status': 'error', 'message': str(e)}

    @http.route('/unitrade/otp/verify', type='json', auth='user', methods=['POST'])
    def verify_otp(self, **kwargs):
        """Verify OTP through the shared unitrade.otp model."""
        data = request.jsonrequest or {}
        otp_code = data.get('otp_code', '')

        try:
            request.env.user.action_verify_otp(otp_code)
            request.env.user.sudo().write({'is_otp_verified': True})
            return {'status': 'success', 'message': 'Email berhasil diverifikasi!'}
        except Exception as e:
            _logger.exception('Failed to verify OTP for user %s', request.env.uid)
            return {'status': 'error', 'message': str(e)}
