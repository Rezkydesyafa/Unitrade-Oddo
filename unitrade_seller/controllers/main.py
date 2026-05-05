from odoo import http
from odoo.http import request
from markupsafe import Markup, escape
from werkzeug.urls import url_encode
import logging

_logger = logging.getLogger(__name__)


def _safe_get(record, field_name, default=False):
    """Safely read optional custom fields that may come from another addon."""
    try:
        return record[field_name] if field_name in record._fields else default
    except Exception:
        return default


class UnitradeSellerController(http.Controller):
    _PROFILE_TABS = ('home', 'latest', 'sold', 'reviews')

    @staticmethod
    def _seller_public_ref(seller):
        seller._ensure_profile_uuid()
        return seller.x_profile_uuid

    @staticmethod
    def _get_seller_by_public_ref(profile_ref=None, seller_id=None):
        Seller = request.env['unitrade.seller'].sudo()
        seller = Seller.browse()
        found_by_uuid = False
        if seller_id:
            seller = Seller.browse(seller_id).exists()
        elif profile_ref:
            seller = Seller.search([('x_profile_uuid', '=', profile_ref)], limit=1)
            found_by_uuid = bool(seller)
            if not seller and profile_ref.isdigit():
                seller = Seller.browse(int(profile_ref)).exists()

        if seller and (found_by_uuid or UnitradeSellerController._can_view_seller_profile(seller)):
            seller._ensure_profile_uuid()
            return seller
        return Seller.browse()

    @staticmethod
    def _can_view_seller_profile(seller):
        if seller.status == 'verified':
            return True

        user = request.env.user
        if user._is_public():
            return False

        if seller.user_id.id == user.id:
            return True

        return (
            user.has_group('base.group_system')
            or user.has_group('unitrade_seller.group_unitrade_admin')
        )

    @staticmethod
    def _seller_products(seller, search=None, tab='home', limit=15):
        Product = request.env['product.template'].sudo()
        domain = [
            ('x_seller_id', '=', seller.id),
            ('x_is_marketplace', '=', True),
            ('sale_ok', '=', True),
            ('website_published', '=', True),
        ]
        if search:
            domain += ['|', ('name', 'ilike', search), ('description_sale', 'ilike', search)]

        if tab == 'latest':
            order = 'create_date desc'
        elif tab == 'sold' and 'sales_count' in Product._fields:
            order = 'sales_count desc, create_date desc'
        else:
            order = 'website_sequence asc, create_date desc'

        return Product.search(domain, order=order, limit=limit)

    @staticmethod
    def _seller_address(seller):
        if seller.x_profile_address:
            return seller.x_profile_address

        partner = seller.partner_id
        if not partner:
            return seller.x_profile_location or 'Area kampus UNISA Yogyakarta'

        address_parts = [
            partner.street,
            partner.street2,
            partner.city,
            partner.state_id.name,
        ]
        return ', '.join([part for part in address_parts if part]) or seller.x_profile_location or 'Area kampus UNISA Yogyakarta'

    @staticmethod
    def _seller_map_coordinates(seller):
        lat = seller.x_profile_latitude
        lng = seller.x_profile_longitude
        if lat and lng:
            return lat, lng
        return -7.7162, 110.3554

    @staticmethod
    def _seller_review_summary(products):
        if not products or 'unitrade.review' not in request.env.registry:
            return {
                'rating': 0.0,
                'review_count': 0,
                'counts': {str(star): 0 for star in range(1, 6)},
            }

        domain = [
            ('product_id', 'in', products.ids),
            ('is_visible', '=', True),
        ]
        Review = request.env['unitrade.review'].sudo()
        reviews = Review.search(domain)
        review_count = len(reviews)
        counts = {}
        for star in range(1, 6):
            counts[str(star)] = Review.search_count(domain + [('rating', '=', star)])
        return {
            'rating': round(sum(reviews.mapped('rating')) / review_count, 1) if review_count else 0.0,
            'review_count': review_count,
            'counts': counts,
        }

    @staticmethod
    def _seller_reviews(products, rating=None, limit=12):
        if not products or 'unitrade.review' not in request.env.registry:
            return request.env['ir.ui.view'].browse()
        domain = [
            ('product_id', 'in', products.ids),
            ('is_visible', '=', True),
        ]
        if rating:
            domain.append(('rating', '=', rating))
        return request.env['unitrade.review'].sudo().search(domain, order='create_date desc', limit=limit)

    @staticmethod
    def _seller_review_star_filters(review_summary, rating, active_rating=None):
        rounded_rating = int(round(rating or 0))
        counts = review_summary.get('counts') or {}
        filters = [
            {
                'star': star,
                'count': counts.get(str(star), 0),
                'active': active_rating == star,
            }
            for star in range(5, 0, -1)
        ]
        display = [
            {
                'star': star,
                'count': counts.get(str(star), 0),
                'active': star <= rounded_rating,
            }
            for star in range(1, 6)
        ]
        return filters, display

    @staticmethod
    def _active_review_rating(value):
        try:
            rating = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return rating if 1 <= rating <= 5 else 0

    @http.route([
        '/seller-profile/<string:profile_ref>',
        '/unitrade/seller-profile/<string:profile_ref>',
        '/unitrade/seller/<int:seller_id>',
        '/seller/<int:seller_id>',
    ], type='http', auth='public', website=True, sitemap=True)
    def seller_profile(self, profile_ref=None, seller_id=None, **kwargs):
        """Render public seller profile from the Figma seller-page design."""
        seller = self._get_seller_by_public_ref(profile_ref=profile_ref, seller_id=seller_id)
        if not seller:
            return request.not_found()

        search = (kwargs.get('search') or '').strip()
        tab = kwargs.get('tab') or 'home'
        if tab not in self._PROFILE_TABS:
            tab = 'home'
        active_rating = self._active_review_rating(kwargs.get('rating')) if tab == 'reviews' else 0

        all_products = request.env['product.template'].sudo().search([
            ('x_seller_id', '=', seller.id),
            ('x_is_marketplace', '=', True),
            ('sale_ok', '=', True),
            ('website_published', '=', True),
        ])
        products = self._seller_products(seller, search=search, tab=tab)
        review_summary = self._seller_review_summary(all_products)
        seller_rating = review_summary['rating'] or seller.average_rating or 0.0
        review_star_filters, review_star_display = self._seller_review_star_filters(review_summary, seller_rating, active_rating)
        seller_reviews = self._seller_reviews(all_products, rating=active_rating)
        total_sold = int(sum(all_products.mapped('sales_count'))) if all_products and 'sales_count' in all_products._fields else 0
        joined_date = seller.create_date.strftime('%d/%m/%Y') if seller.create_date else ''
        seller_public_ref = self._seller_public_ref(seller)
        seller_map_lat, seller_map_lng = self._seller_map_coordinates(seller)

        values = {
            'seller': seller,
            'seller_public_ref': seller_public_ref,
            'seller_is_preview': seller.status != 'verified',
            'seller_products': products,
            'seller_all_products': all_products,
            'seller_address': self._seller_address(seller),
            'seller_map_lat': seller_map_lat,
            'seller_map_lng': seller_map_lng,
            'seller_rating': seller_rating,
            'seller_review_count': review_summary['review_count'],
            'seller_review_counts': review_summary['counts'],
            'seller_review_star_filters': review_star_filters,
            'seller_review_star_display': review_star_display,
            'seller_review_active_rating': active_rating,
            'seller_reviews': seller_reviews,
            'seller_total_sold': total_sold or seller.total_sold,
            'seller_joined_date': joined_date,
            'active_tab': tab,
            'seller_search': search,
            'seller_tab_urls': {
                key: '/seller-profile/%s?%s' % (
                    seller_public_ref,
                    url_encode({
                        'tab': key,
                        'search': search,
                    } if search else {'tab': key}),
                )
                for key in self._PROFILE_TABS
            },
            'page_title': '%s - Profil Penjual UniTrade' % seller.name,
        }
        return request.render('unitrade_seller.seller_profile_template', values)

    @http.route('/unitrade/seller-profile/products', type='json', auth='public', website=True, methods=['POST'])
    def seller_profile_products(self, **kwargs):
        """Return seller profile tab fragments for OWL switching."""
        profile_ref = kwargs.get('profile_ref') or ''
        tab = kwargs.get('tab') or 'home'
        search = (kwargs.get('search') or '').strip()
        if tab not in self._PROFILE_TABS:
            tab = 'home'
        active_rating = self._active_review_rating(kwargs.get('rating')) if tab == 'reviews' else 0

        seller = self._get_seller_by_public_ref(profile_ref=profile_ref)
        if not seller:
            return {
                'success': False,
                'message': 'Seller tidak ditemukan',
                'html': '',
            }

        all_products = request.env['product.template'].sudo().search([
            ('x_seller_id', '=', seller.id),
            ('x_is_marketplace', '=', True),
            ('sale_ok', '=', True),
            ('website_published', '=', True),
        ])
        template = 'unitrade_seller.seller_profile_reviews_fragment' if tab == 'reviews' else 'unitrade_seller.seller_profile_products_fragment'
        products = self._seller_products(seller, search=search, tab=tab)
        review_summary = self._seller_review_summary(all_products)
        seller_rating = review_summary['rating'] or seller.average_rating or 0.0
        review_star_filters, review_star_display = self._seller_review_star_filters(review_summary, seller_rating, active_rating)
        html = request.env['ir.ui.view']._render_template(
            template,
            {
                'seller': seller,
                'seller_products': products,
                'seller_reviews': self._seller_reviews(all_products, rating=active_rating),
                'seller_rating': seller_rating,
                'seller_review_count': review_summary['review_count'],
                'seller_review_counts': review_summary['counts'],
                'seller_review_star_filters': review_star_filters,
                'seller_review_star_display': review_star_display,
                'seller_review_active_rating': active_rating,
                'seller_search': search,
            },
        )
        return {
            'success': True,
            'html': str(html),
            'tab': tab,
            'search': search,
            'rating': active_rating,
        }

    @http.route('/unitrade/seller/profile', type='http', auth='user', website=True)
    def my_seller_profile(self, **kwargs):
        """Convenience route for the current user's public seller profile."""
        seller = request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', request.env.uid),
            ('status', '=', 'verified'),
        ], limit=1)
        if not seller:
            return request.redirect('/seller-verification')
        return request.redirect('/seller-profile/%s' % self._seller_public_ref(seller))

    @http.route([
        '/seller-profile/<string:profile_ref>/chat',
        '/unitrade/seller/<int:seller_id>/chat',
    ], type='http', auth='user', website=True)
    def seller_chat(self, profile_ref=None, seller_id=None, **kwargs):
        """Entry point for seller chat until a dedicated chat module is available."""
        seller = self._get_seller_by_public_ref(profile_ref=profile_ref, seller_id=seller_id)
        if not seller:
            return request.not_found()

        whatsapp = seller.user_id.x_whatsapp if 'x_whatsapp' in seller.user_id._fields else ''
        if whatsapp:
            phone = ''.join(ch for ch in whatsapp if ch.isdigit())
            if phone.startswith('0'):
                phone = '62%s' % phone[1:]
            return request.redirect('https://wa.me/%s' % phone, local=False)

        _logger.info('Seller chat requested by user %s for seller %s', request.env.uid, seller.id)
        return request.redirect('/seller-profile/%s?chat=requested' % self._seller_public_ref(seller))

    @http.route([
        '/seller-profile/<string:profile_ref>/report',
        '/unitrade/seller/<int:seller_id>/report',
    ], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def report_seller(self, profile_ref=None, seller_id=None, **kwargs):
        """Create a lightweight moderation note for a reported seller profile."""
        seller = self._get_seller_by_public_ref(profile_ref=profile_ref, seller_id=seller_id)
        if not seller:
            return request.not_found()

        reason = (kwargs.get('reason') or 'Report dari halaman profil penjual').strip()[:500]
        media_files = request.httprequest.files.getlist('media')
        if len(media_files) > 3:
            return request.redirect('/seller-profile/%s?report_error=media_limit' % self._seller_public_ref(seller))

        attachments = []
        for index, media in enumerate(media_files[:3], start=1):
            if not media or not media.filename:
                continue
            mimetype = media.mimetype or ''
            if not mimetype.startswith('image/'):
                continue
            filename = media.filename.rsplit('\\', 1)[-1].rsplit('/', 1)[-1] or 'seller-report-%s.jpg' % index
            attachments.append((filename, media.read()))

        body = Markup('Seller dilaporkan oleh %s: %s') % (escape(request.env.user.name), escape(reason))
        if attachments:
            body += Markup('<br/>Media pendukung: %s gambar.') % len(attachments)
        seller.message_post(body=body, subtype_xmlid='mail.mt_note', attachments=attachments, body_is_html=True)
        _logger.info(
            'Seller %s reported by user %s with %s media attachment(s)',
            seller.id,
            request.env.uid,
            len(attachments),
        )
        return request.redirect('/seller-profile/%s?reported=1' % self._seller_public_ref(seller))

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
