from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class UnitradeReview(models.Model):
    _name = 'unitrade.review'
    _description = 'UniTrade Product Review'
    _order = 'create_date desc'
    _rec_name = 'product_id'

    product_id = fields.Many2one('product.template', string='Produk', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', string='Reviewer', required=True, default=lambda self: self.env.uid, index=True)
    order_id = fields.Many2one('sale.order', string='Pesanan', required=True)
    rating = fields.Integer(string='Rating', required=True, default=5)
    comment = fields.Text(string='Komentar')
    review_image = fields.Image(
        string='Gambar Ulasan',
        max_width=1920,
        max_height=1920,
        help='Gambar opsional yang diunggah bersama ulasan produk.',
    )
    review_image_mimetype = fields.Char(string='Tipe Gambar', readonly=True)
    review_image_2 = fields.Image(
        string='Gambar Ulasan 2',
        max_width=1920,
        max_height=1920,
        help='Gambar opsional kedua yang diunggah bersama ulasan produk.',
    )
    review_image_2_mimetype = fields.Char(string='Tipe Gambar 2', readonly=True)
    review_image_3 = fields.Image(
        string='Gambar Ulasan 3',
        max_width=1920,
        max_height=1920,
        help='Gambar opsional ketiga yang diunggah bersama ulasan produk.',
    )
    review_image_3_mimetype = fields.Char(string='Tipe Gambar 3', readonly=True)
    review_tags = fields.Char(string='Tag Ulasan')
    is_visible = fields.Boolean(string='Tampilkan', default=True)
    helpful_vote_ids = fields.One2many(
        'unitrade.review.helpful',
        'review_id',
        string='Vote Membantu',
        readonly=True,
    )
    helpful_count = fields.Integer(
        string='Jumlah Membantu',
        compute='_compute_interaction_counts',
    )
    report_ids = fields.One2many(
        'unitrade.review.report',
        'review_id',
        string='Laporan',
        readonly=True,
    )
    report_count = fields.Integer(
        string='Jumlah Laporan',
        compute='_compute_interaction_counts',
    )

    _sql_constraints = [
        ('order_unique', 'UNIQUE(order_id, product_id)', 'Anda sudah memberikan ulasan untuk produk ini pada pesanan ini!'),
        ('rating_range', 'CHECK(rating >= 1 AND rating <= 5)', 'Rating harus antara 1-5!'),
    ]

    def _compute_interaction_counts(self):
        helpful_counts = {review_id: 0 for review_id in self.ids}
        report_counts = {review_id: 0 for review_id in self.ids}

        if self.ids:
            helpful_rows = self.env['unitrade.review.helpful'].sudo().read_group(
                [('review_id', 'in', self.ids)],
                ['review_id'],
                ['review_id'],
            )
            report_rows = self.env['unitrade.review.report'].sudo().read_group(
                [('review_id', 'in', self.ids)],
                ['review_id'],
                ['review_id'],
            )
            for row in helpful_rows:
                review_value = row.get('review_id')
                if review_value:
                    helpful_counts[review_value[0]] = row.get('review_id_count', 0)
            for row in report_rows:
                review_value = row.get('review_id')
                if review_value:
                    report_counts[review_value[0]] = row.get('review_id_count', 0)

        for review in self:
            review.helpful_count = helpful_counts.get(review.id, 0)
            review.report_count = report_counts.get(review.id, 0)

    @api.model
    def _unitrade_refresh_product_review_stats(self, products):
        products = products.exists()
        if not products:
            return

        Review = self.sudo()
        for product in products.sudo():
            visible_reviews = Review.search([
                ('product_id', '=', product.id),
                ('is_visible', '=', True),
            ])
            review_count = len(visible_reviews)
            average_rating = (
                round(sum(visible_reviews.mapped('rating')) / review_count, 1)
                if review_count else 0.0
            )
            product.write({
                'x_average_rating': average_rating,
                'x_review_count': review_count,
            })

    def init(self):
        reviews = self.sudo().search([('product_id', '!=', False)])
        self._unitrade_refresh_product_review_stats(reviews.mapped('product_id'))

    @api.model_create_multi
    def create(self, vals_list):
        reviews = super().create(vals_list)
        self._unitrade_refresh_product_review_stats(reviews.mapped('product_id'))
        return reviews

    def write(self, vals):
        products_before = self.mapped('product_id')
        result = super().write(vals)
        if {'product_id', 'rating', 'is_visible'}.intersection(vals):
            self._unitrade_refresh_product_review_stats(products_before | self.mapped('product_id'))
        return result

    def unlink(self):
        products = self.mapped('product_id')
        result = super().unlink()
        self._unitrade_refresh_product_review_stats(products)
        return result

    @api.model
    def _unitrade_order_is_reviewable(self, order):
        if not order or order.state not in ('sale', 'done'):
            return False
        if 'x_payment_status' in order._fields and order.x_payment_status not in ('paid', 'refunded'):
            return False
        if 'x_unitrade_order_state' in order._fields:
            return order.x_unitrade_order_state in ('completed', 'refunded')
        return order.state == 'done'

    @api.model
    def _unitrade_repair_invalid_seed_reviews(self):
        invalid_reviews = self.sudo().browse()
        for review in self.sudo().search([]):
            if not self._unitrade_order_is_reviewable(review.order_id):
                invalid_reviews |= review
        if invalid_reviews:
            count = len(invalid_reviews)
            products = invalid_reviews.mapped('product_id')
            invalid_reviews.write({'is_visible': False})
            self._unitrade_refresh_product_review_stats(products)
            _logger.info('Hidden %s invalid UniTrade seed review(s).', count)
        return True

    @api.onchange('product_id', 'user_id')
    def _onchange_review_order_domain(self):
        domain = [('state', '=', 'done')]
        if self.user_id:
            domain.append(('partner_id', '=', self.user_id.partner_id.id))
        if self.product_id:
            domain.append(('order_line.product_id.product_tmpl_id', '=', self.product_id.id))
        if self.order_id and self.order_id not in self.env['sale.order'].search(domain):
            self.order_id = False
        return {'domain': {'order_id': domain}}

    @api.constrains('order_id')
    def _check_order_done(self):
        for record in self:
            if not self._unitrade_order_is_reviewable(record.order_id):
                raise ValidationError(_('Ulasan hanya bisa diberikan untuk pesanan yang sudah selesai.'))

    def action_save_review(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tersimpan'),
                'message': _('Ulasan produk berhasil disimpan.'),
                'type': 'success',
                'sticky': False,
            },
        }


