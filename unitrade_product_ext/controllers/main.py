from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.http_routing.models.ir_http import slug
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

UNITRADE_MAX_FILTER_PRICE = 10_000_000
UNITRADE_SORT_MAP = {
    'terkait': 'website_sequence asc',
    'terlaris': 'sales_count desc',
    'terbaru': 'create_date desc',
    'termurah': 'list_price asc',
    'termahal': 'list_price desc',
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
        weight = _safe_get(product, 'x_weight_product', 0) or 0
        condition = _safe_get(product, 'x_condition', '')
        brand = _safe_get(product, 'x_brand', '')
        specification = _safe_get(product, 'x_specification', '')
        seller_location = _safe_get(product, 'x_seller_location', '')
        seller_lat = _safe_get(product, 'x_seller_latitude', 0)
        seller_lng = _safe_get(product, 'x_seller_longitude', 0)
        item_lat = _safe_get(product, 'x_item_latitude', 0)
        item_lng = _safe_get(product, 'x_item_longitude', 0)
        map_lat = item_lat or seller_lat
        map_lng = item_lng or seller_lng
        seller = _safe_get(product, 'x_seller_id', False)
        discount_percent = max(_safe_get(product, 'x_discount_percent', 0) or 0, 0)
        original_price = product.list_price or 0.0
        has_discount = bool(discount_percent and original_price > 0)
        discounted_price = (
            original_price * (100 - min(discount_percent, 100)) / 100
            if has_discount
            else original_price
        )

        # Reviews
        reviews = []
        review_count = 0
        rating = 0.0
        try:
            Review = request.env['unitrade.review'].sudo()
            review_domain = [
                ('product_id', '=', product.id),
                ('is_visible', '=', True),
            ]
            reviews = Review.search(review_domain, order='create_date desc', limit=20)
            review_stats = Review.read_group(review_domain, ['rating:avg'], [])
            if review_stats:
                review_count = review_stats[0].get('__count', 0)
                rating = round(review_stats[0].get('rating_avg') or 0.0, 1) if review_count else 0.0
        except Exception:
            _logger.exception('Failed to load UniTrade reviews for product %s', product.id)
        full_stars = int(rating)
        has_half = (rating - full_stars) >= 0.5

        # Marketplace recommendations
        recommended_products = request.env['product.template']
        try:
            Product = request.env['product.template'].sudo()
            base_domain = [
                ('id', '!=', product.id),
                ('x_is_marketplace', '=', True),
                ('sale_ok', '=', True),
                ('website_published', '=', True),
            ]
            if product.categ_id:
                recommended_products = Product.search(
                    base_domain + [('categ_id', '=', product.categ_id.id)],
                    order='create_date desc',
                    limit=8,
                )
            if len(recommended_products) < 8:
                extra_products = Product.search(
                    base_domain + [('id', 'not in', recommended_products.ids)],
                    order='create_date desc',
                    limit=8 - len(recommended_products),
                )
                recommended_products |= extra_products
        except Exception:
            _logger.exception('Failed to load UniTrade product recommendations for product %s', product.id)

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
            variant = product.product_variant_id or product.product_variant_ids[:1]
            if variant and hasattr(request.website, '_get_product_available_qty'):
                qty = request.website.sudo()._get_product_available_qty(variant.sudo())
            else:
                qty = (
                    sum(product.product_variant_ids.sudo().mapped('qty_available'))
                    if 'qty_available' in product.product_variant_ids._fields
                    else None
                )
        except Exception:
            qty = None
        allow_out_of_stock = bool(
            'allow_out_of_stock_order' in product._fields
            and product.allow_out_of_stock_order
        )
        stock_text = (
            f'Stok: {int(qty)} tersedia'
            if qty and qty > 0
            else 'Stok habis' if qty == 0 else 'Tersedia'
        )
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
            'ut_has_discount': has_discount,
            'ut_discount_percent': discount_percent,
            'ut_original_price': original_price,
            'ut_discounted_price': discounted_price,
            'ut_seller_location': seller_location,
            'ut_seller_lat': seller_lat,
            'ut_seller_lng': seller_lng,
            'ut_map_lat': map_lat,
            'ut_map_lng': map_lng,
            'ut_seller': seller,
            'ut_reviews': reviews,
            'ut_recommended_products': recommended_products,
            'ut_is_in_wishlist': is_in_wishlist,
            'ut_is_public_user': is_public_user,
            'ut_stock_text': stock_text,
            'ut_available_qty': max(qty or 0, 0) if qty is not None else 0,
            'ut_cart_qty': 0,
            'ut_allow_out_of_stock_order': allow_out_of_stock,
            'ut_product_stock_warning': request.session.pop('unitrade_product_stock_warning', ''),
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

    def _unitrade_int(self, value, default=0):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed

    def _unitrade_float(self, value, default=0.0):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return parsed if math.isfinite(parsed) else default

    def _unitrade_price(self, value):
        parsed = self._unitrade_int(value, 0)
        if parsed < 0:
            return 0
        return min(parsed, UNITRADE_MAX_FILTER_PRICE)

    def _unitrade_normalized_shop_filters(self, page=1, category=None, search='', ppg=False, **post):
        min_price = self._unitrade_price(post.get('ut_min_price', 0))
        max_price = self._unitrade_price(post.get('ut_max_price', 0))
        if max_price and max_price < min_price:
            max_price = 0

        return {
            'page': max(self._unitrade_int(page, 1), 1),
            'category': category,
            'search': (search or post.get('search') or '').strip(),
            'ppg': ppg or post.get('ppg') or False,
            'lokasi': post.get('lokasi') if post.get('lokasi') in ('terdekat', 'kabupaten', 'diy') else '',
            'kondisi': post.get('kondisi') if post.get('kondisi') in ('new', 'used') else '',
            'sort': post.get('sort') if post.get('sort') in UNITRADE_SORT_MAP else 'terkait',
            'ut_min_price': min_price,
            'ut_max_price': max_price,
            'lat': self._unitrade_float(post.get('lat'), 0.0),
            'lon': self._unitrade_float(post.get('lon'), 0.0),
        }

    def _unitrade_filter_domain(self, values):
        domain = []
        if values['kondisi']:
            domain.append(('x_condition', '=', values['kondisi']))
        if values['ut_min_price']:
            domain.append(('list_price', '>=', values['ut_min_price']))
        if values['ut_max_price']:
            domain.append(('list_price', '<=', values['ut_max_price']))

        if values['lokasi'] == 'kabupaten':
            seller_location_domains = [
                [('x_seller_location', 'ilike', label)]
                for label in DIY_DISTRICTS.values()
            ]
            domain = expression.AND([
                domain,
                expression.OR([
                    [('x_item_district', 'in', list(DIY_DISTRICTS.keys()))],
                ] + seller_location_domains),
            ])
        elif values['lokasi'] == 'diy':
            seller_location_domains = [
                [('x_seller_location', 'ilike', label)]
                for label in DIY_DISTRICTS.values()
            ]
            domain = expression.AND([
                domain,
                expression.OR([
                    [('x_item_province', '=', 'diy')],
                    [('x_item_district', 'in', list(DIY_DISTRICTS.keys()))],
                ] + seller_location_domains),
            ])
        elif values['lokasi'] == 'terdekat':
            domain = expression.AND([
                domain,
                expression.OR([
                    [('x_item_latitude', '!=', 0), ('x_item_longitude', '!=', 0)],
                    [('x_seller_latitude', '!=', 0), ('x_seller_longitude', '!=', 0)],
                ]),
            ])
        return domain

    def _unitrade_shop_url(self, category):
        if category and getattr(category, 'id', False):
            return '/shop/category/%s' % slug(category)
        return '/shop'

    def _unitrade_url_args(self, values):
        args = {}
        if values['search']:
            args['search'] = values['search']
        if values['ppg']:
            args['ppg'] = values['ppg']
        if values['lokasi']:
            args['lokasi'] = values['lokasi']
        if values['kondisi']:
            args['kondisi'] = values['kondisi']
        if values['sort'] and values['sort'] != 'terkait':
            args['sort'] = values['sort']
        if values['ut_min_price']:
            args['ut_min_price'] = str(values['ut_min_price'])
        if values['ut_max_price']:
            args['ut_max_price'] = str(values['ut_max_price'])
        if values['lokasi'] == 'terdekat' and values['lat'] and values['lon']:
            args['lat'] = '%.6f' % values['lat']
            args['lon'] = '%.6f' % values['lon']
        return args

    def _unitrade_shop_metadata(self, qcontext, fallback_page=1):
        pager = qcontext.get('pager') or {}
        page_info = pager.get('page') or {}
        current_page = page_info.get('num') or max(self._unitrade_int(fallback_page, 1), 1)
        page_count = pager.get('page_count') or 0
        has_more = bool(page_count and current_page < page_count)
        return {
            'page': current_page,
            'page_count': page_count,
            'has_more': has_more,
            'next_page': current_page + 1 if has_more else False,
        }

    def _unitrade_apply_shop_filters(self, response, values):
        if not hasattr(response, 'qcontext'):
            return {}

        qcontext = response.qcontext
        category = qcontext.get('category') or values['category']
        ppg_val = qcontext.get('ppg') or self._unitrade_int(values['ppg'], 20) or 20
        filter_domain = self._unitrade_filter_domain(values)
        needs_requery = bool(filter_domain) or values['sort'] != 'terkait'

        if needs_requery:
            Product = request.env['product.template'].sudo().with_context(bin_size=True)
            base_domain = self._get_shop_domain(values['search'], category, [])
            full_domain = expression.AND([base_domain, filter_domain]) if filter_domain else base_domain
            url_args = self._unitrade_url_args(values)
            url = self._unitrade_shop_url(category)

            if values['lokasi'] == 'terdekat' and values['lat'] and values['lon']:
                all_products = Product.search(full_domain)
                products_with_distance = []
                for product in all_products:
                    product_lat, product_lon = self._product_coordinates(product)
                    distance = self._haversine(values['lat'], values['lon'], product_lat, product_lon)
                    products_with_distance.append((product, distance))
                products_with_distance.sort(key=lambda item: item[1])

                product_count = len(products_with_distance)
                pager = request.website.pager(
                    url=url, total=product_count, page=values['page'], step=ppg_val,
                    url_args=url_args
                )
                page_products = products_with_distance[pager['offset']:pager['offset'] + ppg_val]
                products = Product.browse([product.id for product, _distance in page_products])
            else:
                product_count = Product.search_count(full_domain)
                pager = request.website.pager(
                    url=url, total=product_count, page=values['page'], step=ppg_val,
                    url_args=url_args
                )
                products = Product.search(
                    full_domain,
                    order=UNITRADE_SORT_MAP.get(values['sort'], UNITRADE_SORT_MAP['terkait']),
                    limit=ppg_val,
                    offset=pager['offset'],
                )

            qcontext.update({
                'products': products,
                'pager': pager,
                'search_count': product_count,
                'search_product': products,
            })

        qcontext.update({
            'ut_lokasi': values['lokasi'],
            'ut_kondisi': values['kondisi'],
            'ut_sort': values['sort'],
            'ut_min_price': values['ut_min_price'],
            'ut_max_price': values['ut_max_price'],
            'ut_lat': values['lat'],
            'ut_lon': values['lon'],
        })
        metadata = self._unitrade_shop_metadata(qcontext, values['page'])
        qcontext.update({
            'ut_page': metadata['page'],
            'ut_page_count': metadata['page_count'],
            'ut_has_more': metadata['has_more'],
            'ut_next_page': metadata['next_page'],
        })
        return metadata

    @http.route()
    def shop(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, ppg=False, **post):
        """Override shop to apply UniTrade sidebar filters and sorting."""
        values = self._unitrade_normalized_shop_filters(
            page=page or 1, category=category, search=search, ppg=ppg, **post
        )
        response = super().shop(
            page=page, category=category, search=values['search'],
            min_price=min_price, max_price=max_price, ppg=ppg, **post
        )

        if not hasattr(response, 'qcontext'):
            return response

        self._unitrade_apply_shop_filters(response, values)
        return response

    @http.route('/unitrade/shop/filter', type='json', auth='public', website=True, csrf=False)
    def unitrade_shop_filter(self, **post):
        """Return the UniTrade shop product grid for OWL filter updates."""
        payload = dict(post)

        page = max(self._unitrade_int(payload.pop('page', 1), 1), 1)

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
                return {
                    'html': '',
                    'search_count': 0,
                    'page': page,
                    'page_count': 0,
                    'has_more': False,
                    'next_page': False,
                }

            qcontext = response.qcontext
            html = request.env['ir.ui.view']._render_template(
                'unitrade_theme.unitrade_shop_results_fragment',
                qcontext
            )
            metadata = self._unitrade_shop_metadata(qcontext, page)
            return {
                'html': str(html),
                'search_count': qcontext.get('search_count', 0),
                'page': metadata['page'],
                'page_count': metadata['page_count'],
                'has_more': metadata['has_more'],
                'next_page': metadata['next_page'],
            }
        except Exception:
            _logger.exception('Failed to render UniTrade OWL shop filter response')
            return {
                'html': '',
                'search_count': 0,
                'page': page,
                'page_count': 0,
                'has_more': False,
                'next_page': False,
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
