import base64

from odoo import http
from odoo.http import request
from odoo.tools.mimetypes import guess_mimetype


class UnitradeSellerMedia(http.Controller):
    """Serve seller avatar reliably (sudo + fallback) untuk dipakai di UI."""

    @http.route('/unitrade/seller-avatar/<int:seller_id>', type='http', auth='public', website=True, sitemap=False)
    def unitrade_seller_avatar(self, seller_id, **kwargs):
        fallback = '/web/static/img/user_menu_avatar.png'
        if 'unitrade.seller' not in request.env.registry:
            return request.redirect(fallback)
        seller = request.env['unitrade.seller'].sudo().browse(seller_id).exists()
        if not seller:
            return request.redirect(fallback)
        image = False
        if 'x_avatar_128' in seller._fields:
            image = seller.x_avatar_128
        if not image and seller.user_id:
            image = seller.user_id.avatar_128
        if not image and seller.partner_id:
            image = seller.partner_id.image_128
        if not image:
            return request.redirect(fallback)
        try:
            raw = base64.b64decode(image)
        except Exception:
            return request.redirect(fallback)
        return request.make_response(raw, headers=[
            ('Content-Type', guess_mimetype(raw, default='image/png')),
            ('Cache-Control', 'public, max-age=86400'),
        ])