class UnitradeReviewHelpful(models.Model):
    _name = 'unitrade.review.helpful'
    _description = 'UniTrade Review Helpful Vote'
    _order = 'create_date desc'
    _rec_name = 'review_id'

    review_id = fields.Many2one(
        'unitrade.review',
        string='Ulasan',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one(
        'product.template',
        string='Produk',
        related='review_id.product_id',
        store=True,
        index=True,
        readonly=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user,
        ondelete='cascade',
        index=True,
    )

    _sql_constraints = [
        (
            'review_user_unique',
            'UNIQUE(review_id, user_id)',
            'User hanya bisa memberi satu vote membantu untuk setiap ulasan.',
        ),
    ]


class UnitradeReviewReport(models.Model):
    _name = 'unitrade.review.report'
    _description = 'UniTrade Review Report'
    _order = 'create_date desc'
    _rec_name = 'review_id'

    review_id = fields.Many2one(
        'unitrade.review',
        string='Ulasan',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one(
        'product.template',
        string='Produk',
        related='review_id.product_id',
        store=True,
        index=True,
        readonly=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Pelapor',
        required=True,
        default=lambda self: self.env.user,
        ondelete='cascade',
        index=True,
    )
    reason = fields.Selection(
        [
            ('spam', 'Spam atau promosi'),
            ('abuse', 'Bahasa kasar atau pelecehan'),
            ('irrelevant', 'Tidak relevan dengan produk'),
            ('fake', 'Ulasan palsu atau menyesatkan'),
            ('other', 'Lainnya'),
        ],
        string='Alasan',
        required=True,
    )
    note = fields.Text(string='Catatan Tambahan')
    review_rating = fields.Integer(string='Rating Ulasan', related='review_id.rating', readonly=True)
    review_comment = fields.Text(string='Komentar Ulasan', related='review_id.comment', readonly=True)
    state = fields.Selection(
        [
            ('submitted', 'Terkirim'),
            ('under_review', 'Ditinjau'),
            ('resolved', 'Selesai'),
            ('rejected', 'Ditolak'),
        ],
        string='Status',
        default='submitted',
        required=True,
        index=True,
    )
    reviewed_by_id = fields.Many2one('res.users', string='Direview Oleh', readonly=True)
    reviewed_date = fields.Datetime(string='Tanggal Review', readonly=True)

    _sql_constraints = [
        (
            'review_report_user_unique',
            'UNIQUE(review_id, user_id)',
            'Anda sudah melaporkan ulasan ini.',
        ),
    ]

    def action_start_review(self):
        for report in self:
            report.write({
                'state': 'under_review',
                'reviewed_by_id': self.env.user.id,
                'reviewed_date': fields.Datetime.now(),
            })

    def action_mark_resolved(self):
        for report in self:
            report.write({
                'state': 'resolved',
                'reviewed_by_id': self.env.user.id,
                'reviewed_date': fields.Datetime.now(),
            })

    def action_reject(self):
        for report in self:
            report.write({
                'state': 'rejected',
                'reviewed_by_id': self.env.user.id,
                'reviewed_date': fields.Datetime.now(),
            })
