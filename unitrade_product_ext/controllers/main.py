from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.osv import expression
import logging
import math

_logger = logging.getLogger(__name__)

DIY_DISTRICTS = {
    'yogyakarta': 'Kota Yogyakarta',
    'sleman': 'Sleman',
    'bantul': 'Bantul',
    'kulon_progo': 'Kulon Progo',
    'gunungkidul': 'Gunungkidul',
}


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
                wish = request.env['unitrade.wishlist'].sudo().search([
                    ('user_id', '=', request.env.uid),
                    ('product_id', '=', product.id),
                ], limit=1)
                is_in_wishlist = bool(wish)
            except Exception:
                _logger.exception('Failed to check UniTrade wishlist for product %s', product.id)

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

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        """Calculate distance in km between two GPS coordinates."""
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @staticmethod
    def _product_coordinates(product):
        """Return item coordinates, falling back to seller coordinates for existing data."""
        lat = _safe_get(product, 'x_item_latitude', 0) or _safe_get(product, 'x_seller_latitude', 0)
        lon = _safe_get(product, 'x_item_longitude', 0) or _safe_get(product, 'x_seller_longitude', 0)
        return lat, lon

    @http.route()
    def shop(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, ppg=False, **post):
        """Override shop to apply UniTrade sidebar filters and sorting."""
        response = super().shop(
            page=page, category=category, search=search,
            min_price=min_price, max_price=max_price, ppg=ppg, **post
        )

        if not hasattr(response, 'qcontext'):
            return response

        # --- Read filter params from URL ---
        ut_lokasi = post.get('lokasi', '')
        ut_kondisi = post.get('kondisi', '')
        ut_sort = post.get('sort', '')
        ut_min_price = 0
        ut_max_price = 0
        ut_lat = 0.0
        ut_lon = 0.0
        try:
            ut_min_price = int(post.get('ut_min_price', 0))
        except (ValueError, TypeError):
            pass
        try:
            ut_max_price = int(post.get('ut_max_price', 0))
        except (ValueError, TypeError):
            pass
        try:
            ut_lat = float(post.get('lat', 0))
            ut_lon = float(post.get('lon', 0))
        except (ValueError, TypeError):
            pass

        # --- Build extra domain ---
        extra_domain = []
        if ut_kondisi in ('new', 'used'):
            extra_domain.append(('x_condition', '=', ut_kondisi))
        if ut_min_price > 0:
            extra_domain.append(('list_price', '>=', ut_min_price))
        if ut_max_price > 0:
            extra_domain.append(('list_price', '<=', ut_max_price))

        # Location filters
        if ut_lokasi == 'kabupaten':
            seller_location_domains = [
                [('x_seller_location', 'ilike', label)]
                for label in DIY_DISTRICTS.values()
            ]
            extra_domain = expression.AND([
                extra_domain,
                expression.OR([
                    [('x_item_district', 'in', list(DIY_DISTRICTS.keys()))],
                ] + seller_location_domains),
            ])
        elif ut_lokasi == 'diy':
            seller_location_domains = [
                [('x_seller_location', 'ilike', label)]
                for label in DIY_DISTRICTS.values()
            ]
            extra_domain = expression.AND([
                extra_domain,
                expression.OR([
                    [('x_item_province', '=', 'diy')],
                    [('x_item_district', 'in', list(DIY_DISTRICTS.keys()))],
                ] + seller_location_domains),
            ])
        elif ut_lokasi == 'terdekat':
            extra_domain = expression.AND([
                extra_domain,
                expression.OR([
                    [('x_item_latitude', '!=', 0), ('x_item_longitude', '!=', 0)],
                    [('x_seller_latitude', '!=', 0), ('x_seller_longitude', '!=', 0)],
                ]),
            ])

        # --- Determine sort order ---
        sort_map = {
            'terkait': 'website_sequence asc',
            'terlaris': 'sales_count desc',
            'terbaru': 'create_date desc',
            'termurah': 'list_price asc',
            'termahal': 'list_price desc',
        }
        order = sort_map.get(ut_sort, 'website_sequence asc')

        # --- Re-query products if extra filters or sort is applied ---
        needs_requery = bool(extra_domain) or bool(ut_sort)
        if needs_requery:
            Product = request.env['product.template'].sudo()
            base_domain = [('sale_ok', '=', True), ('website_published', '=', True)]
            if search:
                base_domain += ['|',
                    ('name', 'ilike', search),
                    ('description_sale', 'ilike', search),
                ]
            if category:
                base_domain.append(('public_categ_ids', 'child_of', int(category)))

            full_domain = base_domain + extra_domain
            ppg_val = response.qcontext.get('ppg', 20)
            url_args = {
                'search': search,
                'lokasi': ut_lokasi,
                'kondisi': ut_kondisi,
                'sort': ut_sort,
                'ut_min_price': str(ut_min_price) if ut_min_price else '',
                'ut_max_price': str(ut_max_price) if ut_max_price else '',
            }

            # Special handling for "terdekat" — sort by Haversine distance
            if ut_lokasi == 'terdekat' and ut_lat and ut_lon:
                all_products = Product.search(full_domain)
                product_with_dist = []
                for p in all_products:
                    product_lat, product_lon = self._product_coordinates(p)
                    dist = self._haversine(ut_lat, ut_lon, product_lat, product_lon)
                    product_with_dist.append((p, dist))
                product_with_dist.sort(key=lambda x: x[1])

                product_count = len(product_with_dist)
                offset = int(page) * ppg_val if page else 0
                url_args.update({'lat': str(ut_lat), 'lon': str(ut_lon)})
                pager = request.website.pager(
                    url='/shop', total=product_count, page=page, step=ppg_val,
                    url_args=url_args
                )
                page_products = [pd[0] for pd in product_with_dist[offset:offset + ppg_val]]
                products = Product.browse([p.id for p in page_products]) if page_products else Product.browse([])
                response.qcontext['products'] = products
                response.qcontext['pager'] = pager
                response.qcontext['search_count'] = product_count
            else:
                product_count = Product.search_count(full_domain)
                pager = request.website.pager(
                    url='/shop', total=product_count, page=page, step=ppg_val,
                    url_args=url_args
                )
                products = Product.search(
                    full_domain, order=order,
                    limit=ppg_val, offset=pager['offset']
                )
                response.qcontext['products'] = products
                response.qcontext['pager'] = pager
                response.qcontext['search_count'] = product_count

        # --- Pass filter state to template ---
        response.qcontext['ut_lokasi'] = ut_lokasi
        response.qcontext['ut_kondisi'] = ut_kondisi
        response.qcontext['ut_sort'] = ut_sort
        response.qcontext['ut_min_price'] = ut_min_price
        response.qcontext['ut_max_price'] = ut_max_price

        return response

    @http.route('/unitrade/shop/filter', type='json', auth='public', website=True, csrf=False)
    def unitrade_shop_filter(self, **post):
        """Return the UniTrade shop product grid for OWL filter updates."""
        payload = dict(post)

        try:
            page = int(payload.pop('page', 0) or 0)
        except (ValueError, TypeError):
            page = 0

        search = payload.pop('search', '') or ''
        category_id = payload.pop('category_id', '') or payload.pop('category', '') or None
        ppg = payload.pop('ppg', False) or False

        try:
            category = int(category_id) if category_id else None
        except (ValueError, TypeError):
            category = None

        try:
            response = self.shop(
                page=page,
                category=category,
                search=search,
                min_price=0.0,
                max_price=0.0,
                ppg=ppg,
                **payload
            )
            if not hasattr(response, 'qcontext'):
                return {'html': '', 'search_count': 0}

            qcontext = response.qcontext
            html = request.env['ir.ui.view']._render_template(
                'unitrade_theme.unitrade_shop_results_fragment',
                qcontext
            )
            return {
                'html': str(html),
                'search_count': qcontext.get('search_count', 0),
            }
        except Exception:
            _logger.exception('Failed to render UniTrade OWL shop filter response')
            return {
                'html': '',
                'search_count': 0,
                'error': 'filter_render_failed',
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
