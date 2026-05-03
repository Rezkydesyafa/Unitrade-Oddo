from odoo import http
from odoo.http import request
import base64
import binascii
import logging
import re

_logger = logging.getLogger(__name__)

_IMAGE_DATA_RE = re.compile(r'^data:(image/(?:jpeg|jpg|png|webp));base64,(.+)$')
_MAX_REVIEW_IMAGE_BYTES = 3 * 1024 * 1024


class UnitradeReviewController(http.Controller):

    @staticmethod
    def _review_payload(review):
        image_url = ''
        if review.review_image:
            mimetype = review.review_image_mimetype or 'image/jpeg'
            image_url = 'data:%s;base64,%s' % (mimetype, review.review_image.decode() if isinstance(review.review_image, bytes) else review.review_image)
        return {
            'id': review.id,
            'rating': review.rating,
            'comment': review.comment or '',
            'user_name': review.user_id.name or 'Pengguna',
            'date': review.create_date.strftime('%d %b %Y') if review.create_date else '',
            'avatar_url': '/web/image/res.users/%s/avatar_128' % review.user_id.id,
            'image_url': image_url,
        }

    @staticmethod
    def _prepare_review_image(image_data):
        if not image_data:
            return {}

        match = _IMAGE_DATA_RE.match(image_data)
        if not match:
            raise ValueError('Format gambar harus JPG, PNG, atau WebP.')

        mimetype = match.group(1).replace('image/jpg', 'image/jpeg')
        image_base64 = match.group(2)
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError('File gambar tidak valid.') from exc

        if len(image_bytes) > _MAX_REVIEW_IMAGE_BYTES:
            raise ValueError('Ukuran gambar maksimal 3 MB.')

        return {
            'review_image': base64.b64encode(image_bytes).decode('ascii'),
            'review_image_mimetype': mimetype,
        }

    @staticmethod
    def _summary(product_id):
        Review = request.env['unitrade.review'].sudo()
        domain = [
            ('product_id', '=', product_id),
            ('is_visible', '=', True),
        ]
        reviews = Review.search(domain)
        total = len(reviews)
        average = round(sum(reviews.mapped('rating')) / total, 1) if total else 0
        counts = {}
        for star in range(1, 6):
            counts[str(star)] = Review.search_count(domain + [('rating', '=', star)])
        return {
            'total': total,
            'average': average,
            'counts': counts,
        }

    @staticmethod
    def _eligible_order(product_id):
        if request.env.user._is_public():
            return request.env['sale.order']
        return request.env['sale.order'].sudo().search([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('state', '=', 'sale'),
            ('order_line.product_id.product_tmpl_id', '=', product_id),
        ], order='date_order desc', limit=1)

    @staticmethod
    def _can_review(product_id):
        if request.env.user._is_public():
            return False
        order = UnitradeReviewController._eligible_order(product_id)
        if not order:
            return False
        existing = request.env['unitrade.review'].sudo().search([
            ('product_id', '=', product_id),
            ('user_id', '=', request.env.uid),
            ('order_id', '=', order.id),
        ], limit=1)
        return not bool(existing)

    @http.route('/unitrade/reviews/list', type='json', auth='public', website=True, methods=['POST'])
    def list_reviews(self, **kwargs):
        try:
            product_id = int(kwargs.get('product_id') or 0)
        except (TypeError, ValueError):
            return {'success': False, 'message': 'Produk tidak valid'}

        sort = kwargs.get('sort') or 'newest'
        rating = kwargs.get('rating')
        limit = int(kwargs.get('limit') or 5)
        offset = int(kwargs.get('offset') or 0)

        domain = [
            ('product_id', '=', product_id),
            ('is_visible', '=', True),
        ]
        if rating:
            try:
                rating = int(rating)
                if 1 <= rating <= 5:
                    domain.append(('rating', '=', rating))
            except (TypeError, ValueError):
                pass

        order = 'create_date asc' if sort == 'oldest' else 'create_date desc'
        Review = request.env['unitrade.review'].sudo()
        total_filtered = Review.search_count(domain)
        reviews = Review.search(domain, order=order, limit=limit, offset=offset)

        return {
            'success': True,
            'reviews': [self._review_payload(review) for review in reviews],
            'total_filtered': total_filtered,
            'has_more': offset + limit < total_filtered,
            'summary': self._summary(product_id),
            'can_review': self._can_review(product_id),
            'is_public': request.env.user._is_public(),
        }

    @http.route('/unitrade/reviews/create', type='json', auth='user', website=True, methods=['POST'])
    def create_review(self, **kwargs):
        try:
            product_id = int(kwargs.get('product_id') or 0)
            rating = int(kwargs.get('rating') or 0)
        except (TypeError, ValueError):
            return {'success': False, 'message': 'Data ulasan tidak valid'}

        comment = (kwargs.get('comment') or '').strip()
        if rating < 1 or rating > 5:
            return {'success': False, 'message': 'Rating harus antara 1 sampai 5'}

        try:
            image_values = self._prepare_review_image(kwargs.get('image_data') or '')
        except ValueError as exc:
            return {'success': False, 'message': str(exc)}

        order = self._eligible_order(product_id)
        if not order:
            return {
                'success': False,
                'message': 'Ulasan hanya bisa diberikan setelah pesanan produk ini selesai.',
            }

        try:
            review = request.env['unitrade.review'].sudo().create({
                'product_id': product_id,
                'user_id': request.env.uid,
                'order_id': order.id,
                'rating': rating,
                'comment': comment,
                'is_visible': True,
                **image_values,
            })
        except Exception as exc:
            _logger.exception('Failed to create UniTrade review')
            return {'success': False, 'message': str(exc)}

        return {
            'success': True,
            'message': 'Ulasan berhasil dikirim',
            'review': self._review_payload(review),
            'summary': self._summary(product_id),
            'can_review': False,
        }
