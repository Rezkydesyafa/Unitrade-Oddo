from odoo import http
from odoo.http import request
import base64
import binascii
import logging
import re

_logger = logging.getLogger(__name__)

_IMAGE_DATA_RE = re.compile(r'^data:(image/(?:jpeg|jpg|png|webp));base64,(.+)$')
_MAX_REVIEW_IMAGE_BYTES = 2 * 1024 * 1024
_MAX_REVIEW_IMAGES = 3


class UnitradeReviewController(http.Controller):

    @staticmethod
    def _review_payload(review):
        images = []
        for field_name, mimetype_field in (
            ('review_image', 'review_image_mimetype'),
            ('review_image_2', 'review_image_2_mimetype'),
            ('review_image_3', 'review_image_3_mimetype'),
        ):
            image_value = review[field_name]
            if image_value:
                mimetype = review[mimetype_field] or 'image/jpeg'
                encoded = image_value.decode() if isinstance(image_value, bytes) else image_value
                images.append('data:%s;base64,%s' % (mimetype, encoded))
        return {
            'id': review.id,
            'rating': review.rating,
            'comment': review.comment or '',
            'tags': [tag.strip() for tag in (review.review_tags or '').split(',') if tag.strip()],
            'user_name': review.user_id.name or 'Pengguna',
            'date': review.create_date.strftime('%d %b %Y') if review.create_date else '',
            'avatar_url': '/web/image/res.users/%s/avatar_128' % review.user_id.id,
            'image_url': images[0] if images else '',
            'image_urls': images,
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

        if len(image_bytes) >= _MAX_REVIEW_IMAGE_BYTES:
            raise ValueError('Ukuran setiap gambar harus kurang dari 2 MB.')

        return {
            'review_image': base64.b64encode(image_bytes).decode('ascii'),
            'review_image_mimetype': mimetype,
        }

    @classmethod
    def _prepare_review_images(cls, image_items):
        image_items = image_items or []
        if isinstance(image_items, str):
            image_items = [image_items] if image_items else []
        if not isinstance(image_items, list):
            raise ValueError('Data gambar tidak valid.')
        if len(image_items) > _MAX_REVIEW_IMAGES:
            raise ValueError('Maksimal 3 gambar.')

        values = {}
        target_fields = [
            ('review_image', 'review_image_mimetype'),
            ('review_image_2', 'review_image_2_mimetype'),
            ('review_image_3', 'review_image_3_mimetype'),
        ]
        for index, image_data in enumerate(image_items):
            prepared = cls._prepare_review_image(image_data)
            if not prepared:
                continue
            image_field, mimetype_field = target_fields[index]
            values[image_field] = prepared['review_image']
            values[mimetype_field] = prepared['review_image_mimetype']
        return values

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
            ('state', 'in', ['sale', 'done']),
            ('order_line.product_id.product_tmpl_id', '=', product_id),
        ], order='date_order desc', limit=1)

    @staticmethod
    def _eligible_order_for_review(product_id, order_id=None):
        if request.env.user._is_public():
            return request.env['sale.order']

        partner = request.env.user.partner_id.commercial_partner_id
        partners = request.env['res.partner'].sudo().search([('commercial_partner_id', '=', partner.id)])
        domain = [
            ('partner_id', 'in', partners.ids),
            ('state', 'in', ['sale', 'done']),
            ('order_line.product_id.product_tmpl_id', '=', product_id),
        ]
        if order_id:
            domain.append(('id', '=', order_id))
        return request.env['sale.order'].sudo().search(domain, order='date_order desc', limit=1)

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
        ], limit=1)
        return not bool(existing)

    @staticmethod
    def _review_status_map(product_ids):
        product_ids = [int(product_id) for product_id in product_ids if int(product_id or 0)]
        if request.env.user._is_public() or not product_ids:
            return {}

        Review = request.env['unitrade.review'].sudo()
        reviews = Review.search([
            ('product_id', 'in', product_ids),
            ('user_id', '=', request.env.uid),
        ])
        reviewed_ids = set(reviews.mapped('product_id').ids)
        return {
            str(product_id): {
                'reviewed': product_id in reviewed_ids,
                'can_review': product_id not in reviewed_ids,
            }
            for product_id in product_ids
        }

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

        order_map = {
            'oldest': 'create_date asc',
            'highest': 'rating desc, create_date desc',
            'lowest': 'rating asc, create_date desc',
            'newest': 'create_date desc',
        }
        order = order_map.get(sort, 'create_date desc')
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

    @http.route('/unitrade/reviews/status', type='json', auth='user', website=True, methods=['POST'])
    def review_status(self, **kwargs):
        product_ids = kwargs.get('product_ids') or []
        if isinstance(product_ids, (str, int)):
            product_ids = [product_ids]
        try:
            normalized_ids = list({int(product_id) for product_id in product_ids if int(product_id or 0)})
        except (TypeError, ValueError):
            return {'success': False, 'message': 'Produk tidak valid'}
        return {
            'success': True,
            'status': self._review_status_map(normalized_ids),
        }

    @http.route('/unitrade/reviews/create', type='json', auth='user', website=True, methods=['POST'])
    def create_review(self, **kwargs):
        try:
            product_id = int(kwargs.get('product_id') or 0)
            rating = int(kwargs.get('rating') or 0)
            order_id = int(kwargs.get('order_id') or 0)
        except (TypeError, ValueError):
            return {'success': False, 'message': 'Data ulasan tidak valid'}

        comment = (kwargs.get('comment') or '').strip()
        tags = kwargs.get('tags') or []
        if isinstance(tags, list):
            tag_values = [str(tag).strip() for tag in tags if str(tag).strip()]
        else:
            tag_values = [tag.strip() for tag in str(tags).split(',') if tag.strip()]
        tag_values = tag_values[:6]
        if rating < 1 or rating > 5:
            return {'success': False, 'message': 'Rating harus antara 1 sampai 5'}

        user_product_review = request.env['unitrade.review'].sudo().search([
            ('product_id', '=', product_id),
            ('user_id', '=', request.env.uid),
        ], limit=1)
        if user_product_review:
            return {
                'success': True,
                'message': 'Anda sudah memberikan ulasan untuk produk ini.',
                'review': self._review_payload(user_product_review),
                'summary': self._summary(product_id),
                'can_review': False,
                'already_reviewed': True,
            }

        order = self._eligible_order_for_review(product_id, order_id)
        if not order:
            return {
                'success': False,
                'message': 'Ulasan hanya bisa diberikan setelah pesanan produk ini selesai.',
            }

        existing_review = request.env['unitrade.review'].sudo().search([
            ('product_id', '=', product_id),
            ('order_id', '=', order.id),
        ], limit=1)
        if existing_review:
            return {
                'success': True,
                'message': 'Anda sudah memberikan ulasan untuk produk ini.',
                'review': self._review_payload(existing_review),
                'summary': self._summary(product_id),
                'can_review': False,
                'already_reviewed': True,
            }

        try:
            image_values = self._prepare_review_images(kwargs.get('images') or kwargs.get('image_data') or [])
        except ValueError as exc:
            return {'success': False, 'message': str(exc)}

        try:
            review = request.env['unitrade.review'].sudo().create({
                'product_id': product_id,
                'user_id': request.env.uid,
                'order_id': order.id,
                'rating': rating,
                'comment': comment,
                'review_tags': ', '.join(tag_values),
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
