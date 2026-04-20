from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


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
