from odoo import http
from odoo.http import request
import logging
import json

_logger = logging.getLogger(__name__)


class UnitradeSellerController(http.Controller):

    @http.route('/unitrade/seller/register', type='http', auth='user', website=True)
    def seller_register_page(self, **kwargs):
        """Render seller registration page"""
        user = request.env.user
        existing_seller = request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', user.id)
        ], limit=1)

        values = {
            'user': user,
            'seller': existing_seller,
            'page_title': 'Daftar Jadi Seller — UniTrade',
        }
        return request.render('unitrade_seller.seller_register_template', values)

    @http.route('/unitrade/seller/register/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def seller_register_submit(self, **kwargs):
        """Handle seller registration form submission"""
        user = request.env.user

        # Check if already registered
        existing = request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', user.id)
        ], limit=1)
        if existing:
            return request.redirect('/unitrade/seller/register?error=already_registered')

        # Get form data
        nim = kwargs.get('nim', '').strip()
        ktm_file = kwargs.get('ktm_image')

        if not nim:
            return request.redirect('/unitrade/seller/register?error=nim_required')

        # Create seller record
        import base64
        vals = {
            'user_id': user.id,
            'nim': nim,
        }

        if ktm_file:
            vals['ktm_image'] = base64.b64encode(ktm_file.read())
            vals['ktm_filename'] = ktm_file.filename

        try:
            seller = request.env['unitrade.seller'].sudo().create(vals)
            if seller.ktm_image:
                seller.action_submit_verification()
            _logger.info('Seller registration created for user %s (NIM: %s)', user.name, nim)
            return request.redirect('/unitrade/seller/register?success=1')
        except Exception as e:
            _logger.error('Seller registration failed: %s', str(e))
            return request.redirect('/unitrade/seller/register?error=%s' % str(e))

    @http.route('/unitrade/seller/dashboard', type='http', auth='user', website=True)
    def seller_dashboard(self, **kwargs):
        """Render seller dashboard"""
        user = request.env.user
        seller = request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', user.id),
            ('status', '=', 'verified'),
        ], limit=1)

        if not seller:
            return request.redirect('/unitrade/seller/register')

        values = {
            'seller': seller,
            'page_title': 'Dashboard Penjual — UniTrade',
        }
        return request.render('unitrade_seller.seller_dashboard_template', values)

    @http.route('/unitrade/otp/send', type='json', auth='user', methods=['POST'])
    def send_otp(self, **kwargs):
        """Send OTP to user email"""
        try:
            request.env.user.action_send_otp()
            return {'status': 'success', 'message': 'OTP berhasil dikirim ke email Anda.'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/unitrade/otp/verify', type='json', auth='user', methods=['POST'])
    def verify_otp(self, **kwargs):
        """Verify OTP code"""
        data = request.jsonrequest
        otp_code = data.get('otp_code', '')

        try:
            request.env.user.action_verify_otp(otp_code)
            return {'status': 'success', 'message': 'Email berhasil diverifikasi!'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
