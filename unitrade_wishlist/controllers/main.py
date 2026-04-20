from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class UnitradeWishlistController(http.Controller):

    @http.route('/unitrade/wishlist', type='http', auth='user', website=True)
    def wishlist_page(self, **kwargs):
        items = request.env['unitrade.wishlist'].sudo().search([
            ('user_id', '=', request.env.uid)
        ])
        values = {
            'wishlist_items': items,
            'page_title': 'Wishlist — UniTrade',
        }
        return request.render('unitrade_wishlist.wishlist_page_template', values)

    @http.route('/unitrade/wishlist/toggle', type='json', auth='user', methods=['POST'])
    def wishlist_toggle(self, **kwargs):
        data = request.jsonrequest
        product_id = data.get('product_id')

        Wishlist = request.env['unitrade.wishlist'].sudo()
        existing = Wishlist.search([
            ('user_id', '=', request.env.uid),
            ('product_id', '=', product_id),
        ], limit=1)

        if existing:
            existing.unlink()
            return {'added': False, 'message': 'Dihapus dari wishlist'}
        else:
            Wishlist.create({
                'user_id': request.env.uid,
                'product_id': product_id,
            })
            return {'added': True, 'message': 'Ditambahkan ke wishlist'}
