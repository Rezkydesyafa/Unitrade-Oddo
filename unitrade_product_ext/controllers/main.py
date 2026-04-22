from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
import logging

_logger = logging.getLogger(__name__)


class UnitradeWebsiteSale(WebsiteSale):
    """Override the default Odoo product detail page to inject UniTrade data."""

    @http.route()
    def product(self, product, category='', search='', **kwargs):
        """Extend the default /shop/<product> to add review, seller, and recommendation data."""
        response = super().product(product, category=category, search=search, **kwargs)

        # Inject extra UniTrade data into the template context
        if hasattr(response, 'qcontext'):
            qcontext = response.qcontext
            prod = qcontext.get('product', product)

            # Get product images (main + extra)
            product_images = []
            try:
                if prod.product_variant_id:
                    product_images = prod.product_variant_id.product_template_image_ids
            except Exception:
                product_images = []

            # Get reviews (safe if module not installed)
            reviews = request.env['unitrade.review'].sudo()
            try:
                if 'unitrade.review' in request.env:
                    reviews = request.env['unitrade.review'].sudo().search([
                        ('product_id', '=', prod.id),
                        ('is_visible', '=', True),
                    ], order='create_date desc', limit=20)
            except Exception:
                pass

            # Get seller info
            seller = prod.x_seller_id if hasattr(prod, 'x_seller_id') else False

            # Get "other products from this store" — same seller
            seller_products = request.env['product.template'].sudo()
            if seller:
                seller_products = request.env['product.template'].sudo().search([
                    ('x_seller_id', '=', seller.id),
                    ('id', '!=', prod.id),
                    ('x_is_marketplace', '=', True),
                ], limit=6)

            # Fallback: same category products
            if not seller_products:
                seller_products = request.env['product.template'].sudo().search([
                    ('categ_id', '=', prod.categ_id.id),
                    ('id', '!=', prod.id),
                ], limit=6)

            # Check wishlist
            is_in_wishlist = False
            try:
                if 'unitrade.wishlist' in request.env:
                    if request.env.user and not request.env.user._is_public():
                        wishlist_item = request.env['unitrade.wishlist'].sudo().search([
                            ('user_id', '=', request.env.user.id),
                            ('product_id', '=', prod.id),
                        ], limit=1)
                        is_in_wishlist = bool(wishlist_item)
            except Exception:
                pass

            # Stock info
            qty_available = 0
            try:
                qty_available = prod.qty_available if hasattr(prod, 'qty_available') else 0
            except Exception:
                pass

            stock_text = 'Stok Tersedia' if qty_available > 0 else 'Stok Habis'
            shipping_text = 'Gratis Ongkir' if hasattr(prod, 'x_free_shipping') and prod.x_free_shipping else ''
            
            # Compute Rating values for template
            avg_rating = prod.x_average_rating if hasattr(prod, 'x_average_rating') and prod.x_average_rating else 0.0
            full_stars = int(avg_rating)
            has_half_star = (avg_rating - full_stars) >= 0.3
            
            # Weight formatting
            weight_val = prod.x_weight_product if hasattr(prod, 'x_weight_product') and prod.x_weight_product else 0
            weight_int = int(weight_val)

            # Is public user
            is_public_user = request.env.user._is_public()

            # Inject into qcontext
            qcontext.update({
                'ut_product_images': product_images,
                'ut_reviews': reviews,
                'ut_seller': seller,
                'ut_seller_products': seller_products,
                'ut_is_in_wishlist': is_in_wishlist,
                'ut_stock_text': stock_text,
                'ut_shipping_text': shipping_text,
                'ut_qty_available': int(qty_available),
                'ut_full_stars': full_stars,
                'ut_has_half_star': has_half_star,
                'ut_weight_int': weight_int,
                'ut_is_public_user': is_public_user,
            })

        return response
