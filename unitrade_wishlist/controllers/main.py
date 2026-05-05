import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class UnitradeWishlistController(http.Controller):

    @http.route('/unitrade/wishlist', type='http', auth='user', website=True)
    def wishlist_legacy_page(self, **kwargs):
        return request.redirect('/my/wishlist')

    @http.route('/my/wishlist', type='http', auth='user', website=True)
    def wishlist_page(self, **kwargs):
        items = request.env['unitrade.wishlist'].sudo().search([
            ('user_id', '=', request.env.uid),
        ])
        values = {
            'wishlist_items': items,
            'wishlist_groups': self._prepare_wishlist_groups(items),
            'wishlist_count': len(items),
            'page_title': 'Wishlist - UniTrade',
        }
        return request.render('unitrade_wishlist.wishlist_page_template', values)

    @http.route('/unitrade/wishlist/toggle', type='json', auth='user', methods=['POST'])
    def wishlist_toggle(self, **kwargs):
        product_id = kwargs.get('product_id')
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return {'success': False, 'added': False, 'message': 'Produk tidak valid'}

        product = request.env['product.template'].sudo().browse(product_id).exists()
        if not product:
            return {'success': False, 'added': False, 'message': 'Produk tidak ditemukan'}

        Wishlist = request.env['unitrade.wishlist'].sudo()
        existing = Wishlist.search([
            ('user_id', '=', request.env.uid),
            ('product_id', '=', product_id),
        ], limit=1)

        if existing:
            existing.unlink()
            return {
                'success': True,
                'added': False,
                'message': 'Dihapus dari wishlist',
                'count': Wishlist.search_count([('user_id', '=', request.env.uid)]),
            }

        Wishlist.create({
            'user_id': request.env.uid,
            'product_id': product_id,
        })
        return {
            'success': True,
            'added': True,
            'message': 'Ditambahkan ke wishlist',
            'count': Wishlist.search_count([('user_id', '=', request.env.uid)]),
        }

    @http.route('/unitrade/wishlist/status', type='json', auth='public', methods=['POST'])
    def wishlist_status(self, **kwargs):
        product_id = kwargs.get('product_id')
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return {'success': False, 'active': False, 'message': 'Produk tidak valid'}

        if request.env.user._is_public():
            return {'success': True, 'active': False}

        product = request.env['product.template'].sudo().browse(product_id).exists()
        if not product:
            return {'success': False, 'active': False, 'message': 'Produk tidak ditemukan'}

        active = bool(request.env['unitrade.wishlist'].sudo().search_count([
            ('user_id', '=', request.env.uid),
            ('product_id', '=', product.id),
        ]))
        return {'success': True, 'active': active}

    @http.route('/unitrade/wishlist/remove', type='json', auth='user', methods=['POST'])
    def wishlist_remove(self, **kwargs):
        wishlist_id = kwargs.get('wishlist_id')
        product_id = kwargs.get('product_id')

        domain = [('user_id', '=', request.env.uid)]
        try:
            if wishlist_id:
                domain.append(('id', '=', int(wishlist_id)))
            else:
                domain.append(('product_id', '=', int(product_id)))
        except (TypeError, ValueError):
            return {'success': False, 'message': 'Produk tidak valid'}

        Wishlist = request.env['unitrade.wishlist'].sudo()
        existing = Wishlist.search(domain, limit=1)
        if existing:
            existing.unlink()

        return {
            'success': True,
            'message': 'Dihapus dari wishlist',
            'count': Wishlist.search_count([('user_id', '=', request.env.uid)]),
        }

    def _prepare_wishlist_groups(self, wishlist_items):
        grouped = []
        group_index = {}
        for item in wishlist_items:
            product = item.product_id.sudo()
            if not product.exists():
                continue

            seller = product.x_seller_id if 'x_seller_id' in product._fields and product.x_seller_id else False
            seller_key = seller.id if seller else 0
            if seller_key not in group_index:
                group = self._wishlist_seller_group(seller)
                group_index[seller_key] = group
                grouped.append(group)
            group_index[seller_key]['items'].append(self._wishlist_product_item(item, product, seller))
        return grouped

    def _wishlist_seller_group(self, seller):
        seller_ref = self._seller_public_ref(seller)
        return {
            'seller': seller,
            'seller_name': seller.name if seller else 'Penjual UniTrade',
            'seller_avatar_url': self._seller_avatar_url(seller),
            'seller_url': '/seller-profile/%s' % seller_ref if seller_ref else '#',
            'seller_chat_url': '/seller-profile/%s/chat' % seller_ref if seller_ref else '#',
            'items': [],
        }

    def _wishlist_product_item(self, wishlist, product, seller):
        variant = product.product_variant_id
        seller_ref = self._seller_public_ref(seller)
        can_order = bool(product.sale_ok and product.website_published and variant)
        if can_order and 'qty_available' in variant._fields:
            can_order = variant.qty_available > 0

        return {
            'wishlist_id': wishlist.id,
            'product_id': product.id,
            'name': product.name,
            'product_url': product.website_url or '/shop/product/%s' % product.id,
            'image_url': '/web/image/product.template/%s/image_512' % product.id,
            'category': product.categ_id.name if product.categ_id else '-',
            'quantity': self._quantity_label(product),
            'rating': self._rating_label(product),
            'price': self._format_product_price(product),
            'can_order': can_order,
            'cart_url': '/shop/cart/update?product_id=%s&add_qty=1' % variant.id if can_order else '#',
            'chat_url': '/seller-profile/%s/chat' % seller_ref if seller_ref else '#',
        }

    @staticmethod
    def _seller_public_ref(seller):
        if not seller:
            return ''
        if hasattr(seller, '_ensure_profile_uuid'):
            seller._ensure_profile_uuid()
        return seller.x_profile_uuid or seller.id

    @staticmethod
    def _seller_avatar_url(seller):
        if seller and seller.user_id:
            return '/web/image/res.users/%s/image_128?unique=%s' % (
                seller.user_id.id,
                seller.user_id.write_date or '',
            )
        return '/web/static/img/user_menu_avatar.png'

    @staticmethod
    def _quantity_label(product):
        qty = 0
        try:
            if product.product_variant_ids and 'qty_available' in product.product_variant_ids._fields:
                qty = sum(product.product_variant_ids.mapped('qty_available'))
        except Exception:
            _logger.debug('Unable to read wishlist stock for product %s', product.id, exc_info=True)
        return str(int(qty)) if float(qty or 0).is_integer() else ('%.2f' % qty).rstrip('0').rstrip('.')

    @staticmethod
    def _rating_label(product):
        rating = product.x_average_rating if 'x_average_rating' in product._fields else 0.0
        return '%.1f' % (rating or 0.0)

    @staticmethod
    def _format_product_price(product):
        currency = product.currency_id or request.website.currency_id or request.env.company.currency_id
        formatted = ('{:,.0f}'.format(product.list_price or 0.0)).replace(',', '.')
        symbol = currency.symbol or 'Rp'
        if currency.position == 'after':
            return '%s %s' % (formatted, symbol)
        return '%s %s' % (symbol, formatted)
