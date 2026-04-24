from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
import logging
import math

_logger = logging.getLogger(__name__)


def _safe_get(record, field_name, default=False):
    """Safely get a field value from a record, returning default if field doesn't exist."""
    try:
        return record[field_name] if field_name in record._fields else default
    except Exception:
        return default


class UnitradeProductController(http.Controller):

    @http.route('/unitrade/products', type='http', auth='public', website=True)
    def product_catalog(self, **kwargs):
        """Marketplace product catalog with filters"""
        Product = request.env['product.template'].sudo()

        products = Product._search_marketplace_products(
            keyword=kwargs.get('search'),
            category_id=kwargs.get('category'),
            condition=kwargs.get('condition'),
            min_price=kwargs.get('min_price'),
            max_price=kwargs.get('max_price'),
            location=kwargs.get('location'),
            sort_by=kwargs.get('sort', 'create_date desc'),
        )

        categories = request.env['product.category'].sudo().search([])

        values = {
            'products': products,
            'categories': categories,
            'search': kwargs.get('search', ''),
            'page_title': 'Katalog Produk — UniTrade',
        }
        return request.render('unitrade_product_ext.product_catalog_template', values)

    @http.route('/unitrade/product/<int:product_id>', type='http', auth='public', website=True)
    def product_detail(self, product_id, **kwargs):
        """Product detail page"""
        product = request.env['product.template'].sudo().browse(product_id)
        if not product.exists():
            return request.not_found()

        # Get similar products
        similar = request.env['product.template'].sudo().search([
            ('categ_id', '=', product.categ_id.id),
            ('id', '!=', product.id),
            ('x_is_marketplace', '=', True),
        ], limit=4)

        values = {
            'product': product,
            'similar_products': similar,
            'page_title': f'{product.name} — UniTrade',
        }
        return request.render('unitrade_product_ext.product_detail_template', values)


class UnitradeWebsiteSale(WebsiteSale):
    """Override WebsiteSale to inject pre-computed variables into product detail qcontext.
    
    This is needed because QWeb t-cache blocks do NOT have access to Python builtins
    like int(), getattr(), range(), etc. All computed values must come from the controller.
    """

    def _prepare_unitrade_product_values(self, product):
        """Compute all custom field values safely for the product detail template."""
        rating = _safe_get(product, 'x_average_rating', 0) or 0.0
        full_stars = int(rating)
        has_half = (rating - full_stars) >= 0.5
        review_count = _safe_get(product, 'x_review_count', 0) or 0
        weight = _safe_get(product, 'x_weight_product', 0) or 0
        condition = _safe_get(product, 'x_condition', '')
        brand = _safe_get(product, 'x_brand', '')
        specification = _safe_get(product, 'x_specification', '')
        seller_location = _safe_get(product, 'x_seller_location', '')
        seller_lat = _safe_get(product, 'x_seller_latitude', 0)
        seller_lng = _safe_get(product, 'x_seller_longitude', 0)
        seller = _safe_get(product, 'x_seller_id', False)

        # Reviews
        reviews = []
        try:
            Review = request.env['unitrade.review'].sudo()
            reviews = Review.search([
                ('product_id', '=', product.id),
                ('is_visible', '=', True),
            ], order='create_date desc', limit=20)
        except Exception:
            pass

        # Seller products
        seller_products = []
        if seller:
            try:
                seller_products = request.env['product.template'].sudo().search([
                    ('x_seller_id', '=', seller.id),
                    ('id', '!=', product.id),
                    ('website_published', '=', True),
                ], limit=8)
            except Exception:
                pass

        # Build related product data as plain dicts (no field access needed in template)
        seller_products_data = []
        for rp in seller_products:
            seller_products_data.append({
                'id': rp.id,
                'name': rp.name,
                'list_price': rp.list_price,
                'price_formatted': '{:,.0f}'.format(rp.list_price).replace(',', '.'),
                'location': _safe_get(rp, 'x_seller_location', '') or 'Yogyakarta',
                'rating': _safe_get(rp, 'x_average_rating', 0) or 0.0,
                'website_url': rp.website_url,
            })

        # Check wishlist
        is_in_wishlist = False
        is_public_user = request.env.user._is_public()
        if not is_public_user:
            try:
                wish = request.env['product.wishlist'].sudo().search([
                    ('partner_id', '=', request.env.user.partner_id.id),
                    ('product_id.product_tmpl_id', '=', product.id),
                ], limit=1)
                is_in_wishlist = bool(wish)
            except Exception:
                pass

        # Stock text
        try:
            qty = sum(product.product_variant_ids.mapped('qty_available'))
        except Exception:
            qty = 0
        stock_text = f'Stok: {int(qty)} tersedia' if qty > 0 else 'Stok habis'

        return {
            'ut_rating': rating,
            'ut_full_stars': full_stars,
            'ut_has_half_star': has_half,
            'ut_review_count': review_count,
            'ut_star_range': list(range(1, 6)),
            'ut_weight_int': int(weight),
            'ut_condition': condition,
            'ut_brand': brand,
            'ut_specification': specification,
            'ut_seller_location': seller_location,
            'ut_seller_lat': seller_lat,
            'ut_seller_lng': seller_lng,
            'ut_seller': seller,
            'ut_reviews': reviews,
            'ut_seller_products': seller_products_data,
            'ut_is_in_wishlist': is_in_wishlist,
            'ut_is_public_user': is_public_user,
            'ut_stock_text': stock_text,
            'ut_shipping_text': '',
            'ut_product_images': product.product_template_image_ids or [],
        }

    @http.route()
    def product(self, product, category='', search='', **kwargs):
        """Override to inject pre-computed UniTrade variables into qcontext."""
        response = super().product(product, category=category, search=search, **kwargs)

        if hasattr(response, 'qcontext') and response.qcontext.get('product'):
            prod = response.qcontext['product']
            ut_vals = self._prepare_unitrade_product_values(prod)
            response.qcontext.update(ut_vals)

        return response
