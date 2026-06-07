import json
import logging
from datetime import timedelta
from urllib.parse import quote_plus

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class UnitradeAdminStats(models.AbstractModel):
    """Aggregator service for UniTrade admin dashboard.

    Exposes a single :meth:`get_dashboard_data` JSON-friendly RPC that the OWL
    client calls once on mount. Keeping aggregation here (instead of a dozen
    smaller calls) keeps the dashboard responsive and the client code simple.
    """

    _name = 'unitrade.admin.stats'
    _description = 'UniTrade Admin Dashboard Aggregator'

    # ---- access guard ------------------------------------------------------

    @api.model
    def _check_admin(self):
        user = self.env.user
        if user.has_group('base.group_system') or user.has_group(
            'unitrade_seller.group_unitrade_admin'
        ):
            return
        raise AccessError(_('Hanya admin UniTrade yang dapat membuka dashboard ini.'))

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _safe_count(model, domain):
        try:
            return model.search_count(domain)
        except Exception:  # noqa: BLE001 - keep dashboard resilient
            _logger.exception('Failed counting %s with domain %s', model, domain)
            return 0

    def _has_model(self, model_name):
        return model_name in self.env

    def _current_admin_user(self):
        uid = self.env.context.get('unitrade_admin_user_id') or self.env.uid
        user = self.env['res.users'].sudo().browse(uid).exists()
        return user or self.env.user

    def _notification_domain(self):
        return [
            ('audience', '=', 'admin'),
            ('user_id', '=', self._current_admin_user().id),
        ]

    def _notification_model(self):
        return self.env['unitrade.notification'].sudo() if self._has_model('unitrade.notification') else None

    def _unitrade_admin_group(self):
        return self.env.ref('unitrade_seller.group_unitrade_admin', raise_if_not_found=False)

    def _is_unitrade_admin_user(self, user):
        group = self._unitrade_admin_group()
        system_group = self.env.ref('base.group_system', raise_if_not_found=False)
        return bool(
            user
            and ((group and group in user.groups_id) or (system_group and system_group in user.groups_id))
        )

    def _marketplace_user_domain(self):
        """Return users relevant for UniTrade admin, including portal buyers."""
        public_user = self.env.ref('base.public_user', raise_if_not_found=False)
        domain = []
        if public_user:
            domain.append(('id', '!=', public_user.id))
        return domain

    def _verification_status_for_admin(self, verification):
        """Map seller verification records into admin queue states."""
        if not verification:
            return 'unverified'
        if verification.state in ('pending', 'manual_review'):
            return 'pending'
        if verification.state == 'approved':
            return 'verified'
        if verification.state == 'rejected':
            reason = (verification.rejection_reason or '').lower()
            raw = (verification.ocr_raw_text or '').lower()
            if 'ocr' in reason or 'vision_api_failed' in reason or 'api error' in raw:
                return 'pending'
            return 'rejected'
        return 'unverified'

    def _customer_service_counts(self):
        ChatReport = (
            self.env['unitrade.chat.report'].sudo()
            if self._has_model('unitrade.chat.report') else None
        )
        Dispute = (
            self.env['unitrade.dispute'].sudo()
            if self._has_model('unitrade.dispute') else None
        )
        Seller = (
            self.env['unitrade.seller'].sudo()
            if self._has_model('unitrade.seller') else None
        )
        Order = self.env['sale.order'].sudo()
        Ticket = (
            self.env['unitrade.customer.ticket'].sudo()
            if self._has_model('unitrade.customer.ticket') else None
        )

        chat_open = (
            self._safe_count(ChatReport, [('state', 'in', ('submitted', 'under_review'))])
            if ChatReport is not None else 0
        )
        ticket_open = (
            self._safe_count(Ticket, [('status', 'in', ('pending', 'in_progress'))])
            if Ticket is not None else 0
        )
        ticket_pending = (
            self._safe_count(Ticket, [('status', '=', 'pending')])
            if Ticket is not None else 0
        )
        dispute_states = (
            'submitted',
            'under_review',
            'need_buyer_evidence',
            'need_seller_response',
            'admin_review_final',
        )
        disputes_active = (
            self._safe_count(Dispute, [('state', 'in', dispute_states)])
            if Dispute is not None else 0
        )
        disputes_overdue = (
            self._safe_count(Dispute, [('state', 'in', dispute_states), ('is_overdue', '=', True)])
            if Dispute is not None and 'is_overdue' in Dispute._fields else 0
        )
        seller_reports = (
            self._safe_count(Seller, [('report_state', 'in', ('reported', 'under_review'))])
            if Seller is not None and 'report_state' in Seller._fields else 0
        )
        flagged_orders = (
            self._safe_count(Order, [('x_admin_flagged', '=', True)])
            if 'x_admin_flagged' in Order._fields else 0
        )

        return {
            'open_total': ticket_open + chat_open + disputes_active + seller_reports + flagged_orders,
            'urgent': ticket_pending + chat_open + disputes_overdue + flagged_orders,
            'ticket_open': ticket_open,
            'ticket_pending': ticket_pending,
            'chat_open': chat_open,
            'disputes_active': disputes_active,
            'disputes_overdue': disputes_overdue,
            'seller_reports': seller_reports,
            'flagged_orders': flagged_orders,
        }

    def _notification_summary(self):
        Notification = self._notification_model()
        if Notification is None:
            return {'total': 0, 'unread': 0, 'urgent': 0, 'warning': 0, 'read': 0}
        domain = self._notification_domain()
        return {
            'total': self._safe_count(Notification, domain),
            'unread': self._safe_count(Notification, domain + [('is_read', '=', False)]),
            'urgent': self._safe_count(Notification, domain + [
                ('is_read', '=', False),
                ('priority', 'in', ('urgent', 'critical')),
            ]),
            'warning': self._safe_count(Notification, domain + [
                ('is_read', '=', False),
                ('priority', '=', 'warning'),
            ]),
            'read': self._safe_count(Notification, domain + [('is_read', '=', True)]),
        }

    # ---- main payload ------------------------------------------------------

    @api.model
    def get_dashboard_data(self):
        """Return a JSON-serialisable dict consumed by the OWL dashboard."""
        self._check_admin()

        Users = self.env['res.users'].sudo()
        Seller = self.env['unitrade.seller'].sudo() if self._has_model('unitrade.seller') else None
        Order = self.env['sale.order'].sudo()
        Product = self.env['product.template'].sudo()
        Voucher = (
            self.env['unitrade.voucher'].sudo().with_context(active_test=False)
            if self._has_model('unitrade.voucher') else None
        )
        Sponsorship = (
            self.env['unitrade.sponsorship.request'].sudo()
            if self._has_model('unitrade.sponsorship.request') else None
        )
        Review = (
            self.env['unitrade.review'].sudo()
            if self._has_model('unitrade.review') else None
        )
        Payout = (
            self.env['unitrade.seller.payout'].sudo()
            if self._has_model('unitrade.seller.payout') else None
        )
        Announcement = (
            self.env['unitrade.announcement'].sudo()
            if self._has_model('unitrade.announcement') else None
        )

        today = fields.Date.context_today(self)
        seven_days_ago = today - timedelta(days=6)

        # --- counters --------------------------------------------------------
        marketplace_user_domain = self._marketplace_user_domain()
        total_users = self._safe_count(Users, marketplace_user_domain)
        unitrade_admin_group = self._unitrade_admin_group()
        admin_users = (
            self._safe_count(Users, [('groups_id', 'in', unitrade_admin_group.id)])
            if unitrade_admin_group else 0
        )
        # Marketplace users = portal/internal users that are not blocked
        marketplace_users = self._safe_count(
            Users,
            marketplace_user_domain + [
                ('active', '=', True),
                ('x_unitrade_is_blocked', '=', False),
            ],
        ) if 'x_unitrade_is_blocked' in Users._fields else total_users

        blocked_users = (
            self._safe_count(Users, marketplace_user_domain + [('x_unitrade_is_blocked', '=', True)])
            if 'x_unitrade_is_blocked' in Users._fields
            else 0
        )

        verified_sellers = self._safe_count(Seller, [('status', '=', 'verified')]) if Seller is not None else 0
        pending_ktm = self._safe_count(Seller, [('status', '=', 'pending')]) if Seller is not None else 0
        if self._has_model('unitrade.seller.verification'):
            pending_ktm += len(
                self.env['unitrade.seller.verification'].sudo().search(
                    [('state', 'in', ('pending', 'manual_review', 'rejected'))]
                ).filtered(
                    lambda verification: self._verification_status_for_admin(verification) == 'pending'
                )
            )
        rejected_sellers = self._safe_count(Seller, [('status', '=', 'rejected')]) if Seller is not None else 0
        reported_sellers = (
            self._safe_count(Seller, [('report_state', 'in', ('reported', 'under_review'))])
            if Seller is not None
            else 0
        )

        # --- products --------------------------------------------------------
        product_domain = self._marketplace_product_domain(Product)
        active_products = self._safe_count(Product, product_domain + [('active', '=', True)])
        archived_products = self._safe_count(Product, product_domain + [('active', '=', False)])

        # --- orders / transactions ------------------------------------------
        order_states = ['draft', 'sent', 'sale', 'done', 'cancel']
        recent_floor = fields.Datetime.to_datetime(seven_days_ago - timedelta(days=23))
        orders_by_state = {}
        for state in order_states:
            orders_by_state[state] = self._safe_count(
                Order, [('state', '=', state), ('create_date', '>=', recent_floor)]
            )

        total_orders = self._safe_count(Order, [])
        completed_orders = orders_by_state.get('sale', 0) + orders_by_state.get('done', 0)
        processing_orders = orders_by_state.get('sent', 0) + orders_by_state.get('draft', 0)
        cancelled_orders = orders_by_state.get('cancel', 0)
        # Refund / pending payment proxies (use payment_state if exists, else sale.order.invoice_status)
        pending_refunds = 0
        if 'x_payment_status' in Order._fields:
            pending_refunds = self._safe_count(Order, [('x_payment_status', '=', 'refunded')])

        vouchers_total = self._safe_count(Voucher, []) if Voucher is not None else 0
        vouchers_active = 0
        vouchers_expired = 0
        if Voucher is not None:
            now = fields.Datetime.now()
            active_voucher_domain = [
                ('active', '=', True),
                '|', ('date_start', '=', False), ('date_start', '<=', now),
                '|', ('date_end', '=', False), ('date_end', '>=', now),
            ]
            vouchers_active = self._safe_count(Voucher, active_voucher_domain)
            vouchers_expired = self._safe_count(Voucher, [
                ('date_end', '!=', False),
                ('date_end', '<', now),
            ])

        sponsorship_new = (
            self._safe_count(Sponsorship, [('status', '=', 'new')])
            if Sponsorship is not None else 0
        )
        reviews_hidden = (
            self._safe_count(Review, [('is_visible', '=', False)])
            if Review is not None else 0
        )
        payout_pending = (
            self._safe_count(Payout, [('state', 'in', ('draft', 'ready'))])
            if Payout is not None else 0
        )
        refunds_need_admin = 0
        if self._has_model('unitrade.dispute'):
            Dispute = self.env['unitrade.dispute'].sudo()
            refunds_need_admin = self._safe_count(Dispute, [('state', '=', 'admin_review_final')])
        announcements_draft = (
            self._safe_count(Announcement, [('state', '=', 'draft')])
            if Announcement is not None else 0
        )

        audit_critical = 0
        if self._has_model('unitrade.admin.audit.log'):
            AuditLog = self.env['unitrade.admin.audit.log'].sudo()
            audit_critical = self._safe_count(AuditLog, [('severity', '=', 'critical')])

        # --- GMV --------------------------------------------------------------
        gmv_total = 0.0
        gmv_series = []
        try:
            self.env.cr.execute(
                """
                SELECT date_trunc('day', create_date)::date AS day,
                       COALESCE(SUM(amount_total), 0)       AS total
                  FROM sale_order
                 WHERE state IN ('sale', 'done')
                   AND create_date::date >= %s
                 GROUP BY day
                 ORDER BY day
                """,
                [seven_days_ago],
            )
            rows = {r['day']: r['total'] for r in self.env.cr.dictfetchall()}
            for offset in range(7):
                day = seven_days_ago + timedelta(days=offset)
                value = float(rows.get(day, 0) or 0)
                gmv_total += value
                gmv_series.append({
                    'date': fields.Date.to_string(day),
                    'label': day.strftime('%d %b'),
                    'value': value,
                })
        except Exception:  # noqa: BLE001
            _logger.exception('Failed computing GMV series')

        # GMV change vs previous 7-day window
        gmv_prev_total = 0.0
        try:
            self.env.cr.execute(
                """
                SELECT COALESCE(SUM(amount_total), 0) AS total
                  FROM sale_order
                 WHERE state IN ('sale', 'done')
                   AND create_date::date >= %s
                   AND create_date::date < %s
                """,
                [seven_days_ago - timedelta(days=7), seven_days_ago],
            )
            prev = self.env.cr.fetchone()
            gmv_prev_total = float(prev[0] or 0) if prev else 0.0
        except Exception:  # noqa: BLE001
            _logger.exception('Failed computing previous GMV total')

        if gmv_prev_total > 0:
            gmv_change_pct = ((gmv_total - gmv_prev_total) / gmv_prev_total) * 100
        else:
            gmv_change_pct = 0.0 if gmv_total == 0 else 100.0

        # --- task queue ------------------------------------------------------
        tasks = []
        if pending_ktm:
            tasks.append({
                'urgency': 'urgent',
                'title': _('%s Pengajuan Verifikasi KTM Belum Diproses') % pending_ktm,
                'description': _('Seller mahasiswa menunggu verifikasi KTM.'),
                'badge': _('Urgent'),
                'badge_class': 'badge-red',
                'action': 'pending_ktm',
            })
        if reported_sellers:
            tasks.append({
                'urgency': 'warning',
                'title': _('%s Seller Dilaporkan Belum Ditinjau') % reported_sellers,
                'description': _('Laporan seller perlu ditangani sebelum verifikasi dicabut.'),
                'badge': _('Warning'),
                'badge_class': 'badge-yellow',
                'action': 'reported_sellers',
            })
        if pending_refunds:
            tasks.append({
                'urgency': 'urgent',
                'title': _('%s Permintaan Refund Belum Ditinjau') % pending_refunds,
                'description': _('Pembeli menunggu putusan refund.'),
                'badge': _('Urgent'),
                'badge_class': 'badge-red',
                'action': 'refunds',
            })
        if not tasks:
            tasks.append({
                'urgency': 'info',
                'title': _('Tidak ada tugas mendesak'),
                'description': _('Semua antrian admin sedang kosong. Selamat berbelanja informasi.'),
                'badge': _('Aman'),
                'badge_class': 'badge-green',
                'action': '',
            })

        self._sync_admin_notifications_from_tasks()
        cs_counts = self._customer_service_counts()

        # --- response --------------------------------------------------------
        return {
            'today': fields.Date.to_string(today),
            'user_name': self._current_admin_user().name,
            'counts': {
                'users_total': total_users,
                'users_active': marketplace_users,
                'users_blocked': blocked_users,
                'users_admin': admin_users,
                'sellers_verified': verified_sellers,
                'sellers_pending': pending_ktm,
                'sellers_rejected': rejected_sellers,
                'sellers_reported': reported_sellers,
                'products_active': active_products,
                'products_archived': archived_products,
                'orders_total': total_orders,
                'orders_completed': completed_orders,
                'orders_processing': processing_orders,
                'orders_cancelled': cancelled_orders,
                'refunds_pending': pending_refunds,
                'vouchers_total': vouchers_total,
                'vouchers_active': vouchers_active,
                'vouchers_expired': vouchers_expired,
                'customer_service_open': cs_counts['open_total'],
                'customer_service_urgent': cs_counts['urgent'],
                'sponsorship_new': sponsorship_new,
                'reviews_hidden': reviews_hidden,
                'payout_pending': payout_pending,
                'refunds_need_admin': refunds_need_admin,
                'announcements_draft': announcements_draft,
                'audit_critical': audit_critical,
            },
            'gmv': {
                'total_idr': gmv_total,
                'total_idr_display': self._format_idr(gmv_total),
                'change_pct': gmv_change_pct,
                'change_pct_abs': abs(gmv_change_pct),
                'change_is_up': gmv_change_pct >= 0,
                'series': gmv_series,
            },
            'tasks': tasks,
            'notifications': self._notification_summary(),
        }

    @staticmethod
    def _format_idr(value):
        """Indonesian-style thousand separator using dots."""
        n = int(round(float(value or 0)))
        return f'{n:,}'.replace(',', '.')

    @staticmethod
    def _float_value(value, default=0.0):
        try:
            if value in (None, ''):
                return default
            return max(0.0, float(str(value).strip().replace(',', '.')))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _int_value(value, default=0):
        try:
            if value in (None, ''):
                return default
            return max(0, int(float(str(value).strip().replace(',', '.'))))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _bool_value(value, default=True):
        if value in (None, ''):
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'aktif')

    def _user_timezone(self):
        tz_name = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        try:
            return pytz.timezone(tz_name)
        except Exception:  # noqa: BLE001
            return pytz.UTC

    def _parse_datetime_value(self, value):
        value = (value or '').strip()
        if not value:
            return False
        value = value.replace('T', ' ')
        if len(value) == 16:
            value += ':00'
        try:
            local_dt = fields.Datetime.from_string(value)
        except Exception:  # noqa: BLE001
            return False
        if not local_dt:
            return False
        if local_dt.tzinfo:
            return local_dt.astimezone(pytz.UTC).replace(tzinfo=None)
        local_tz = self._user_timezone()
        try:
            localized = local_tz.localize(local_dt, is_dst=None)
        except Exception:  # noqa: BLE001
            localized = local_tz.localize(local_dt)
        return localized.astimezone(pytz.UTC).replace(tzinfo=None)

    def _datetime_label(self, value):
        if not value:
            return '-'
        try:
            local_dt = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(value))
            return local_dt.strftime('%d %b %Y %H:%M')
        except Exception:  # noqa: BLE001
            return fields.Datetime.to_string(value)

    def _datetime_input_value(self, value):
        if not value:
            return ''
        try:
            local_dt = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(value))
            return local_dt.strftime('%Y-%m-%dT%H:%M')
        except Exception:  # noqa: BLE001
            return ''

    def _voucher_status(self, voucher, now=None):
        now = now or fields.Datetime.now()
        if not voucher.active:
            return ('inactive', _('Nonaktif'), 'gray')
        if voucher.date_start and voucher.date_start > now:
            return ('scheduled', _('Terjadwal'), 'yellow')
        if voucher.date_end and voucher.date_end < now:
            return ('expired', _('Kedaluwarsa'), 'red')
        return ('active', _('Aktif'), 'green')

    def _product_status_meta(self, product):
        if 'x_listing_status' in product._fields:
            status = product.x_listing_status or 'draft'
            label = self._selection_label(product, 'x_listing_status')
            if status == 'draft' and self._product_awaits_listing_fee(product):
                status, label = 'fee_pending', _('Menunggu Fee')
        elif not product.active:
            status, label = 'archived', _('Diarsipkan')
        elif self._product_awaits_listing_fee(product):
            status, label = 'fee_pending', _('Menunggu Fee')
        elif getattr(product, 'website_published', False):
            status, label = 'published', _('Terpublikasi')
        else:
            status, label = 'draft', _('Draft')
        badge = {
            'published': 'green',
            'fee_pending': 'yellow',
            'expired': 'yellow',
            'rejected': 'red',
            'archived': 'gray',
            'draft': 'blue',
        }.get(status, 'gray')
        return status, label, badge

    def _product_fee_status_meta(self, product):
        if 'x_listing_fee_status' not in product._fields:
            return 'not_required', _('Tidak Wajib'), 'gray'
        status = product.x_listing_fee_status or 'not_required'
        if status == 'not_required' and self._product_awaits_listing_fee(product):
            return 'unpaid', _('Belum Bayar'), 'yellow'
        label = self._selection_label(product, 'x_listing_fee_status')
        badge = {
            'paid': 'green',
            'waived': 'green',
            'unpaid': 'yellow',
            'pending': 'yellow',
            'failed': 'red',
            'not_required': 'gray',
        }.get(status, 'gray')
        return status, label, badge

    @staticmethod
    def _or_domain(leaves):
        leaves = [leaf for leaf in leaves if leaf]
        if not leaves:
            return []
        if len(leaves) == 1:
            return leaves
        return ['|'] * (len(leaves) - 1) + leaves

    @staticmethod
    def _marketplace_product_domain(Product):
        if 'x_is_marketplace' in Product._fields:
            return [('x_is_marketplace', '=', True)]
        return [('sale_ok', '=', True)]

    @staticmethod
    def _product_awaits_listing_fee(product):
        return bool(
            getattr(product, 'active', False)
            and getattr(product, 'x_is_marketplace', False)
            and not getattr(product, 'sale_ok', True)
        )

    def _expected_listing_fee_for_product(self, product):
        Config = self.env['ir.config_parameter'].sudo()
        if not self._bool_value(Config.get_param('unitrade.seller.listing_fee.enabled', 'True'), True):
            return 0.0
        threshold = self._float_value(Config.get_param('unitrade.seller.listing_fee.threshold', '1000000'), 1000000.0)
        low_fee = self._float_value(Config.get_param('unitrade.seller.listing_fee.low_amount', '2000'), 2000.0)
        high_fee = self._float_value(Config.get_param('unitrade.seller.listing_fee.high_amount', '5000'), 5000.0)
        price = product.list_price or 0.0
        if hasattr(product, '_unitrade_discounted_price'):
            try:
                price = product._unitrade_discounted_price()
            except Exception:  # noqa: BLE001 - display helper must not break admin page
                price = product.list_price or 0.0
        return high_fee if price >= threshold else low_fee

    # ---- products list -----------------------------------------------------

    @api.model
    def get_products_page(self, query='', status='', fee_status='', page=1, page_size=20):
        """Return paginated marketplace products for the admin UI."""
        self._check_admin()
        Product = self.env['product.template'].sudo().with_context(active_test=False)
        now = fields.Datetime.now()

        domain = self._marketplace_product_domain(Product)

        if query:
            search_leaves = [('name', 'ilike', query)]
            if 'default_code' in Product._fields:
                search_leaves.append(('default_code', 'ilike', query))
            if 'x_seller_name' in Product._fields:
                search_leaves.append(('x_seller_name', 'ilike', query))
            elif 'x_seller_id' in Product._fields:
                search_leaves.append(('x_seller_id.name', 'ilike', query))
            domain += self._or_domain(search_leaves)

        if status:
            if 'x_listing_status' in Product._fields:
                if status == 'fee_pending':
                    domain += ['|', ('x_listing_status', '=', status), ('sale_ok', '=', False)]
                else:
                    domain.append(('x_listing_status', '=', status))
            elif status == 'published':
                domain += [('active', '=', True), ('website_published', '=', True)]
            elif status == 'archived':
                domain.append(('active', '=', False))
            elif status == 'draft':
                domain += [('active', '=', True), ('website_published', '=', False)]

        if fee_status and 'x_listing_fee_status' in Product._fields:
            if fee_status == 'unpaid':
                domain += ['|', ('x_listing_fee_status', '=', fee_status), ('sale_ok', '=', False)]
            else:
                domain.append(('x_listing_fee_status', '=', fee_status))

        total = Product.search_count(domain)
        page = max(1, int(page or 1))
        page_size = max(5, min(int(page_size or 20), 100))
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        products = Product.search(domain, limit=page_size, offset=offset, order='create_date desc, id desc')

        base_domain = self._marketplace_product_domain(Product)
        published_domain = [('active', '=', True), ('website_published', '=', True)]
        fee_pending_domain = []
        expired_domain = []
        if 'x_listing_status' in Product._fields:
            published_domain = [('x_listing_status', '=', 'published')]
            fee_pending_domain = ['|', ('x_listing_status', '=', 'fee_pending'), ('sale_ok', '=', False)]
            expired_domain = [('x_listing_status', '=', 'expired')]
        elif 'x_listing_fee_status' in Product._fields:
            fee_pending_domain = ['|', ('x_listing_fee_status', 'in', ('unpaid', 'pending')), ('sale_ok', '=', False)]
        elif 'x_listing_expires_at' in Product._fields:
            expired_domain = [('x_listing_expires_at', '!=', False), ('x_listing_expires_at', '<', now)]

        stats = {
            'total': Product.search_count(base_domain),
            'published': Product.search_count(base_domain + published_domain),
            'fee_pending': Product.search_count(base_domain + fee_pending_domain) if fee_pending_domain else 0,
            'fee_not_required': (
                Product.search_count(base_domain + [('x_listing_fee_status', '=', 'not_required'), ('sale_ok', '=', True)])
                if 'x_listing_fee_status' in Product._fields else 0
            ),
            'expired': Product.search_count(base_domain + expired_domain) if expired_domain else 0,
            'archived': Product.search_count(base_domain + [('active', '=', False)]),
        }

        rows = []
        for product in products:
            listing_status, listing_label, listing_badge = self._product_status_meta(product)
            fee_key, fee_label, fee_badge = self._product_fee_status_meta(product)
            seller = product.x_seller_id if 'x_seller_id' in product._fields else False
            stock_qty = getattr(product, 'x_unitrade_stock_qty', False)
            free_qty = getattr(product, 'x_unitrade_free_qty', False)
            stock_label = '-'
            if stock_qty is not False:
                stock_label = '%g' % (stock_qty or 0.0)
                if free_qty is not False:
                    stock_label = '%s tersedia / %g stok' % (('%g' % (free_qty or 0.0)), stock_qty or 0.0)

            rows.append({
                'id': product.id,
                'name': product.display_name or product.name or '',
                'image_url': '/web/image/product.template/%s/image_128' % product.id,
                'seller_name': seller.name if seller else (getattr(product, 'x_seller_name', '') or '-'),
                'seller_initials': self._initials(seller.name if seller else getattr(product, 'x_seller_name', '')),
                'seller_url': '/web#id=%s&model=unitrade.seller&view_type=form' % seller.id if seller else '',
                'condition_label': self._selection_label(product, 'x_condition') if 'x_condition' in product._fields else '-',
                'price_display': 'Rp ' + self._format_idr(product.list_price),
                'stock_label': stock_label,
                'listing_status': listing_status,
                'listing_status_label': listing_label,
                'listing_badge_class': listing_badge,
                'fee_status': fee_key,
                'fee_status_label': fee_label,
                'fee_badge_class': fee_badge,
                'published': bool(getattr(product, 'website_published', False)),
                'active': bool(product.active),
                'create_date_label': product.create_date.strftime('%d %b %Y') if product.create_date else '-',
                'expires_label': self._datetime_label(product.x_listing_expires_at)
                if 'x_listing_expires_at' in product._fields else '-',
                'backend_url': '/web#id=%s&model=product.template&view_type=form' % product.id,
            })

        return {
            'rows': rows,
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages,
            'query': query or '',
            'status': status or '',
            'fee_status': fee_status or '',
            'stats': stats,
            'backend_list_url': '/web#action=unitrade_product_ext.action_unitrade_products',
        }

    def _product_image_payloads(self, product):
        images = []
        unique = fields.Datetime.to_string(product.write_date or product.create_date or fields.Datetime.now())
        if product.image_1920:
            images.append({
                'label': _('Foto Utama'),
                'url': '/web/image/product.template/%s/image_1024?unique=%s' % (product.id, quote_plus(unique)),
            })
        if 'product_template_image_ids' in product._fields:
            for image in product.product_template_image_ids.filtered('image_1920')[:5]:
                image_unique = fields.Datetime.to_string(image.write_date or image.create_date or fields.Datetime.now())
                images.append({
                    'label': image.name or _('Foto Tambahan'),
                    'url': '/web/image/product.image/%s/image_1024?unique=%s' % (
                        image.id,
                        quote_plus(image_unique),
                    ),
                })
        if not images:
            images.append({
                'label': _('Tidak Ada Foto'),
                'url': '/web/static/img/placeholder.png',
            })
        return images[:6]

    def _listing_fee_history(self, product):
        if not self._has_model('unitrade.payment.intent'):
            return []
        PaymentIntent = self.env['unitrade.payment.intent'].sudo()
        intents = PaymentIntent.search(
            [
                ('intent_type', '=', 'listing_fee'),
                ('product_template_id', '=', product.id),
            ],
            order='create_date desc, id desc',
            limit=8,
        )
        rows = []
        for intent in intents:
            rows.append({
                'id': intent.id,
                'name': intent.name or '-',
                'state': intent.state or '',
                'state_label': self._selection_label(intent, 'state'),
                'provider': self._selection_label(intent, 'provider') if intent.provider else '-',
                'method': intent.payment_method_label or intent.payment_method_code or '-',
                'amount': 'Rp ' + self._format_idr(intent.amount),
                'reference': (
                    intent.payment_reference
                    or intent.midtrans_order_id
                    or intent.xendit_reference_id
                    or '-'
                ),
                'created': self._datetime_label(intent.create_date),
                'expires_at': self._datetime_label(intent.expires_at),
                'paid_at': self._datetime_label(intent.paid_at),
                'error': self._short_text(intent.error_message or '', limit=120),
                'url': '/web#id=%s&model=unitrade.payment.intent&view_type=form' % intent.id,
            })
        return rows

    @api.model
    def get_product_detail(self, product_id):
        self._check_admin()
        Product = self.env['product.template'].sudo().with_context(active_test=False)
        product = Product.browse(int(product_id or 0)).exists()
        if not product:
            return {'ok': False, 'error': _('Produk tidak ditemukan.')}

        listing_status, listing_label, listing_badge = self._product_status_meta(product)
        fee_status, fee_label, fee_badge = self._product_fee_status_meta(product)
        seller = product.x_seller_id if 'x_seller_id' in product._fields else False
        stock_qty = getattr(product, 'x_unitrade_stock_qty', False)
        free_qty = getattr(product, 'x_unitrade_free_qty', False)
        stock_label = '-'
        if stock_qty is not False:
            stock_label = '%g stok' % (stock_qty or 0.0)
            if free_qty is not False:
                stock_label = '%g tersedia / %g stok' % (free_qty or 0.0, stock_qty or 0.0)

        fee_requires_waive = fee_status in ('unpaid', 'pending', 'failed')
        listing_fee_amount = getattr(product, 'x_listing_fee', 0.0)
        if not listing_fee_amount and fee_status in ('unpaid', 'pending'):
            listing_fee_amount = self._expected_listing_fee_for_product(product)
        can_publish = bool(
            product.active
            and not product.website_published
            and fee_status in ('paid', 'waived', 'not_required')
        )
        return {
            'ok': True,
            'id': product.id,
            'name': product.display_name or product.name or '-',
            'default_code': product.default_code or '',
            'category': product.categ_id.display_name or '-',
            'description': (
                product.description_sale
                or getattr(product, 'x_description', '')
                or getattr(product, 'description', '')
                or '-'
            ),
            'condition': self._selection_label(product, 'x_condition') if 'x_condition' in product._fields else '-',
            'brand': getattr(product, 'x_brand', '') or '-',
            'price': 'Rp ' + self._format_idr(product.list_price),
            'stock': stock_label,
            'active': bool(product.active),
            'published': bool(product.website_published),
            'listing_status': listing_status,
            'listing_status_label': listing_label,
            'listing_badge_class': listing_badge,
            'fee_status': fee_status,
            'fee_status_label': fee_label,
            'fee_badge_class': fee_badge,
            'listing_fee': 'Rp ' + self._format_idr(listing_fee_amount),
            'activated_at': self._datetime_label(getattr(product, 'x_listing_activated_at', False)),
            'expires_at': self._datetime_label(getattr(product, 'x_listing_expires_at', False)),
            'fee_paid_at': self._datetime_label(getattr(product, 'x_listing_fee_paid_at', False)),
            'waive_reason': getattr(product, 'x_listing_fee_waive_reason', '') or '',
            'rejection_reason': getattr(product, 'x_listing_rejection_reason', '') or '',
            'seller': {
                'id': seller.id if seller else 0,
                'name': seller.name if seller else (getattr(product, 'x_seller_name', '') or '-'),
                'status': self._selection_label(seller, 'status') if seller else '-',
                'email': seller.user_id.login if seller and seller.user_id else '',
                'nim': seller.nim if seller and 'nim' in seller._fields else '',
                'admin_user_url': (
                    '/unitrade/admin/users?q=%s' % quote_plus(seller.user_id.login or seller.user_id.name or '')
                    if seller and seller.user_id else ''
                ),
            },
            'images': self._product_image_payloads(product),
            'listing_fee_history': self._listing_fee_history(product),
            'public_url': '/unitrade/product/%s' % product.id if product.website_published else '',
            'backend_url': '/web#id=%s&model=product.template&view_type=form' % product.id,
            'actions': {
                'can_publish': can_publish,
                'can_unpublish': bool(product.website_published),
                'can_waive': fee_requires_waive,
                'can_reject': fee_status != 'failed',
                'publish_blocked_reason': (
                    _('Produk masih menunggu fee. Gunakan Waive Fee jika admin ingin membebaskan pembayaran.')
                    if fee_requires_waive else ''
                ),
            },
        }

    @api.model
    def admin_run_product_action(self, product_id, action='', reason='', publish_after=True):
        self._check_admin()
        Product = self.env['product.template'].sudo().with_context(active_test=False)
        product = Product.browse(int(product_id or 0)).exists()
        if not product:
            return {'ok': False, 'error': _('Produk tidak ditemukan.')}
        # Keep the real admin user for audit checks, while avoiding product ACL
        # friction from Sales/Inventory groups on the dashboard action.
        product_admin = product.with_user(self.env.user).sudo()

        action = (action or '').strip()
        reason = (reason or '').strip()
        try:
            if action == 'publish':
                fee_status, _, _ = self._product_fee_status_meta(product)
                if fee_status in ('unpaid', 'pending', 'failed'):
                    return {
                        'ok': False,
                        'error': _('Produk masih menunggu fee. Waive fee dulu jika admin ingin mempublikasikan manual.'),
                    }
                if hasattr(product, 'action_unitrade_publish_admin'):
                    product_admin.action_unitrade_publish_admin()
                else:
                    product_admin.write({'x_is_marketplace': True, 'sale_ok': True, 'website_published': True, 'active': True})
            elif action == 'unpublish':
                if hasattr(product, 'action_unitrade_unpublish_admin'):
                    product_admin.action_unitrade_unpublish_admin()
                else:
                    product_admin.write({'website_published': False})
            elif action == 'waive':
                if not reason:
                    return {'ok': False, 'error': _('Alasan waive fee wajib diisi.')}
                wizard = self.env['unitrade.product.waive.wizard'].create({
                    'product_id': product.id,
                    'reason': reason,
                    'publish_after': bool(publish_after),
                })
                wizard.action_confirm()
            elif action == 'reject':
                if not reason:
                    return {'ok': False, 'error': _('Alasan penolakan wajib diisi.')}
                wizard = self.env['unitrade.product.reject.wizard'].create({
                    'product_id': product.id,
                    'reason': reason,
                })
                wizard.action_confirm()
            else:
                return {'ok': False, 'error': _('Aksi produk tidak valid.')}
        except Exception as error:  # noqa: BLE001
            _logger.exception('Admin product action failed: %s', action)
            return {'ok': False, 'error': str(error)}
        return {'ok': True, 'id': product.id, 'action': action}

    # ---- vouchers list ----------------------------------------------------

    @api.model
    def get_vouchers_page(self, query='', status='', page=1, page_size=20):
        """Return paginated checkout vouchers for the admin UI."""
        self._check_admin()
        if not self._has_model('unitrade.voucher'):
            return {
                'rows': [],
                'page': 1,
                'page_size': int(page_size),
                'total': 0,
                'total_pages': 1,
                'query': query or '',
                'status': status or '',
                'stats': {
                    'total': 0,
                    'active': 0,
                    'expired': 0,
                    'scheduled': 0,
                    'inactive': 0,
                    'redemptions': 0,
                },
            }

        Voucher = self.env['unitrade.voucher'].sudo().with_context(active_test=False)
        Order = self.env['sale.order'].sudo()
        now = fields.Datetime.now()
        domain = []

        if query:
            domain += ['|', ('code', 'ilike', query), ('name', 'ilike', query)]

        active_domain = [
            ('active', '=', True),
            '|', ('date_start', '=', False), ('date_start', '<=', now),
            '|', ('date_end', '=', False), ('date_end', '>=', now),
        ]
        expired_domain = [('date_end', '!=', False), ('date_end', '<', now)]
        scheduled_domain = [
            ('active', '=', True),
            ('date_start', '!=', False),
            ('date_start', '>', now),
        ]
        inactive_domain = [('active', '=', False)]

        if status == 'active':
            domain += active_domain
        elif status == 'expired':
            domain += expired_domain
        elif status == 'scheduled':
            domain += scheduled_domain
        elif status == 'inactive':
            domain += inactive_domain

        total = Voucher.search_count(domain)
        page = max(1, int(page or 1))
        page_size = max(5, min(int(page_size or 20), 100))
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        vouchers = Voucher.search(domain, limit=page_size, offset=offset, order='active desc, date_end desc, id desc')

        redemption_domain = []
        if 'x_unitrade_voucher_id' in Order._fields:
            redemption_domain.append(('x_unitrade_voucher_id', '!=', False))
            redemption_domain.append(('state', 'in', ('sale', 'done')))
            if 'x_payment_status' in Order._fields:
                redemption_domain.append(('x_payment_status', 'not in', ('cancelled', 'failed', 'expired')))

        stats = {
            'total': Voucher.search_count([]),
            'active': Voucher.search_count(active_domain),
            'expired': Voucher.search_count(expired_domain),
            'scheduled': Voucher.search_count(scheduled_domain),
            'inactive': Voucher.search_count(inactive_domain),
            'redemptions': self._safe_count(Order, redemption_domain) if redemption_domain else 0,
        }

        rows = []
        for voucher in vouchers:
            status_key, status_label, badge_class = self._voucher_status(voucher, now=now)
            if voucher.discount_type == 'percent':
                discount_label = '%s%%' % ('%g' % (voucher.discount_percent or 0.0))
            else:
                discount_label = 'Rp ' + self._format_idr(voucher.discount_amount)
            usage_count = voucher._usage_count() if hasattr(voucher, '_usage_count') else 0
            usage_limit = voucher.usage_limit or 0
            period_start = self._datetime_label(voucher.date_start)
            period_end = self._datetime_label(voucher.date_end)
            rows.append({
                'id': voucher.id,
                'name': voucher.name or '',
                'code': voucher.code or '',
                'active': bool(voucher.active),
                'status': status_key,
                'status_label': status_label,
                'badge_class': badge_class,
                'discount_type': voucher.discount_type,
                'discount_label': discount_label,
                'discount_amount': voucher.discount_amount or 0.0,
                'discount_percent': voucher.discount_percent or 0.0,
                'min_order_amount': voucher.min_order_amount or 0.0,
                'min_order_display': 'Rp ' + self._format_idr(voucher.min_order_amount),
                'usage_count': usage_count,
                'usage_limit': usage_limit,
                'usage_label': '%s / %s' % (usage_count, usage_limit or 'Tanpa batas'),
                'usage_limit_per_user': voucher.usage_limit_per_user or 0,
                'period_label': '%s - %s' % (period_start, period_end),
                'date_start_label': period_start,
                'date_end_label': period_end,
                'date_start_input': self._datetime_input_value(voucher.date_start),
                'date_end_input': self._datetime_input_value(voucher.date_end),
            })

        return {
            'rows': rows,
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages,
            'query': query or '',
            'status': status or '',
            'stats': stats,
        }

    # ---- users list -------------------------------------------------------

    @api.model
    def get_users_page(self, query='', status='', seller_status='', page=1, page_size=20):
        """Return paginated users list for the admin UI."""
        self._check_admin()
        Users = self.env['res.users'].sudo()
        Seller = self.env['unitrade.seller'].sudo() if self._has_model('unitrade.seller') else None
        Verification = (
            self.env['unitrade.seller.verification'].sudo()
            if self._has_model('unitrade.seller.verification') else None
        )

        domain = self._marketplace_user_domain()

        if query:
            domain += ['|', '|',
                       ('name', 'ilike', query),
                       ('login', 'ilike', query),
                       ('partner_id.phone', 'ilike', query)]

        if status == 'aktif' and 'x_unitrade_is_blocked' in Users._fields:
            domain.append(('x_unitrade_is_blocked', '=', False))
        elif status == 'blokir' and 'x_unitrade_is_blocked' in Users._fields:
            domain.append(('x_unitrade_is_blocked', '=', True))

        # Seller status filter via seller record
        if seller_status and (Seller is not None or Verification is not None):
            user_ids = []
            if seller_status == 'verified':
                if Seller is not None:
                    user_ids += Seller.search([('status', '=', 'verified')]).mapped('user_id').ids
            elif seller_status == 'pending':
                if Seller is not None:
                    user_ids += Seller.search([('status', '=', 'pending')]).mapped('user_id').ids
                if Verification is not None:
                    partners = Verification.search([('state', 'in', ('pending', 'manual_review', 'rejected'))]).filtered(
                        lambda verification: self._verification_status_for_admin(verification) == 'pending'
                    ).mapped('partner_id').ids
                    if partners:
                        user_ids += Users.search([('partner_id', 'in', partners)]).ids
            elif seller_status == 'rejected':
                if Seller is not None:
                    user_ids += Seller.search([('status', '=', 'rejected')]).mapped('user_id').ids
                if Verification is not None:
                    partners = Verification.search([('state', '=', 'rejected')]).filtered(
                        lambda verification: self._verification_status_for_admin(verification) == 'rejected'
                    ).mapped('partner_id').ids
                    if partners:
                        user_ids += Users.search([('partner_id', 'in', partners)]).ids
            elif seller_status == 'unverified':
                user_ids_with_seller = Seller.search([]).mapped('user_id').ids if Seller is not None else []
                partner_ids_with_verification = Verification.search([]).mapped('partner_id').ids if Verification is not None else []
                if user_ids_with_seller:
                    domain.append(('id', 'not in', user_ids_with_seller))
                if partner_ids_with_verification:
                    domain.append(('partner_id', 'not in', partner_ids_with_verification))
            if seller_status != 'unverified':
                domain.append(('id', 'in', list(set(user_ids)) or [0]))

        total = Users.search_count(domain)
        page = max(1, int(page or 1))
        offset = (page - 1) * int(page_size)
        users = Users.search(domain, limit=int(page_size), offset=offset, order='create_date desc')

        # Pre-fetch sellers in one query for performance
        seller_by_user = {}
        if Seller is not None:
            sellers = Seller.search([('user_id', 'in', users.ids)])
            for s in sellers:
                seller_by_user[s.user_id.id] = s
        verification_by_partner = {}
        if Verification is not None:
            verifications = Verification.search(
                [('partner_id', 'in', users.mapped('partner_id').ids)],
                order='create_date desc',
            )
            for verification in verifications:
                verification_by_partner.setdefault(verification.partner_id.id, verification)

        rows = []
        for user in users:
            seller = seller_by_user.get(user.id)
            verification = verification_by_partner.get(user.partner_id.id) if user.partner_id else False
            seller_status_val = 'unverified'
            if seller:
                seller_status_val = seller.status  # draft/pending/verified/rejected/revoked
            elif verification:
                seller_status_val = self._verification_status_for_admin(verification)

            blocked = bool(getattr(user, 'x_unitrade_is_blocked', False))
            rows.append({
                'id': user.id,
                'name': user.name or '',
                'login': user.login or '',
                'email': user.email or user.login or '',
                'phone': (user.partner_id.phone or user.partner_id.mobile or '') if user.partner_id else '',
                'create_date': fields.Date.to_string(user.create_date) if user.create_date else '',
                'is_blocked': blocked,
                'block_reason': getattr(user, 'x_unitrade_block_reason', '') or '',
                'is_unitrade_admin': self._is_unitrade_admin_user(user),
                'seller_status': seller_status_val,
                'seller_id': seller.id if seller else False,
                'verification_id': verification.id if verification else False,
                'initials': self._initials(user.name),
            })

        total_pages = max(1, (total + int(page_size) - 1) // int(page_size))
        return {
            'rows': rows,
            'page': page,
            'page_size': int(page_size),
            'total': total,
            'total_pages': total_pages,
            'query': query,
            'status': status,
            'seller_status': seller_status,
        }

    # ---- transactions list ------------------------------------------------

    @api.model
    def get_transactions_page(self, query='', state='', date_from='', page=1, page_size=20):
        """Return paginated sale orders list."""
        self._check_admin()
        Order = self.env['sale.order'].sudo()

        domain = []
        if query:
            domain += ['|', '|',
                       ('name', 'ilike', query),
                       ('partner_id.name', 'ilike', query),
                       ('partner_invoice_id.name', 'ilike', query)]

        state_map = {
            'draft': ['draft', 'sent'],
            'processing': ['sale'],
            'done': ['done'],
            'cancelled': ['cancel'],
        }
        if state in state_map:
            domain.append(('state', 'in', state_map[state]))
        elif state == 'refund' and 'x_payment_status' in Order._fields:
            domain.append(('x_payment_status', '=', 'refunded'))
        elif state == 'flagged' and 'x_admin_flagged' in Order._fields:
            domain.append(('x_admin_flagged', '=', True))

        if date_from:
            try:
                domain.append(('create_date', '>=', date_from))
            except Exception:  # noqa: BLE001
                pass

        total = Order.search_count(domain)
        page = max(1, int(page or 1))
        offset = (page - 1) * int(page_size)
        orders = Order.search(domain, limit=int(page_size), offset=offset, order='create_date desc')

        # Today's quick stats (hari ini)
        today_start = fields.Datetime.to_datetime(fields.Date.context_today(self))
        today_count = self._safe_count(Order, [('create_date', '>=', today_start)])
        processing_count = self._safe_count(Order, [('state', '=', 'sale')])
        pending_payment_count = (
            self._safe_count(Order, [('x_payment_status', '=', 'pending')])
            if 'x_payment_status' in Order._fields else 0
        )
        refund_count = (
            self._safe_count(Order, [('x_payment_status', '=', 'refunded')])
            if 'x_payment_status' in Order._fields else 0
        )
        flagged_count = (
            self._safe_count(Order, [('x_admin_flagged', '=', True)])
            if 'x_admin_flagged' in Order._fields else 0
        )

        rows = []
        for order in orders:
            buyer = order.partner_id
            seller_name = ''
            seller_initials = '?'
            # Try to derive seller from first product line
            if order.order_line:
                template = order.order_line[0].product_id.product_tmpl_id
                if 'x_seller_id' in template._fields and template.x_seller_id:
                    seller_name = template.x_seller_id.name or ''
                    seller_initials = self._initials(seller_name)

            payment_status = getattr(order, 'x_payment_status', '') or ''
            rows.append({
                'id': order.id,
                'name': order.name,
                'buyer_name': buyer.name if buyer else '',
                'buyer_initials': self._initials(buyer.name) if buyer else '?',
                'seller_name': seller_name,
                'seller_initials': seller_initials,
                'product_summary': order.order_line[0].name[:80] if order.order_line else '-',
                'amount_display': 'Rp ' + self._format_idr(order.amount_total),
                'amount': order.amount_total,
                'state': order.state,
                'state_label': dict(order._fields['state'].selection).get(order.state, order.state),
                'payment_status': payment_status,
                'payment_status_label': (
                    dict(order._fields['x_payment_status'].selection).get(payment_status, payment_status)
                    if 'x_payment_status' in order._fields and payment_status else ''
                ),
                'is_flagged': bool(getattr(order, 'x_admin_flagged', False)),
                'create_date': fields.Datetime.to_string(order.create_date) if order.create_date else '',
                'create_date_label': order.create_date.strftime('%d %b %H:%M') if order.create_date else '',
            })

        total_pages = max(1, (total + int(page_size) - 1) // int(page_size))
        return {
            'rows': rows,
            'page': page,
            'page_size': int(page_size),
            'total': total,
            'total_pages': total_pages,
            'query': query,
            'state': state,
            'date_from': date_from,
            'stats': {
                'today': today_count,
                'processing': processing_count,
                'pending_payment': pending_payment_count,
                'refund': refund_count,
                'flagged': flagged_count,
            },
        }

    @staticmethod
    def _initials(name):
        if not name:
            return '?'
        parts = [p for p in name.split() if p]
        if not parts:
            return '?'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    # ---- write actions (called via JSON RPC) ------------------------------

    @api.model
    def admin_create_admin_user(self, values):
        self._check_admin()
        values = values or {}
        name = (values.get('name') or '').strip()
        email = (values.get('email') or values.get('login') or '').strip().lower()
        password = values.get('password') or ''
        note = (values.get('note') or '').strip()

        if not name:
            return {'ok': False, 'error': _('Nama admin wajib diisi.')}
        if not email or '@' not in email:
            return {'ok': False, 'error': _('Email/login admin tidak valid.')}

        Users = self.env['res.users'].sudo()
        admin_group = self._unitrade_admin_group()
        base_user_group = self.env.ref('base.group_user', raise_if_not_found=False)
        portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
        public_group = self.env.ref('base.group_public', raise_if_not_found=False)
        if not admin_group:
            return {'ok': False, 'error': _('Group admin UniTrade tidak ditemukan.')}

        existing = Users.search(['|', ('login', '=', email), ('email', '=', email)], limit=1)
        commands = []
        for group in (portal_group, public_group):
            if group:
                commands.append((3, group.id))
        for group in (base_user_group, admin_group):
            if group:
                commands.append((4, group.id))

        if existing:
            write_vals = {
                'name': name,
                'login': email,
                'email': email,
                'groups_id': commands,
            }
            if password:
                write_vals['password'] = password
            if 'x_unitrade_admin_note' in existing._fields and note:
                write_vals['x_unitrade_admin_note'] = note
            existing.write(write_vals)
            user = existing
            created = False
        else:
            if not password or len(password) < 8:
                return {
                    'ok': False,
                    'error': _('Password sementara minimal 8 karakter untuk akun admin baru.'),
                }
            group_ids = [group.id for group in (base_user_group, admin_group) if group]
            create_vals = {
                'name': name,
                'login': email,
                'email': email,
                'password': password,
                'groups_id': [(6, 0, group_ids)],
            }
            user = Users.create(create_vals)
            if 'x_unitrade_admin_note' in user._fields and note:
                user.write({'x_unitrade_admin_note': note})
            created = True

        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'admin.user.create' if created else 'admin.user.grant',
                _('Admin UniTrade %s untuk %s.') % (
                    _('dibuat') if created else _('diberi akses'),
                    user.login,
                ),
                record=user,
                severity='warning',
                payload={'created': created, 'login': user.login},
            )

        return {
            'ok': True,
            'created': created,
            'user_id': user.id,
            'message': (
                _('Akun admin baru berhasil dibuat.')
                if created else
                _('User yang sudah ada berhasil diberi role admin UniTrade.')
            ),
        }

    @api.model
    def admin_block_user(self, user_id, reason):
        self._check_admin()
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            raise AccessError(_('User tidak ditemukan.'))
        user._unitrade_apply_block(reason or _('Diblokir oleh admin via dashboard.'))
        return {'ok': True}

    @api.model
    def admin_unblock_user(self, user_id):
        self._check_admin()
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            raise AccessError(_('User tidak ditemukan.'))
        user.action_unitrade_unblock()
        return {'ok': True}

    @api.model
    def admin_approve_seller(self, seller_id):
        self._check_admin()
        if not self._has_model('unitrade.seller'):
            return {'ok': False, 'error': 'no seller model'}
        seller = self.env['unitrade.seller'].sudo().browse(int(seller_id))
        if not seller.exists():
            return {'ok': False, 'error': 'seller not found'}
        seller.action_verify()
        return {'ok': True}

    @api.model
    def admin_reject_seller(self, seller_id, reason):
        self._check_admin()
        if not self._has_model('unitrade.seller'):
            return {'ok': False, 'error': 'no seller model'}
        seller = self.env['unitrade.seller'].sudo().browse(int(seller_id))
        if not seller.exists():
            return {'ok': False, 'error': 'seller not found'}
        seller.write({'rejection_reason': reason or _('Ditolak oleh admin via dashboard.')})
        seller.action_reject()
        return {'ok': True}

    @api.model
    def admin_approve_verification(self, verification_id, nim=''):
        self._check_admin()
        if not self._has_model('unitrade.seller.verification'):
            return {'ok': False, 'error': 'no verification model'}
        verification = self.env['unitrade.seller.verification'].sudo().browse(int(verification_id))
        if not verification.exists():
            return {'ok': False, 'error': 'verification not found'}

        nim = (nim or '').strip()
        values = {}
        if not verification.nim_extracted:
            if not nim:
                return {
                    'ok': False,
                    'error_code': 'nim_required',
                    'error': _('OCR belum membaca NIM. Isi NIM dari foto KTM untuk approve manual.'),
                }
            values.update({
                'nim_extracted': nim,
                'nim_valid': True,
            })

            if self._has_model('unisa.student'):
                student = self.env['unisa.student'].sudo().search([('nim', '=', nim)], limit=1)
                if not student:
                    return {
                        'ok': False,
                        'error_code': 'nim_not_found',
                        'error': _('NIM %s tidak ditemukan di data mahasiswa UNISA.') % nim,
                    }
                values.update({
                    'nim_registered': True,
                    'student_name': student.name,
                })

        if not verification.name_match_token:
            values['name_match_token'] = 'manual_admin'
        if not verification.name_confidence:
            values['name_confidence'] = 1.0
        if values:
            review_note = verification.review_note or ''
            values['review_note'] = (
                (review_note + '\n' if review_note else '') +
                _('Approve manual dari dashboard admin.')
            )
            verification.write(values)

        try:
            verification.action_approve()
        except Exception as error:  # noqa: BLE001 - return readable error to admin UI
            _logger.exception('Admin approve verification %s failed', verification.id)
            return {'ok': False, 'error': str(error)}
        return {'ok': True}

    @api.model
    def admin_reject_verification(self, verification_id, reason):
        self._check_admin()
        if not self._has_model('unitrade.seller.verification'):
            return {'ok': False, 'error': 'no verification model'}
        verification = self.env['unitrade.seller.verification'].sudo().browse(int(verification_id))
        if not verification.exists():
            return {'ok': False, 'error': 'verification not found'}
        verification.write({'rejection_reason': reason or _('Ditolak oleh admin via dashboard.')})
        verification.action_reject()
        return {'ok': True}

    @api.model
    def admin_save_user_note(self, user_id, note):
        self._check_admin()
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'error': 'user not found'}
        if 'x_unitrade_admin_note' not in user._fields:
            return {'ok': False, 'error': 'note field unavailable'}
        user.write({'x_unitrade_admin_note': note or False})
        return {'ok': True}

    @api.model
    def admin_reset_seller_to_draft(self, seller_id):
        self._check_admin()
        if not self._has_model('unitrade.seller'):
            return {'ok': False, 'error': 'no seller model'}
        seller = self.env['unitrade.seller'].sudo().browse(int(seller_id))
        if not seller.exists():
            return {'ok': False, 'error': 'seller not found'}
        seller.action_reset_to_draft()
        return {'ok': True}

    @api.model
    def admin_resend_verification_email(self, user_id):
        """Re-send OTP/verification email to the user."""
        self._check_admin()
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'error': 'user not found'}
        if hasattr(user, 'action_send_otp'):
            user.action_send_otp()
            return {'ok': True}
        return {'ok': False, 'error': 'OTP not supported'}

    @api.model
    def admin_flag_order(self, order_id, reason):
        self._check_admin()
        order = self.env['sale.order'].sudo().browse(int(order_id))
        if not order.exists():
            return {'ok': False, 'error': 'order not found'}
        order.action_unitrade_admin_flag(reason)
        return {'ok': True}

    @api.model
    def admin_unflag_order(self, order_id):
        self._check_admin()
        order = self.env['sale.order'].sudo().browse(int(order_id))
        if not order.exists():
            return {'ok': False, 'error': 'order not found'}
        order.action_unitrade_admin_unflag()
        return {'ok': True}

    @api.model
    def admin_create_voucher(self, values):
        self._check_admin()
        if not self._has_model('unitrade.voucher'):
            return {'ok': False, 'error': 'voucher module unavailable'}
        if not isinstance(values, dict):
            return {'ok': False, 'error': 'Payload voucher tidak valid.'}

        Voucher = self.env['unitrade.voucher'].sudo().with_context(active_test=False)
        code = Voucher._normalize_code(values.get('code'))
        name = (values.get('name') or '').strip()
        discount_type = values.get('discount_type') if values.get('discount_type') in ('fixed', 'percent') else 'fixed'
        discount_amount = self._float_value(values.get('discount_amount'))
        discount_percent = self._float_value(values.get('discount_percent'))
        min_order_amount = self._float_value(values.get('min_order_amount'))
        usage_limit = self._int_value(values.get('usage_limit'))
        usage_limit_per_user = self._int_value(values.get('usage_limit_per_user'))
        date_start = self._parse_datetime_value(values.get('date_start'))
        date_end = self._parse_datetime_value(values.get('date_end'))

        if not name:
            return {'ok': False, 'error': 'Nama voucher wajib diisi.'}
        if not code:
            return {'ok': False, 'error': 'Kode voucher wajib diisi.'}
        if Voucher.search([('code', '=', code)], limit=1):
            return {'ok': False, 'error': 'Kode voucher sudah digunakan.'}
        if discount_type == 'fixed' and discount_amount <= 0:
            return {'ok': False, 'error': 'Nominal diskon wajib lebih dari 0.'}
        if discount_type == 'percent' and (discount_percent <= 0 or discount_percent > 100):
            return {'ok': False, 'error': 'Diskon persen harus di antara 0 sampai 100.'}
        if date_start and date_end and date_end < date_start:
            return {'ok': False, 'error': 'Tanggal berakhir tidak boleh lebih awal dari tanggal mulai.'}

        voucher = Voucher.create({
            'name': name,
            'code': code,
            'active': self._bool_value(values.get('active'), default=True),
            'discount_type': discount_type,
            'discount_amount': discount_amount if discount_type == 'fixed' else 0.0,
            'discount_percent': discount_percent if discount_type == 'percent' else 0.0,
            'min_order_amount': min_order_amount,
            'usage_limit': usage_limit,
            'usage_limit_per_user': usage_limit_per_user,
            'date_start': date_start or False,
            'date_end': date_end or False,
            'currency_id': self.env.company.currency_id.id,
        })

        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'voucher.create',
                description='Admin membuat voucher %s.' % voucher.code,
                record=voucher,
                severity='info',
            )
        return {'ok': True, 'id': voucher.id, 'code': voucher.code}

    @api.model
    def admin_update_voucher(self, voucher_id, values):
        self._check_admin()
        if not self._has_model('unitrade.voucher'):
            return {'ok': False, 'error': 'voucher module unavailable'}
        if not isinstance(values, dict):
            return {'ok': False, 'error': 'Payload voucher tidak valid.'}

        Voucher = self.env['unitrade.voucher'].sudo().with_context(active_test=False)
        voucher = Voucher.browse(int(voucher_id or values.get('voucher_id') or 0)).exists()
        if not voucher:
            return {'ok': False, 'error': 'voucher not found'}

        code = Voucher._normalize_code(values.get('code'))
        name = (values.get('name') or '').strip()
        discount_type = values.get('discount_type') if values.get('discount_type') in ('fixed', 'percent') else 'fixed'
        discount_amount = self._float_value(values.get('discount_amount'))
        discount_percent = self._float_value(values.get('discount_percent'))
        min_order_amount = self._float_value(values.get('min_order_amount'))
        usage_limit = self._int_value(values.get('usage_limit'))
        usage_limit_per_user = self._int_value(values.get('usage_limit_per_user'))
        date_start = self._parse_datetime_value(values.get('date_start'))
        date_end = self._parse_datetime_value(values.get('date_end'))

        if not name:
            return {'ok': False, 'error': 'Nama voucher wajib diisi.'}
        if not code:
            return {'ok': False, 'error': 'Kode voucher wajib diisi.'}
        duplicate = Voucher.search([('code', '=', code), ('id', '!=', voucher.id)], limit=1)
        if duplicate:
            return {'ok': False, 'error': 'Kode voucher sudah digunakan.'}
        if discount_type == 'fixed' and discount_amount <= 0:
            return {'ok': False, 'error': 'Nominal diskon wajib lebih dari 0.'}
        if discount_type == 'percent' and (discount_percent <= 0 or discount_percent > 100):
            return {'ok': False, 'error': 'Diskon persen harus di antara 0 sampai 100.'}
        if date_start and date_end and date_end < date_start:
            return {'ok': False, 'error': 'Tanggal berakhir tidak boleh lebih awal dari tanggal mulai.'}

        voucher.write({
            'name': name,
            'code': code,
            'active': self._bool_value(values.get('active'), default=bool(voucher.active)),
            'discount_type': discount_type,
            'discount_amount': discount_amount if discount_type == 'fixed' else 0.0,
            'discount_percent': discount_percent if discount_type == 'percent' else 0.0,
            'min_order_amount': min_order_amount,
            'usage_limit': usage_limit,
            'usage_limit_per_user': usage_limit_per_user,
            'date_start': date_start or False,
            'date_end': date_end or False,
        })

        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'voucher.update',
                description='Admin mengubah voucher %s.' % voucher.code,
                record=voucher,
                severity='info',
            )
        return {'ok': True, 'id': voucher.id, 'code': voucher.code}

    @api.model
    def admin_toggle_voucher(self, voucher_id, active=None):
        self._check_admin()
        if not self._has_model('unitrade.voucher'):
            return {'ok': False, 'error': 'voucher module unavailable'}
        Voucher = self.env['unitrade.voucher'].sudo().with_context(active_test=False)
        voucher = Voucher.browse(int(voucher_id or 0)).exists()
        if not voucher:
            return {'ok': False, 'error': 'voucher not found'}
        next_active = (not voucher.active) if active in (None, '') else self._bool_value(active, default=not voucher.active)
        voucher.write({'active': next_active})
        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'voucher.activate' if next_active else 'voucher.deactivate',
                description='Admin %s voucher %s.' % ('mengaktifkan' if next_active else 'menonaktifkan', voucher.code),
                record=voucher,
                severity='info',
            )
        return {'ok': True, 'id': voucher.id, 'active': voucher.active}

    # ---- settings (read/write via ir.config_parameter) --------------------

    SETTINGS_KEYS = [
        # listing fee
        'unitrade.seller.listing_fee.enabled',
        'unitrade.seller.listing_fee.threshold',
        'unitrade.seller.listing_fee.low_amount',
        'unitrade.seller.listing_fee.high_amount',
        'unitrade.seller.listing_fee.validity_days',
        'unitrade.seller.posting_admin_fee',
        # checkout / escrow
        'unitrade.cancel_window_minutes',
        'unitrade.auto_complete_hours',
        'unitrade.refund_window_days',
        'unitrade.dispute_response_hours',
        # payout
        'unitrade.payout.mode',
        'unitrade.payout.min',
        'unitrade.payout.fee',
        'unitrade.payout.instructions',
        # legal
        'unitrade.legal.terms_url',
        'unitrade.legal.refund_url',
        'unitrade.legal.protection_label',
        # integrations
        'unitrade.midtrans.server_key',
        'unitrade.midtrans.client_key',
        'unitrade.midtrans.is_production',
        'unitrade.xendit.secret_key',
        'unitrade.xendit.webhook_token',
        'unitrade.xendit.is_production',
        'unitrade.xendit.payment_expiry_minutes',
        'unitrade.mapbox_access_token',
        'unitrade.mapbox_style_url',
        'unitrade.mapbox.token',
        'unitrade.gosend.client_id',
        'unitrade.gosend.client_secret',
        'unitrade.gosend.credential',
        # notifications
        'unitrade.notify.ktm_threshold',
        'unitrade.notify.overdue_minutes',
    ]

    SETTINGS_DEFAULTS = {
        'unitrade.seller.listing_fee.enabled': 'True',
        'unitrade.seller.listing_fee.threshold': '1000000',
        'unitrade.seller.listing_fee.low_amount': '2000',
        'unitrade.seller.listing_fee.high_amount': '5000',
        'unitrade.seller.listing_fee.validity_days': '30',
        'unitrade.seller.posting_admin_fee': '0',
        'unitrade.xendit.is_production': 'False',
        'unitrade.xendit.payment_expiry_minutes': '30',
    }

    SETTINGS_NUMERIC_RULES = {
        'unitrade.seller.listing_fee.threshold': {
            'label': 'Batas Harga Produk',
            'min': 0,
        },
        'unitrade.seller.listing_fee.low_amount': {
            'label': 'Fee Harga di Bawah Batas',
            'min': 0,
        },
        'unitrade.seller.listing_fee.high_amount': {
            'label': 'Fee Harga di Atas/Sama Batas',
            'min': 0,
        },
        'unitrade.seller.listing_fee.validity_days': {
            'label': 'Masa Berlaku Listing',
            'min': 1,
        },
        'unitrade.seller.posting_admin_fee': {
            'label': 'Admin Fee Tambahan',
            'min': 0,
        },
        'unitrade.xendit.payment_expiry_minutes': {
            'label': 'Expired Pembayaran Xendit',
            'min': 1,
        },
    }

    @api.model
    def get_settings(self):
        self._check_admin()
        params = self.env['ir.config_parameter'].sudo()
        values = {
            key: params.get_param(key, self.SETTINGS_DEFAULTS.get(key, ''))
            for key in self.SETTINGS_KEYS
        }
        if not values.get('unitrade.mapbox_access_token') and values.get('unitrade.mapbox.token'):
            values['unitrade.mapbox_access_token'] = values['unitrade.mapbox.token']
        return values

    @api.model
    def save_settings(self, values):
        self._check_admin()
        params = self.env['ir.config_parameter'].sudo()
        if not isinstance(values, dict):
            return {'ok': False, 'error': 'invalid payload'}
        actor = self.env.user
        normalized_values = {}
        for key, value in values.items():
            if key not in self.SETTINGS_KEYS:
                continue
            numeric_rule = self.SETTINGS_NUMERIC_RULES.get(key)
            if numeric_rule:
                try:
                    numeric_value = float(value or 0)
                except (TypeError, ValueError):
                    return {
                        'ok': False,
                        'error': _('%s harus berupa angka.') % numeric_rule['label'],
                    }
                if numeric_value < numeric_rule['min']:
                    if numeric_rule['min'] == 1:
                        return {
                            'ok': False,
                            'error': _('%s minimal 1 hari.') % numeric_rule['label'],
                        }
                    return {
                        'ok': False,
                        'error': _('%s tidak boleh negatif.') % numeric_rule['label'],
                    }
                value = str(int(numeric_value))
            normalized_values[key] = '' if value is None else str(value)

        for key, value in normalized_values.items():
            params.set_param(key, '' if value is None else str(value))
        # audit
        _logger.info(
            'UniTrade settings updated by %s. Keys: %s',
            actor.name, list(normalized_values.keys()),
        )
        return {'ok': True}

    # ---- reports ----------------------------------------------------------

    @api.model
    def get_reports(self, date_from='', date_to=''):
        """Build aggregated reports for the chosen period."""
        self._check_admin()
        try:
            df = fields.Date.from_string(date_from) if date_from else None
        except Exception:  # noqa: BLE001
            df = None
        try:
            dt = fields.Date.from_string(date_to) if date_to else None
        except Exception:  # noqa: BLE001
            dt = None
        if not df:
            df = fields.Date.context_today(self) - timedelta(days=29)
        if not dt:
            dt = fields.Date.context_today(self)
        if dt < df:
            df, dt = dt, df

        df_dt = fields.Datetime.to_datetime(df)
        # exclusive upper bound = next day 00:00
        dt_exclusive = fields.Datetime.to_datetime(dt + timedelta(days=1))

        Order = self.env['sale.order'].sudo()
        Users = self.env['res.users'].sudo()
        Product = self.env['product.template'].sudo().with_context(active_test=False)
        Seller = self.env['unitrade.seller'].sudo() if self._has_model('unitrade.seller') else None
        Dispute = self.env['unitrade.dispute'].sudo() if self._has_model('unitrade.dispute') else None
        PaymentIntent = (
            self.env['unitrade.payment.intent'].sudo()
            if self._has_model('unitrade.payment.intent') else None
        )
        Ticket = (
            self.env['unitrade.customer.ticket'].sudo()
            if self._has_model('unitrade.customer.ticket') else None
        )
        Sponsorship = (
            self.env['unitrade.sponsorship.request'].sudo()
            if self._has_model('unitrade.sponsorship.request') else None
        )
        period_domain = [('create_date', '>=', df_dt), ('create_date', '<', dt_exclusive)]

        # --- Transactions ---------------------------------------------------
        total_orders = self._safe_count(Order, period_domain)
        pending_payment = self._safe_count(Order, period_domain + [('state', 'in', ('draft', 'sent'))])
        processing = self._safe_count(Order, period_domain + [('state', '=', 'sale')])
        completed = self._safe_count(Order, period_domain + [('state', '=', 'done')])
        cancelled = self._safe_count(Order, period_domain + [('state', '=', 'cancel')])
        gmv_total = 0.0
        try:
            self.env.cr.execute(
                """SELECT COALESCE(SUM(amount_total), 0)
                     FROM sale_order
                    WHERE state IN ('sale', 'done')
                      AND create_date >= %s
                      AND create_date < %s""",
                [df_dt, dt_exclusive],
            )
            row = self.env.cr.fetchone()
            gmv_total = float(row[0] or 0) if row else 0.0
        except Exception:  # noqa: BLE001
            _logger.exception('Failed to compute GMV for period')

        refund_count = (
            self._safe_count(Order, period_domain + [('x_payment_status', '=', 'refunded')])
            if 'x_payment_status' in Order._fields else 0
        )
        flagged_count = (
            self._safe_count(Order, period_domain + [('x_admin_flagged', '=', True)])
            if 'x_admin_flagged' in Order._fields else 0
        )

        # --- Users ----------------------------------------------------------
        marketplace_user_domain = self._marketplace_user_domain()
        new_users = self._safe_count(Users, period_domain + marketplace_user_domain)
        blocked_users = (
            self._safe_count(Users, marketplace_user_domain + [('x_unitrade_is_blocked', '=', True)])
            if 'x_unitrade_is_blocked' in Users._fields else 0
        )
        new_sellers = self._safe_count(Seller, period_domain) if Seller is not None else 0
        verified_sellers = self._safe_count(Seller, [('status', '=', 'verified')]) if Seller is not None else 0

        # --- Products -------------------------------------------------------
        product_domain = self._marketplace_product_domain(Product)
        total_products = self._safe_count(Product, product_domain)
        if 'x_listing_status' in Product._fields:
            active_products = self._safe_count(Product, product_domain + [('x_listing_status', '=', 'published')])
            pending_products = self._safe_count(Product, product_domain + [('x_listing_status', 'in', ('draft', 'fee_pending'))])
            fee_pending_products = self._safe_count(Product, product_domain + [('x_listing_status', '=', 'fee_pending')])
            expired_products = self._safe_count(Product, product_domain + [('x_listing_status', '=', 'expired')])
            rejected_products = self._safe_count(Product, product_domain + [('x_listing_status', '=', 'rejected')])
        else:
            active_products = self._safe_count(Product, product_domain + [('active', '=', True), ('website_published', '=', True)])
            pending_products = self._safe_count(Product, product_domain + [('active', '=', True), ('website_published', '=', False)])
            fee_pending_products = (
                self._safe_count(
                    Product,
                    product_domain + ['|', ('x_listing_fee_status', 'in', ('unpaid', 'pending')), ('sale_ok', '=', False)],
                )
                if 'x_listing_fee_status' in Product._fields else self._safe_count(Product, product_domain + [('sale_ok', '=', False)])
            )
            expired_products = (
                self._safe_count(Product, product_domain + [
                    ('x_listing_expires_at', '!=', False),
                    ('x_listing_expires_at', '<', fields.Datetime.now()),
                ])
                if 'x_listing_expires_at' in Product._fields else 0
            )
            rejected_products = (
                self._safe_count(Product, product_domain + [('x_listing_fee_status', '=', 'failed')])
                if 'x_listing_fee_status' in Product._fields else 0
            )
        archived_products = self._safe_count(Product, product_domain + [('active', '=', False)])
        new_products = self._safe_count(Product, product_domain + period_domain)

        # --- Refunds --------------------------------------------------------
        refund_report = {
            'total': refund_count,
            'active': 0,
            'approved': 0,
            'rejected': 0,
            'resolved': 0,
            'cancelled': 0,
            'overdue': 0,
        }
        if Dispute is not None:
            refund_domain = [('dispute_type', '=', 'refund')] if 'dispute_type' in Dispute._fields else []
            refund_period_domain = refund_domain + period_domain
            active_states = (
                'submitted',
                'under_review',
                'need_buyer_evidence',
                'need_seller_response',
                'admin_review_final',
            )
            refund_report.update({
                'total': self._safe_count(Dispute, refund_period_domain),
                'active': self._safe_count(Dispute, refund_period_domain + [('state', 'in', active_states)]),
                'approved': self._safe_count(Dispute, refund_period_domain + [('state', '=', 'approved')]),
                'rejected': self._safe_count(Dispute, refund_period_domain + [('state', '=', 'rejected')]),
                'resolved': self._safe_count(Dispute, refund_period_domain + [('state', '=', 'resolved')]),
                'cancelled': self._safe_count(Dispute, refund_period_domain + [('state', '=', 'cancelled')]),
                'overdue': (
                    self._safe_count(Dispute, refund_period_domain + [('is_overdue', '=', True)])
                    if 'is_overdue' in Dispute._fields else 0
                ),
            })

        # --- Listing fee ----------------------------------------------------
        listing_fee_report = {
            'total': 0,
            'paid': 0,
            'pending': 0,
            'failed': 0,
            'expired': 0,
            'waived_products': 0,
            'not_required_products': 0,
            'revenue': 0.0,
            'revenue_display': '0',
        }
        if PaymentIntent is not None:
            fee_domain = [('intent_type', '=', 'listing_fee')]
            fee_period_domain = fee_domain + period_domain
            paid_intents = PaymentIntent.search(fee_period_domain + [('state', '=', 'paid')])
            listing_fee_report.update({
                'total': self._safe_count(PaymentIntent, fee_period_domain),
                'paid': len(paid_intents),
                'pending': self._safe_count(PaymentIntent, fee_period_domain + [('state', '=', 'pending')]),
                'failed': self._safe_count(PaymentIntent, fee_period_domain + [('state', '=', 'failed')]),
                'expired': self._safe_count(PaymentIntent, fee_period_domain + [('state', '=', 'expired')]),
                'revenue': sum(paid_intents.mapped('amount')),
            })
        if 'x_listing_fee_status' in Product._fields:
            listing_fee_report['waived_products'] = self._safe_count(Product, product_domain + [('x_listing_fee_status', '=', 'waived')])
            listing_fee_report['not_required_products'] = self._safe_count(
                Product,
                product_domain + [('x_listing_fee_status', '=', 'not_required'), ('sale_ok', '=', True)],
            )
        listing_fee_report['revenue_display'] = self._format_idr(listing_fee_report['revenue'])

        return {
            'date_from': fields.Date.to_string(df),
            'date_to': fields.Date.to_string(dt),
            'transactions': {
                'total': total_orders,
                'pending_payment': pending_payment,
                'completed': completed,
                'processing': processing,
                'cancelled': cancelled,
                'refund': refund_count,
                'flagged': flagged_count,
                'gmv_total': gmv_total,
                'gmv_total_display': self._format_idr(gmv_total),
            },
            'users': {
                'new_users': new_users,
                'blocked': blocked_users,
                'new_sellers': new_sellers,
                'verified_sellers': verified_sellers,
            },
            'products': {
                'total': total_products,
                'active': active_products,
                'pending': pending_products,
                'fee_pending': fee_pending_products,
                'expired': expired_products,
                'rejected': rejected_products,
                'archived': archived_products,
                'new': new_products,
            },
            'refunds': refund_report,
            'listing_fee': listing_fee_report,
        }

    # ---- customer service ------------------------------------------------

    @staticmethod
    def _short_text(value, limit=120):
        text = (value or '').strip()
        if len(text) <= limit:
            return text
        return text[:limit - 3].rstrip() + '...'

    def _record_action_url(self, xmlid, record_id=False):
        if not xmlid:
            return ''
        if record_id:
            return '/web#action=%s&id=%s&view_type=form' % (xmlid, record_id)
        return '/web#action=%s' % xmlid

    def _selection_label(self, record, field_name):
        try:
            field = record._fields[field_name]
            selection = dict(field.selection)
            return selection.get(record[field_name], record[field_name] or '-')
        except Exception:  # noqa: BLE001
            return getattr(record, field_name, '') or '-'

    def _audit_severity_meta(self, severity):
        return {
            'info': {'label': _('Info'), 'badge_class': 'blue'},
            'warning': {'label': _('Warning'), 'badge_class': 'yellow'},
            'critical': {'label': _('Critical'), 'badge_class': 'red'},
        }.get(severity or 'info', {'label': severity or _('Info'), 'badge_class': 'gray'})

    def _audit_action_label(self, action):
        action = action or ''
        labels = {
            'settings.update': _('Ubah Pengaturan'),
            'user.block': _('Blokir User'),
            'user.unblock': _('Aktifkan User'),
            'user.note': _('Catatan User'),
            'admin.create': _('Tambah Admin'),
            'seller.approve': _('Approve Seller'),
            'seller.reject': _('Tolak Seller'),
            'seller.reset': _('Reset Seller'),
            'order.flag': _('Tandai Transaksi'),
            'order.unflag': _('Hapus Tanda Transaksi'),
            'voucher.create': _('Buat Voucher'),
            'voucher.update': _('Edit Voucher'),
            'voucher.activate': _('Aktifkan Voucher'),
            'voucher.deactivate': _('Nonaktifkan Voucher'),
        }
        if action in labels:
            return labels[action]
        return action.replace('.', ' ').replace('_', ' ').title() if action else '-'

    @api.model
    def get_audit_logs_page(self, query='', severity='', actor_id=0, date_from='', date_to='', page=1, page_size=25):
        self._check_admin()
        if not self._has_model('unitrade.admin.audit.log'):
            return {
                'rows': [],
                'stats': {'total': 0, 'today': 0, 'warning': 0, 'critical': 0},
                'filters': {
                    'q': query or '',
                    'severity': severity or '',
                    'actor_id': int(actor_id or 0),
                    'date_from': date_from or '',
                    'date_to': date_to or '',
                },
                'actors': [],
                'pager': {'page': 1, 'pages': 1, 'total': 0},
            }

        AuditLog = self.env['unitrade.admin.audit.log'].sudo()
        try:
            page = max(1, int(page or 1))
        except (TypeError, ValueError):
            page = 1
        page_size = max(5, min(int(page_size or 25), 100))
        severity = severity if severity in ('info', 'warning', 'critical') else ''
        try:
            actor_id = int(actor_id or 0)
        except (TypeError, ValueError):
            actor_id = 0

        domain = []
        if query:
            domain += [
                '|', '|', '|', '|',
                ('action', 'ilike', query),
                ('description', 'ilike', query),
                ('res_name', 'ilike', query),
                ('res_model', 'ilike', query),
                ('user_id.name', 'ilike', query),
            ]
        if severity:
            domain.append(('severity', '=', severity))
        if actor_id:
            domain.append(('user_id', '=', actor_id))

        start_dt = False
        end_dt = False
        try:
            start_dt = fields.Datetime.to_datetime(fields.Date.from_string(date_from)) if date_from else False
        except Exception:  # noqa: BLE001
            start_dt = False
        try:
            end_date = fields.Date.from_string(date_to) if date_to else False
            end_dt = fields.Datetime.to_datetime(end_date + timedelta(days=1)) if end_date else False
        except Exception:  # noqa: BLE001
            end_dt = False
        if start_dt:
            domain.append(('create_date', '>=', start_dt))
        if end_dt:
            domain.append(('create_date', '<', end_dt))

        total = AuditLog.search_count(domain)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        logs = AuditLog.search(
            domain,
            order='create_date desc, id desc',
            limit=page_size,
            offset=(page - 1) * page_size,
        )

        today = fields.Date.context_today(self)
        today_start = fields.Datetime.to_datetime(today)
        actor_records = AuditLog.search([], order='create_date desc', limit=250).mapped('user_id')
        actors = [
            {'id': user.id, 'name': user.name}
            for user in actor_records
            if user
        ]

        rows = []
        for log in logs:
            severity_meta = self._audit_severity_meta(log.severity)
            target_url = ''
            if log.res_model and log.res_id:
                target_url = '/web#id=%s&model=%s&view_type=form' % (log.res_id, log.res_model)
            rows.append({
                'id': log.id,
                'date': self._datetime_label(log.create_date),
                'time_label': self._humanize_time(log.create_date),
                'actor': log.user_id.name or '-',
                'action': log.action or '-',
                'action_label': self._audit_action_label(log.action),
                'severity': log.severity or 'info',
                'severity_label': severity_meta['label'],
                'badge_class': severity_meta['badge_class'],
                'record': log.res_name or '-',
                'model': log.res_model or '-',
                'description': self._short_text(log.description or '-', limit=160),
                'payload': self._short_text(log.payload or '', limit=120),
                'target_url': target_url,
            })

        return {
            'rows': rows,
            'stats': {
                'total': AuditLog.search_count([]),
                'today': AuditLog.search_count([('create_date', '>=', today_start)]),
                'warning': AuditLog.search_count([('severity', '=', 'warning')]),
                'critical': AuditLog.search_count([('severity', '=', 'critical')]),
            },
            'filters': {
                'q': query or '',
                'severity': severity or '',
                'actor_id': actor_id,
                'date_from': date_from or '',
                'date_to': date_to or '',
            },
            'actors': actors,
            'pager': {
                'page': page,
                'pages': pages,
                'total': total,
                'has_prev': page > 1,
                'has_next': page < pages,
                'prev_page': max(1, page - 1),
                'next_page': min(pages, page + 1),
            },
        }

    def _audit_admin_target_url(self, log):
        model_name = log.res_model or ''
        res_name = log.res_name or ''
        query = quote_plus(res_name) if res_name else ''
        if model_name == 'sale.order':
            return '/unitrade/admin/transactions?q=%s' % query if query else '/unitrade/admin/transactions'
        if model_name == 'res.users':
            return '/unitrade/admin/users?q=%s' % query if query else '/unitrade/admin/users'
        if model_name == 'unitrade.seller':
            return '/unitrade/admin/users?seller_status=reported&q=%s' % query if query else '/unitrade/admin/users'
        if model_name == 'product.template':
            return '/unitrade/admin/products?q=%s' % query if query else '/unitrade/admin/products'
        if model_name == 'unitrade.customer.ticket':
            return '/unitrade/admin/customer-service?queue=ticket'
        if model_name == 'unitrade.chat.report':
            return '/unitrade/admin/customer-service?queue=chat'
        if model_name == 'unitrade.dispute':
            return '/unitrade/admin/customer-service?queue=refund'
        if model_name == 'unitrade.sponsorship.request':
            return '/unitrade/admin/sponsorships?q=%s' % query if query else '/unitrade/admin/sponsorships'
        if model_name == 'unitrade.seller.payout':
            return '/unitrade/admin/payouts?q=%s' % query if query else '/unitrade/admin/payouts'
        if model_name == 'unitrade.voucher':
            return '/unitrade/admin/vouchers?q=%s' % query if query else '/unitrade/admin/vouchers'
        if model_name == 'unitrade.announcement':
            return '/unitrade/admin/announcements?q=%s' % query if query else '/unitrade/admin/announcements'
        if model_name == 'unitrade.notification':
            return '/unitrade/admin/notifications'
        return ''

    @api.model
    def get_audit_log_detail(self, log_id):
        self._check_admin()
        if not self._has_model('unitrade.admin.audit.log'):
            return {'ok': False, 'error': _('Model audit log belum tersedia.')}
        log = self.env['unitrade.admin.audit.log'].sudo().browse(int(log_id or 0)).exists()
        if not log:
            return {'ok': False, 'error': _('Log aktivitas tidak ditemukan.')}

        severity_meta = self._audit_severity_meta(log.severity)
        payload_text = log.payload or ''
        payload_pretty = payload_text
        if payload_text:
            try:
                payload_pretty = json.dumps(
                    json.loads(payload_text),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            except Exception:  # noqa: BLE001
                payload_pretty = payload_text

        target_exists = False
        target_display = log.res_name or ''
        if log.res_model and log.res_id and self._has_model(log.res_model):
            try:
                target = self.env[log.res_model].sudo().browse(log.res_id).exists()
                target_exists = bool(target)
                if target:
                    target_display = target.display_name or target_display
            except Exception:  # noqa: BLE001
                target_exists = False

        return {
            'ok': True,
            'id': log.id,
            'date': self._datetime_label(log.create_date),
            'time_label': self._humanize_time(log.create_date),
            'actor': log.user_id.name or '-',
            'actor_email': log.user_id.email or log.user_id.login or '',
            'action': log.action or '-',
            'action_label': self._audit_action_label(log.action),
            'severity': log.severity or 'info',
            'severity_label': severity_meta['label'],
            'badge_class': severity_meta['badge_class'],
            'description': log.description or '',
            'payload': payload_pretty or '',
            'target': {
                'model': log.res_model or '-',
                'id': log.res_id or '',
                'name': target_display or log.res_name or '-',
                'exists': target_exists,
                'admin_url': self._audit_admin_target_url(log),
            },
        }

    @api.model
    def get_customer_service_page(self, queue='', page=1, page_size=20):
        """Build the admin-only customer service queue.

        This intentionally reads existing operational models and does not
        introduce user/seller-facing state or UI.
        """
        self._check_admin()
        queue = queue if queue in ('ticket', 'chat', 'refund', 'seller', 'order') else ''
        page = max(1, int(page or 1))
        page_size = max(5, min(int(page_size or 20), 100))
        rows = []
        counts = self._customer_service_counts()

        def add_row(**vals):
            rows.append(vals)

        if not queue or queue == 'ticket':
            Ticket = (
                self.env['unitrade.customer.ticket'].sudo()
                if self._has_model('unitrade.customer.ticket') else None
            )
            if Ticket is not None:
                tickets = Ticket.search(
                    [('status', 'in', ('pending', 'in_progress'))],
                    order='create_date desc',
                    limit=60,
                )
                for ticket in tickets:
                    evidence_count = len(ticket.evidence_ids)
                    order_name = ticket.order_id.name if ticket.order_id else _('Tanpa order')
                    add_row(
                        type='ticket',
                        type_label=_('Tiket Bantuan'),
                        title=ticket.title or ticket.name,
                        customer=ticket.partner_id.name or ticket.user_id.name or '-',
                        detail=self._short_text('%s · %s · %s bukti' % (
                            self._selection_label(ticket, 'category'),
                            order_name,
                            evidence_count,
                        )),
                        status=self._selection_label(ticket, 'status'),
                        urgency='urgent' if ticket.status == 'pending' else 'warning',
                        time_label=self._humanize_time(ticket.create_date),
                        date_sort=ticket.create_date,
                        action_url='',
                        case_id=ticket.id,
                        ticket_id=ticket.id,
                        can_start=ticket.status == 'pending',
                        can_done=ticket.status in ('pending', 'in_progress'),
                    )

        if not queue or queue == 'chat':
            ChatReport = (
                self.env['unitrade.chat.report'].sudo()
                if self._has_model('unitrade.chat.report') else None
            )
            if ChatReport is not None:
                reports = ChatReport.search(
                    [('state', 'in', ('submitted', 'under_review'))],
                    order='create_date desc',
                    limit=60,
                )
                for report in reports:
                    add_row(
                        type='chat',
                        type_label=_('Laporan Chat'),
                        title=report.reported_user_id.name or _('User dilaporkan'),
                        customer=report.reporter_user_id.name or '-',
                        detail=self._short_text(report.reason_detail or self._selection_label(report, 'reason')),
                        status=self._selection_label(report, 'state'),
                        urgency='urgent' if report.state == 'submitted' else 'warning',
                        time_label=self._humanize_time(report.create_date),
                        date_sort=report.create_date,
                        action_url='',
                        case_id=report.id,
                    )

        if not queue or queue == 'refund':
            Dispute = (
                self.env['unitrade.dispute'].sudo()
                if self._has_model('unitrade.dispute') else None
            )
            if Dispute is not None:
                active_states = (
                    'submitted',
                    'under_review',
                    'need_buyer_evidence',
                    'need_seller_response',
                    'admin_review_final',
                )
                disputes = Dispute.search(
                    [('state', 'in', active_states)],
                    order='create_date desc',
                    limit=60,
                )
                for dispute in disputes:
                    overdue = bool(getattr(dispute, 'is_overdue', False))
                    mediator = dispute.admin_id.name if dispute.admin_id else _('Belum ada admin penengah')
                    add_row(
                        type='refund',
                        type_label=_('Refund / Dispute'),
                        title=dispute.name or _('Refund'),
                        customer=dispute.buyer_id.name or '-',
                        detail=self._short_text('%s · %s · Penengah: %s' % (
                            dispute.order_id.name or '-',
                            self._selection_label(dispute, 'reason_code') if 'reason_code' in dispute._fields else '',
                            mediator,
                        )),
                        status=self._selection_label(dispute, 'state'),
                        urgency='urgent' if overdue else 'warning',
                        time_label=self._humanize_time(dispute.submitted_at or dispute.create_date),
                        date_sort=dispute.submitted_at or dispute.create_date,
                        action_url='',
                        case_id=dispute.id,
                    )

        if not queue or queue == 'seller':
            Seller = (
                self.env['unitrade.seller'].sudo()
                if self._has_model('unitrade.seller') else None
            )
            if Seller is not None and 'report_state' in Seller._fields:
                sellers = Seller.search(
                    [('report_state', 'in', ('reported', 'under_review'))],
                    order='last_reported_at desc, create_date desc',
                    limit=60,
                )
                for seller in sellers:
                    add_row(
                        type='seller',
                        type_label=_('Laporan Seller'),
                        title=seller.name or seller.user_id.name or '-',
                        customer=seller.user_id.name or '-',
                        detail=self._short_text(getattr(seller, 'last_report_reason', '') or _('Seller perlu ditinjau')),
                        status=self._selection_label(seller, 'report_state'),
                        urgency='warning',
                        time_label=self._humanize_time(seller.last_reported_at or seller.create_date),
                        date_sort=seller.last_reported_at or seller.create_date,
                        action_url='',
                        case_id=seller.id,
                    )

        if not queue or queue == 'order':
            Order = self.env['sale.order'].sudo()
            if 'x_admin_flagged' in Order._fields:
                orders = Order.search(
                    [('x_admin_flagged', '=', True)],
                    order='create_date desc',
                    limit=60,
                )
                for order in orders:
                    add_row(
                        type='order',
                        type_label=_('Transaksi Flagged'),
                        title=order.name or '-',
                        customer=order.partner_id.name or '-',
                        detail=self._short_text(getattr(order, 'x_admin_flag_reason', '') or _('Perlu dicek CS')),
                        status=(
                            dict(order._fields['state'].selection).get(order.state, order.state)
                            if 'state' in order._fields else order.state
                        ),
                        urgency='urgent',
                        time_label=self._humanize_time(order.create_date),
                        date_sort=order.create_date,
                        action_url='',
                        case_id=order.id,
                    )

        rank = {'urgent': 0, 'warning': 1, 'info': 2}
        rows.sort(
            key=lambda row: (
                rank.get(row.get('urgency'), 9),
                -(row.get('date_sort').timestamp() if row.get('date_sort') else 0),
            )
        )
        for row in rows:
            row.pop('date_sort', None)

        total = len(rows)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size

        return {
            'counts': counts,
            'queue': queue,
            'rows': rows[offset:offset + page_size],
            'pager': {
                'page': page,
                'total_pages': total_pages,
                'total': total,
                'has_prev': page > 1,
                'has_next': page < total_pages,
                'prev_page': max(1, page - 1),
                'next_page': min(total_pages, page + 1),
            },
        }

    @api.model
    def admin_update_customer_ticket_status(self, ticket_id, status, note=''):
        self._check_admin()
        if not self._has_model('unitrade.customer.ticket'):
            return {'ok': False, 'error': 'customer ticket module unavailable'}
        status = status if status in ('pending', 'in_progress', 'done') else ''
        if not status:
            return {'ok': False, 'error': 'invalid status'}
        ticket = self.env['unitrade.customer.ticket'].sudo().browse(int(ticket_id or 0)).exists()
        if not ticket:
            return {'ok': False, 'error': 'ticket not found'}
        try:
            ticket.action_update_status_from_admin(status, note=note or '', admin=self.env.user)
        except Exception as error:
            _logger.exception('Admin failed to update customer ticket %s status', ticket_id)
            return {'ok': False, 'error': str(error) or _('Status tiket gagal diperbarui.')}
        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'customer_ticket.status',
                description='Admin mengubah status tiket %s menjadi %s.' % (
                    ticket.name,
                    self._selection_label(ticket, 'status'),
                ),
                record=ticket,
                severity='info',
            )
        return {'ok': True, 'id': ticket.id, 'status': ticket.status}

    @api.model
    def admin_reply_customer_ticket(self, ticket_id, body):
        self._check_admin()
        if not self._has_model('unitrade.customer.ticket'):
            return {'ok': False, 'error': 'customer ticket module unavailable'}
        ticket = self.env['unitrade.customer.ticket'].sudo().browse(int(ticket_id or 0)).exists()
        if not ticket:
            return {'ok': False, 'error': 'ticket not found'}
        body = (body or '').strip()
        if not body:
            return {'ok': False, 'error': _('Balasan tidak boleh kosong.')}
        try:
            ticket.action_add_thread_message(
                body,
                author=self.env.user,
                message_type='admin',
                notify_customer=True,
            )
            if ticket.status == 'pending':
                ticket.action_update_status_from_admin(
                    'in_progress',
                    note=_('Tiket mulai diproses setelah Customer Service mengirim balasan.'),
                    admin=self.env.user,
                )
        except Exception as error:
            _logger.exception('Admin failed to reply customer ticket %s', ticket_id)
            return {'ok': False, 'error': str(error) or _('Balasan gagal dikirim.')}
        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'customer_ticket.reply',
                description='Admin membalas tiket %s.' % ticket.name,
                record=ticket,
                severity='info',
            )
        return {'ok': True, 'id': ticket.id}

    def _admin_media_size_label(self, size):
        size = int(size or 0)
        if size >= 1024 * 1024:
            return '%.1f MB' % (size / (1024 * 1024))
        if size >= 1024:
            return '%.0f KB' % (size / 1024)
        return '%s B' % size if size else ''

    def _admin_attachment_payload(self, attachment, label=''):
        attachment = attachment.sudo().exists()
        if not attachment:
            return False
        mimetype = (attachment.mimetype or '').lower()
        return {
            'id': attachment.id,
            'name': attachment.name or label or _('Bukti'),
            'label': label or attachment.name or _('Bukti'),
            'mimetype': mimetype or 'application/octet-stream',
            'size_label': self._admin_media_size_label(attachment.file_size),
            'is_image': mimetype.startswith('image/'),
            'is_video': mimetype.startswith('video/'),
            'url': '/unitrade/admin/media/attachment/%s' % attachment.id,
            'download_url': '/unitrade/admin/media/attachment/%s?download=1' % attachment.id,
        }

    def _admin_attachment_payloads(self, attachments, label=''):
        payloads = []
        seen = set()
        for attachment in attachments.sudo():
            if attachment.id in seen:
                continue
            seen.add(attachment.id)
            payload = self._admin_attachment_payload(attachment, label=label)
            if payload:
                payloads.append(payload)
        return payloads

    def _admin_escrow_media_payload(self, ledger, kind):
        field_name = 'seller_handoff_image' if kind == 'seller' else 'buyer_received_image'
        filename_field = 'seller_handoff_filename' if kind == 'seller' else 'buyer_received_filename'
        title = _('Bukti Penjual') if kind == 'seller' else _('Bukti Pembeli')
        if not ledger or field_name not in ledger._fields or not ledger[field_name]:
            return False
        filename = ledger[filename_field] if filename_field in ledger._fields else ''
        return {
            'id': '%s-%s' % (kind, ledger.id),
            'name': filename or title,
            'label': title,
            'mimetype': 'image/jpeg',
            'size_label': '',
            'is_image': True,
            'is_video': False,
            'url': '/unitrade/admin/media/escrow/%s/%s' % (kind, ledger.id),
            'download_url': '/unitrade/admin/media/escrow/%s/%s?download=1' % (kind, ledger.id),
        }

    def _admin_case_base(self, case_type, record, type_label, title, status_label='', urgency='warning'):
        return {
            'ok': True,
            'id': record.id,
            'type': case_type,
            'type_label': type_label,
            'title': title or '-',
            'status': status_label or '-',
            'urgency': urgency,
            'rows': [],
            'description': '',
            'notes': [],
            'evidence': [],
            'messages': [],
            'timeline': [],
            'actions': {},
        }

    def _customer_ticket_detail(self, case_id):
        if not self._has_model('unitrade.customer.ticket'):
            return {'ok': False, 'error': _('Model tiket bantuan belum tersedia.')}
        ticket = self.env['unitrade.customer.ticket'].sudo().browse(int(case_id or 0)).exists()
        if not ticket:
            return {'ok': False, 'error': _('Tiket bantuan tidak ditemukan.')}
        message_labels = {
            'customer': _('User'),
            'admin': _('Customer Service'),
            'system': _('Sistem'),
        }
        messages = []
        for message in ticket.message_ids.sudo():
            messages.append({
                'author': message.author_id.name or message_labels.get(message.message_type, '-'),
                'time': self._datetime_label(message.create_date),
                'type': message_labels.get(message.message_type, message.message_type),
                'body': message.body or '',
            })
        notes = []
        if ticket.resolved_note:
            notes.append({
                'label': _('Catatan penyelesaian'),
                'value': ticket.resolved_note,
            })
        if ticket.resolved_at:
            notes.append({
                'label': _('Diselesaikan'),
                'value': '%s%s' % (
                    self._datetime_label(ticket.resolved_at),
                    ' oleh %s' % ticket.resolved_by_id.name if ticket.resolved_by_id else '',
                ),
            })
        refund_url = ''
        refund_label = ''
        if ticket.category == 'refund_return' and ticket.order_id and self._has_model('unitrade.dispute'):
            dispute = self.env['unitrade.dispute'].sudo().search(
                [('order_id', '=', ticket.order_id.id)],
                order='create_date desc, id desc',
                limit=1,
            )
            if dispute:
                refund_url = self._record_action_url('unitrade_dispute.action_unitrade_dispute', dispute.id)
                refund_label = _('Buka dispute refund %s') % dispute.name
                notes.append({
                    'label': _('Refund terkait'),
                    'value': '%s - %s' % (dispute.name, self._selection_label(dispute, 'state')),
                })
            else:
                refund_url = '/unitrade/order/%s/refund/new' % ticket.order_id.id
                refund_label = _('Buka halaman ajukan refund')
        data = self._admin_case_base(
            'ticket',
            ticket,
            _('Tiket Bantuan'),
            ticket.title or ticket.name,
            self._selection_label(ticket, 'status'),
            'urgent' if ticket.status == 'pending' else 'warning',
        )
        data.update({
            'description': ticket.description or '',
            'rows': [
                {'label': _('Nomor Tiket'), 'value': ticket.name or '-'},
                {'label': _('Kategori'), 'value': self._selection_label(ticket, 'category')},
                {'label': _('Customer'), 'value': ticket.partner_id.name or ticket.user_id.name or '-'},
                {'label': _('Email'), 'value': ticket.user_id.email or ticket.user_id.login or '-'},
                {'label': _('Order'), 'value': ticket.order_id.name if ticket.order_id else _('Tanpa order')},
                {'label': _('Dibuat'), 'value': self._datetime_label(ticket.create_date)},
            ],
            'evidence': self._admin_attachment_payloads(ticket.evidence_ids.mapped('attachment_id'), label=_('Bukti Tiket')),
            'messages': messages,
            'notes': notes,
            'actions': {
                'ticket_id': ticket.id,
                'can_reply': ticket.status != 'done',
                'can_start': ticket.status == 'pending',
                'can_done': ticket.status in ('pending', 'in_progress'),
                'refund_url': refund_url,
                'refund_label': refund_label,
            },
        })
        return data

    def _chat_report_detail(self, case_id):
        if not self._has_model('unitrade.chat.report'):
            return {'ok': False, 'error': _('Model laporan chat belum tersedia.')}
        report = self.env['unitrade.chat.report'].sudo().browse(int(case_id or 0)).exists()
        if not report:
            return {'ok': False, 'error': _('Laporan chat tidak ditemukan.')}
        attachments = report.proof_attachment_ids
        if report.proof_attachment_id:
            attachments |= report.proof_attachment_id
        conversation = report.conversation_id.sudo()
        data = self._admin_case_base(
            'chat',
            report,
            _('Laporan Chat'),
            report.reported_user_id.name or _('User dilaporkan'),
            self._selection_label(report, 'state'),
            'urgent' if report.state == 'submitted' else 'warning',
        )
        messages = []
        for message in conversation.message_ids.sudo().sorted('id')[-10:]:
            media = False
            if message.attachment_id:
                media = self._admin_attachment_payload(message.attachment_id, label=_('Lampiran chat'))
            messages.append({
                'author': message.author_user_id.name or '-',
                'time': self._datetime_label(message.create_date),
                'type': self._selection_label(message, 'message_type'),
                'body': message.body or '',
                'media': media,
            })
        data.update({
            'description': report.reason_detail or '',
            'rows': [
                {'label': _('Pelapor'), 'value': report.reporter_user_id.name or '-'},
                {'label': _('User Dilaporkan'), 'value': report.reported_user_id.name or '-'},
                {'label': _('Kategori'), 'value': self._selection_label(report, 'reason')},
                {'label': _('Percakapan'), 'value': conversation.name or '-'},
                {'label': _('Produk'), 'value': conversation.product_id.name if conversation.product_id else '-'},
                {'label': _('Dibuat'), 'value': self._datetime_label(report.create_date)},
                {'label': _('Reviewer'), 'value': report.reviewer_user_id.name or '-'},
            ],
            'evidence': self._admin_attachment_payloads(attachments, label=_('Bukti Laporan Chat')),
            'messages': messages,
        })
        if report.admin_note:
            data['notes'].append({'label': _('Catatan Admin'), 'value': report.admin_note})
        return data

    def _refund_dispute_detail(self, case_id):
        if not self._has_model('unitrade.dispute'):
            return {'ok': False, 'error': _('Model refund/dispute belum tersedia.')}
        dispute = self.env['unitrade.dispute'].sudo().browse(int(case_id or 0)).exists()
        if not dispute:
            return {'ok': False, 'error': _('Refund/dispute tidak ditemukan.')}
        data = self._admin_case_base(
            'refund',
            dispute,
            _('Refund / Dispute'),
            dispute.name or _('Refund'),
            self._selection_label(dispute, 'state'),
            'urgent' if bool(getattr(dispute, 'is_overdue', False)) else 'warning',
        )
        evidence = []
        for item in dispute.evidence_ids.sudo():
            payload = self._admin_attachment_payload(item.attachment_id, label=self._selection_label(item, 'evidence_type'))
            if payload:
                payload['note'] = item.note or ''
                evidence.append(payload)
            elif item.url:
                evidence.append({
                    'id': 'url-%s' % item.id,
                    'name': self._selection_label(item, 'evidence_type'),
                    'label': item.note or self._selection_label(item, 'evidence_type'),
                    'mimetype': 'text/uri-list',
                    'size_label': '',
                    'is_image': False,
                    'is_video': False,
                    'url': item.url,
                    'download_url': item.url,
                    'note': item.note or '',
                })
        timeline = []
        for line in dispute.timeline_ids.sudo():
            timeline.append({
                'title': line.label or self._selection_label(line, 'event_key'),
                'status': self._selection_label(line, 'status'),
                'time': self._datetime_label(line.event_time),
                'note': line.note or '',
            })
        data.update({
            'description': dispute.reason_note or '',
            'rows': [
                {'label': _('Order'), 'value': dispute.order_id.name or '-'},
                {'label': _('Buyer'), 'value': dispute.buyer_id.name or '-'},
                {'label': _('Seller'), 'value': dispute.seller_id.name if dispute.seller_id else '-'},
                {'label': _('Alasan'), 'value': self._selection_label(dispute, 'reason_code')},
                {'label': _('Nominal Diajukan'), 'value': 'Rp ' + self._format_idr(dispute.requested_amount)},
                {'label': _('Nominal Disetujui'), 'value': 'Rp ' + self._format_idr(dispute.approved_amount) if dispute.approved_amount else '-'},
                {'label': _('Admin Penengah'), 'value': dispute.admin_id.name or _('Belum ada')},
                {'label': _('Diajukan'), 'value': self._datetime_label(dispute.submitted_at or dispute.create_date)},
            ],
            'evidence': evidence,
            'timeline': timeline,
        })
        if dispute.seller_decision_note:
            data['notes'].append({'label': _('Catatan Seller'), 'value': dispute.seller_decision_note})
        if dispute.admin_decision_note:
            data['notes'].append({'label': _('Catatan Admin'), 'value': dispute.admin_decision_note})
        return data

    def _seller_report_detail(self, case_id):
        if not self._has_model('unitrade.seller'):
            return {'ok': False, 'error': _('Model seller belum tersedia.')}
        seller = self.env['unitrade.seller'].sudo().browse(int(case_id or 0)).exists()
        if not seller:
            return {'ok': False, 'error': _('Laporan seller tidak ditemukan.')}
        data = self._admin_case_base(
            'seller',
            seller,
            _('Laporan Seller'),
            seller.name or seller.user_id.name or '-',
            self._selection_label(seller, 'report_state'),
            'warning',
        )
        messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'unitrade.seller'),
            ('res_id', '=', seller.id),
        ], order='date desc', limit=12)
        evidence = []
        notes = []
        for message in messages:
            if message.attachment_ids:
                evidence.extend(self._admin_attachment_payloads(message.attachment_ids, label=_('Media laporan seller')))
            if message.body:
                notes.append({
                    'label': self._datetime_label(message.date),
                    'value': (message.body or '').replace('<', '&lt;').replace('>', '&gt;'),
                })
        data.update({
            'description': seller.last_report_reason or _('Seller perlu ditinjau.'),
            'rows': [
                {'label': _('Nama Seller'), 'value': seller.name or '-'},
                {'label': _('Pemilik Akun'), 'value': seller.user_id.name or '-'},
                {'label': _('Email'), 'value': seller.user_id.email or seller.user_id.login or '-'},
                {'label': _('Status Seller'), 'value': self._selection_label(seller, 'status')},
                {'label': _('Status Laporan'), 'value': self._selection_label(seller, 'report_state')},
                {'label': _('Jumlah Laporan'), 'value': seller.report_count},
                {'label': _('Terakhir Dilaporkan'), 'value': self._datetime_label(seller.last_reported_at)},
                {'label': _('NIM'), 'value': seller.nim or '-'},
            ],
            'evidence': evidence,
            'notes': notes[:6],
        })
        if seller.report_admin_note:
            data['notes'].insert(0, {'label': _('Catatan Review Admin'), 'value': seller.report_admin_note})
        return data

    def _flagged_order_detail(self, case_id):
        order_detail = self.get_order_detail(case_id)
        if not order_detail:
            return {'ok': False, 'error': _('Transaksi tidak ditemukan.')}
        evidence = []
        if self._has_model('unitrade.escrow.ledger'):
            ledgers = self.env['unitrade.escrow.ledger'].sudo().search([('order_id', '=', int(case_id or 0))])
            for ledger in ledgers:
                for kind in ('seller', 'buyer'):
                    payload = self._admin_escrow_media_payload(ledger, kind)
                    if payload:
                        evidence.append(payload)
        data = self._admin_case_base(
            'order',
            self.env['sale.order'].sudo().browse(int(case_id or 0)),
            _('Transaksi Flagged'),
            order_detail.get('name') or '-',
            order_detail.get('unitrade_state_label') or order_detail.get('state_label') or '-',
            'urgent',
        )
        data.update({
            'description': order_detail.get('flag_reason') or _('Transaksi perlu dicek Customer Service.'),
            'rows': [
                {'label': _('Buyer'), 'value': order_detail.get('buyer_name') or '-'},
                {'label': _('Seller'), 'value': order_detail.get('seller_name') or '-'},
                {'label': _('Nominal'), 'value': order_detail.get('amount_display') or '-'},
                {'label': _('Pembayaran'), 'value': order_detail.get('payment_status_label') or '-'},
                {'label': _('Escrow'), 'value': order_detail.get('escrow_state_label') or '-'},
                {'label': _('Dibuat'), 'value': order_detail.get('create_date') or '-'},
            ],
            'evidence': evidence,
            'timeline': order_detail.get('status_steps') or [],
        })
        return data

    @api.model
    def get_customer_service_detail(self, case_type, case_id):
        self._check_admin()
        case_type = (case_type or '').strip()
        if case_type == 'ticket':
            return self._customer_ticket_detail(case_id)
        if case_type == 'chat':
            return self._chat_report_detail(case_id)
        if case_type == 'refund':
            return self._refund_dispute_detail(case_id)
        if case_type == 'seller':
            return self._seller_report_detail(case_id)
        if case_type == 'order':
            return self._flagged_order_detail(case_id)
        return {'ok': False, 'error': _('Jenis laporan tidak dikenal.')}

    # ---- sponsorship requests -------------------------------------------

    def _sponsorship_status_meta(self, status):
        return {
            'new': {'label': _('Baru'), 'badge_class': 'yellow'},
            'contacted': {'label': _('Dihubungi'), 'badge_class': 'blue'},
            'approved': {'label': _('Disetujui'), 'badge_class': 'green'},
            'rejected': {'label': _('Ditolak'), 'badge_class': 'red'},
        }.get(status or 'new', {'label': status or '-', 'badge_class': 'gray'})

    @api.model
    def get_sponsorships_page(self, query='', status='', page=1, page_size=20):
        self._check_admin()
        Sponsorship = (
            self.env['unitrade.sponsorship.request'].sudo()
            if self._has_model('unitrade.sponsorship.request') else None
        )
        if Sponsorship is None:
            return {
                'rows': [],
                'stats': {'total': 0, 'new': 0, 'contacted': 0, 'approved': 0, 'rejected': 0},
                'filters': {'q': query or '', 'status': status or ''},
                'pager': {'page': 1, 'pages': 1, 'total': 0},
            }

        page = max(1, int(page or 1))
        page_size = max(5, min(int(page_size or 20), 100))
        status = status if status in ('new', 'contacted', 'approved', 'rejected') else ''
        domain = []
        if status:
            domain.append(('status', '=', status))
        if query:
            domain += [
                '|', '|', '|',
                ('name', 'ilike', query),
                ('contact_name', 'ilike', query),
                ('email', 'ilike', query),
                ('phone', 'ilike', query),
            ]

        total = Sponsorship.search_count(domain)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        requests = Sponsorship.search(
            domain,
            order='create_date desc, id desc',
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        rows = []
        for request in requests:
            meta = self._sponsorship_status_meta(request.status)
            admin_target_url = '/unitrade/admin/sponsorships?q=%s#sponsorship-%s' % (
                quote_plus(request.name or ''),
                request.id,
            )
            rows.append({
                'id': request.id,
                'name': request.name or '-',
                'contact_name': request.contact_name or '-',
                'email': request.email or '',
                'phone': request.phone or '',
                'budget_note': request.budget_note or '-',
                'campaign_goal': self._short_text(request.campaign_goal or '-', limit=150),
                'campaign_goal_full': request.campaign_goal or '',
                'status': request.status or 'new',
                'status_label': meta['label'],
                'badge_class': meta['badge_class'],
                'note': request.note or '',
                'note_short': self._short_text(request.note or '-', limit=100),
                'created': self._datetime_label(request.create_date),
                'time_label': self._humanize_time(request.create_date),
                'target_url': admin_target_url,
            })
        return {
            'rows': rows,
            'stats': {
                'total': Sponsorship.search_count([]),
                'new': Sponsorship.search_count([('status', '=', 'new')]),
                'contacted': Sponsorship.search_count([('status', '=', 'contacted')]),
                'approved': Sponsorship.search_count([('status', '=', 'approved')]),
                'rejected': Sponsorship.search_count([('status', '=', 'rejected')]),
            },
            'filters': {'q': query or '', 'status': status or ''},
            'pager': {
                'page': page,
                'pages': pages,
                'total': total,
                'has_prev': page > 1,
                'has_next': page < pages,
                'prev_page': max(1, page - 1),
                'next_page': min(pages, page + 1),
            },
        }

    @api.model
    def admin_update_sponsorship(self, request_id, status='', note=''):
        self._check_admin()
        if not self._has_model('unitrade.sponsorship.request'):
            return {'ok': False, 'error': 'sponsorship module unavailable'}
        status = status if status in ('new', 'contacted', 'approved', 'rejected') else ''
        request = self.env['unitrade.sponsorship.request'].sudo().browse(int(request_id or 0)).exists()
        if not request:
            return {'ok': False, 'error': 'request not found'}
        vals = {'note': note or ''}
        if status:
            vals['status'] = status
        request.write(vals)
        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'sponsorship.update',
                description='Admin memperbarui sponsorship %s.' % (request.name or request.id),
                record=request,
                severity='info',
            )
        return {'ok': True, 'id': request.id, 'status': request.status}

    # ---- delivery monitoring --------------------------------------------

    def _delivery_status_meta(self, status):
        return {
            'pending': {'label': _('Pending'), 'badge_class': 'yellow'},
            'picked_up': {'label': _('Dijemput'), 'badge_class': 'blue'},
            'in_transit': {'label': _('Dalam Pengiriman'), 'badge_class': 'blue'},
            'delivered': {'label': _('Terkirim'), 'badge_class': 'green'},
            'failed': {'label': _('Gagal'), 'badge_class': 'red'},
        }.get(status or 'pending', {'label': status or '-', 'badge_class': 'gray'})

    @api.model
    def get_deliveries_page(self, query='', status='', page=1, page_size=20):
        self._check_admin()
        Delivery = (
            self.env['unitrade.delivery'].sudo()
            if self._has_model('unitrade.delivery') else None
        )
        if Delivery is None:
            return {
                'rows': [],
                'stats': {'total': 0, 'pending': 0, 'in_transit': 0, 'delivered': 0, 'failed': 0},
                'filters': {'q': query or '', 'status': status or ''},
                'pager': {'page': 1, 'pages': 1, 'total': 0},
            }

        page = max(1, int(page or 1))
        page_size = max(5, min(int(page_size or 20), 100))
        status = status if status in ('pending', 'picked_up', 'in_transit', 'delivered', 'failed') else ''
        domain = []
        if status:
            domain.append(('status', '=', status))
        if query:
            domain += [
                '|', '|', '|',
                ('order_id.name', 'ilike', query),
                ('tracking_number', 'ilike', query),
                ('driver_name', 'ilike', query),
                ('driver_phone', 'ilike', query),
            ]

        total = Delivery.search_count(domain)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        deliveries = Delivery.search(
            domain,
            order='create_date desc, id desc',
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        rows = []
        for delivery in deliveries:
            meta = self._delivery_status_meta(delivery.status)
            order = delivery.order_id
            rows.append({
                'id': delivery.id,
                'order_name': order.name if order else '-',
                'buyer': order.partner_id.name if order and order.partner_id else '-',
                'tracking_number': delivery.tracking_number or delivery.gosend_order_id or '-',
                'status': delivery.status or 'pending',
                'status_label': meta['label'],
                'badge_class': meta['badge_class'],
                'shipping_cost': self._format_idr(delivery.shipping_cost),
                'pickup_address': self._short_text(delivery.pickup_address or '-', limit=80),
                'dropoff_address': self._short_text(delivery.dropoff_address or '-', limit=80),
                'driver': delivery.driver_name or '-',
                'driver_phone': delivery.driver_phone or '',
                'created': self._datetime_label(delivery.create_date),
                'time_label': self._humanize_time(delivery.create_date),
                'target_url': self._record_action_url('unitrade_delivery.action_unitrade_delivery', delivery.id),
                'order_url': '/web#id=%s&model=sale.order&view_type=form' % order.id if order else '',
            })
        return {
            'rows': rows,
            'stats': {
                'total': Delivery.search_count([]),
                'pending': Delivery.search_count([('status', '=', 'pending')]),
                'in_transit': Delivery.search_count([('status', 'in', ('picked_up', 'in_transit'))]),
                'delivered': Delivery.search_count([('status', '=', 'delivered')]),
                'failed': Delivery.search_count([('status', '=', 'failed')]),
            },
            'filters': {'q': query or '', 'status': status or ''},
            'pager': {
                'page': page,
                'pages': pages,
                'total': total,
                'has_prev': page > 1,
                'has_next': page < pages,
                'prev_page': max(1, page - 1),
                'next_page': min(pages, page + 1),
            },
        }

    @api.model
    def admin_update_delivery_status(self, delivery_id, status):
        self._check_admin()
        if not self._has_model('unitrade.delivery'):
            return {'ok': False, 'error': 'delivery module unavailable'}
        status = status if status in ('pending', 'picked_up', 'in_transit', 'delivered', 'failed') else ''
        if not status:
            return {'ok': False, 'error': 'invalid status'}
        delivery = self.env['unitrade.delivery'].sudo().browse(int(delivery_id or 0)).exists()
        if not delivery:
            return {'ok': False, 'error': 'delivery not found'}
        delivery.write({'status': status})
        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'delivery.status',
                description='Admin mengubah status delivery %s menjadi %s.' % (
                    delivery.order_id.name or delivery.id,
                    self._selection_label(delivery, 'status'),
                ),
                record=delivery,
                severity='warning' if status == 'failed' else 'info',
            )
        return {'ok': True, 'id': delivery.id, 'status': delivery.status}

    # ---- reviews ---------------------------------------------------------

    @staticmethod
    def _star_label(rating):
        try:
            rating = int(rating or 0)
        except (TypeError, ValueError):
            rating = 0
        return '%s/5' % max(0, min(rating, 5))

    @api.model
    def get_reviews_page(self, query='', visibility='', rating=0, page=1, page_size=20):
        self._check_admin()
        Review = self.env['unitrade.review'].sudo() if self._has_model('unitrade.review') else None
        if Review is None:
            return {
                'rows': [],
                'stats': {'total': 0, 'visible': 0, 'hidden': 0, 'low_rating': 0},
                'filters': {'q': query or '', 'visibility': visibility or '', 'rating': 0},
                'pager': {'page': 1, 'pages': 1, 'total': 0},
            }

        page = max(1, int(page or 1))
        page_size = max(5, min(int(page_size or 20), 100))
        visibility = visibility if visibility in ('visible', 'hidden') else ''
        try:
            rating = int(rating or 0)
        except (TypeError, ValueError):
            rating = 0
        rating = rating if 1 <= rating <= 5 else 0

        domain = []
        if visibility == 'visible':
            domain.append(('is_visible', '=', True))
        elif visibility == 'hidden':
            domain.append(('is_visible', '=', False))
        if rating:
            domain.append(('rating', '=', rating))
        if query:
            domain += [
                '|', '|', '|',
                ('product_id.name', 'ilike', query),
                ('user_id.name', 'ilike', query),
                ('order_id.name', 'ilike', query),
                ('comment', 'ilike', query),
            ]

        total = Review.search_count(domain)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        reviews = Review.search(
            domain,
            order='create_date desc, id desc',
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        rows = []
        for review in reviews:
            has_images = bool(review.review_image or review.review_image_2 or review.review_image_3)
            rows.append({
                'id': review.id,
                'product': review.product_id.display_name or '-',
                'reviewer': review.user_id.name or '-',
                'order': review.order_id.name or '-',
                'rating': review.rating or 0,
                'rating_label': self._star_label(review.rating),
                'comment': self._short_text(review.comment or '-', limit=160),
                'tags': review.review_tags or '-',
                'has_images': has_images,
                'is_visible': bool(review.is_visible),
                'visibility_label': _('Tampil') if review.is_visible else _('Disembunyikan'),
                'badge_class': 'green' if review.is_visible else 'red',
                'created': self._datetime_label(review.create_date),
                'time_label': self._humanize_time(review.create_date),
                'target_url': self._record_action_url('unitrade_review.action_unitrade_review', review.id),
            })

        return {
            'rows': rows,
            'stats': {
                'total': Review.search_count([]),
                'visible': Review.search_count([('is_visible', '=', True)]),
                'hidden': Review.search_count([('is_visible', '=', False)]),
                'low_rating': Review.search_count([('rating', '<=', 2)]),
            },
            'filters': {'q': query or '', 'visibility': visibility or '', 'rating': rating},
            'pager': {
                'page': page,
                'pages': pages,
                'total': total,
                'has_prev': page > 1,
                'has_next': page < pages,
                'prev_page': max(1, page - 1),
                'next_page': min(pages, page + 1),
            },
        }

    @api.model
    def admin_toggle_review_visibility(self, review_id, visible):
        self._check_admin()
        if not self._has_model('unitrade.review'):
            return {'ok': False, 'error': 'review module unavailable'}
        review = self.env['unitrade.review'].sudo().browse(int(review_id or 0)).exists()
        if not review:
            return {'ok': False, 'error': 'review not found'}
        visible = bool(visible)
        review.write({'is_visible': visible})
        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'review.show' if visible else 'review.hide',
                description='Admin %s review produk %s.' % (
                    'menampilkan' if visible else 'menyembunyikan',
                    review.product_id.display_name or review.id,
                ),
                record=review,
                severity='warning' if not visible else 'info',
            )
        return {'ok': True, 'id': review.id, 'is_visible': review.is_visible}

    # ---- payout batches --------------------------------------------------

    def _payout_state_meta(self, state):
        return {
            'draft': {'label': _('Draft'), 'badge_class': 'gray'},
            'ready': {'label': _('Ready to Pay'), 'badge_class': 'yellow'},
            'paid': {'label': _('Paid'), 'badge_class': 'green'},
            'cancelled': {'label': _('Cancelled'), 'badge_class': 'red'},
        }.get(state or 'draft', {'label': state or '-', 'badge_class': 'gray'})

    @api.model
    def get_payouts_page(self, query='', state='', page=1, page_size=20):
        self._check_admin()
        Payout = (
            self.env['unitrade.seller.payout'].sudo()
            if self._has_model('unitrade.seller.payout') else None
        )
        if Payout is None:
            return {
                'rows': [],
                'stats': {'total': 0, 'draft': 0, 'ready': 0, 'paid': 0, 'cancelled': 0},
                'filters': {'q': query or '', 'state': state or ''},
                'pager': {'page': 1, 'pages': 1, 'total': 0},
            }

        page = max(1, int(page or 1))
        page_size = max(5, min(int(page_size or 20), 100))
        state = state if state in ('draft', 'ready', 'paid', 'cancelled') else ''
        domain = []
        if state:
            domain.append(('state', '=', state))
        if query:
            domain += [
                '|', '|',
                ('name', 'ilike', query),
                ('seller_id.name', 'ilike', query),
                ('payment_reference', 'ilike', query),
            ]

        total = Payout.search_count(domain)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        payouts = Payout.search(
            domain,
            order='create_date desc, id desc',
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        rows = []
        for payout in payouts:
            meta = self._payout_state_meta(payout.state)
            rows.append({
                'id': payout.id,
                'name': payout.name or '-',
                'seller': payout.seller_id.name or '-',
                'state': payout.state or 'draft',
                'state_label': meta['label'],
                'badge_class': meta['badge_class'],
                'ledger_count': payout.ledger_count,
                'total_amount': self._format_idr(payout.total_amount),
                'channel': payout.payout_channel_code or '-',
                'account_name': payout.payout_account_name or '-',
                'account_number': payout.payout_account_number or '-',
                'payment_reference': payout.payment_reference or '-',
                'payout_ready': bool(payout.payout_ready),
                'paid_at': self._datetime_label(payout.paid_at) if payout.paid_at else '-',
                'created': self._datetime_label(payout.create_date),
                'target_url': self._record_action_url('unitrade_payment.action_unitrade_seller_payout', payout.id),
                'seller_url': '/web#id=%s&model=unitrade.seller&view_type=form' % payout.seller_id.id if payout.seller_id else '',
            })

        return {
            'rows': rows,
            'stats': {
                'total': Payout.search_count([]),
                'draft': Payout.search_count([('state', '=', 'draft')]),
                'ready': Payout.search_count([('state', '=', 'ready')]),
                'paid': Payout.search_count([('state', '=', 'paid')]),
                'cancelled': Payout.search_count([('state', '=', 'cancelled')]),
            },
            'filters': {'q': query or '', 'state': state or ''},
            'pager': {
                'page': page,
                'pages': pages,
                'total': total,
                'has_prev': page > 1,
                'has_next': page < pages,
                'prev_page': max(1, page - 1),
                'next_page': min(pages, page + 1),
            },
        }

    @api.model
    def admin_run_payout_action(self, payout_id, action, payment_reference='', cancel_reason=''):
        self._check_admin()
        if not self._has_model('unitrade.seller.payout'):
            return {'ok': False, 'error': 'payout module unavailable'}
        payout = self.env['unitrade.seller.payout'].sudo().browse(int(payout_id or 0)).exists()
        if not payout:
            return {'ok': False, 'error': 'payout not found'}
        try:
            if action == 'recompute':
                payout.action_recompute_ledgers()
            elif action == 'ready':
                payout.action_mark_ready()
            elif action == 'paid':
                if payment_reference:
                    payout.write({'payment_reference': payment_reference})
                payout.action_mark_paid()
            elif action == 'cancel':
                if cancel_reason:
                    payout.write({'cancel_reason': cancel_reason})
                payout.action_cancel()
            else:
                return {'ok': False, 'error': 'invalid payout action'}
        except Exception as error:  # noqa: BLE001
            _logger.exception('Admin payout action failed: %s', action)
            return {'ok': False, 'error': str(error)}
        return {'ok': True, 'id': payout.id, 'state': payout.state}

    # ---- announcements ---------------------------------------------------

    def _announcement_state_meta(self, state):
        return {
            'draft': {'label': _('Draft'), 'badge_class': 'yellow'},
            'published': {'label': _('Dipublish'), 'badge_class': 'green'},
        }.get(state or 'draft', {'label': state or '-', 'badge_class': 'gray'})

    def _announcement_target_users(self):
        public_user = self.env.ref('base.public_user', raise_if_not_found=False)
        domain = [('active', '=', True)]
        if public_user:
            domain.append(('id', '!=', public_user.id))
        return self.env['res.users'].sudo().search(domain)

    def _ensure_announcement_notifications(self, announcement):
        """Ensure a published announcement is visible in every user's inbox.

        The notification module already has a broadcast dispatcher. This
        dashboard guard makes admin publish/re-sync deterministic for demo and
        audit: if a prior broadcast skipped or failed a user, the missing
        in-app row is inserted without duplicating rows that already exist.
        """
        if not self._has_model('unitrade.notification'):
            return {'target': 0, 'visible': 0, 'created': 0}

        Notification = self.env['unitrade.notification'].sudo()
        users = self._announcement_target_users()
        if not users:
            announcement.sudo().write({
                'target_user_count': 0,
                'emitted_count': 0,
                'failed_batches': 0,
            })
            return {'target': 0, 'visible': 0, 'created': 0}

        payload = {
            'title_override': announcement.title,
            'message_override': announcement.body,
            'reference_model': announcement._name,
            'reference_id': announcement.id,
        }
        action_url = announcement.action_url or ''
        if action_url and hasattr(Notification, '_validate_action_url'):
            action_url = Notification._validate_action_url(action_url) or ''
        if action_url:
            payload['action_url'] = action_url

        idempotency_key = ''
        if hasattr(Notification, '_build_idempotency_key'):
            idempotency_key = Notification._build_idempotency_key('system.announcement', payload)

        existing_user_ids = set()
        if idempotency_key:
            existing_user_ids.update(Notification.search([
                ('user_id', 'in', users.ids),
                ('idempotency_key', '=', idempotency_key),
            ]).mapped('user_id').ids)
        existing_user_ids.update(Notification.search([
            ('user_id', 'in', users.ids),
            ('event_code', '=', 'system.announcement'),
            ('reference_model', '=', announcement._name),
            ('reference_id', '=', announcement.id),
        ]).mapped('user_id').ids)

        vals_list = []
        for user in users:
            if user.id in existing_user_ids:
                continue
            vals = {
                'user_id': user.id,
                'audience': 'user',
                'title': announcement.title,
                'message': announcement.body,
                'category': 'system',
                'event_code': 'system.announcement',
                'notification_type': 'system',
                'priority': 'info',
                'reference_model': announcement._name,
                'reference_id': announcement.id,
                'action_url': action_url or False,
                'email_state': 'not_applicable',
            }
            if idempotency_key:
                vals['idempotency_key'] = idempotency_key
            vals_list.append(vals)

        created = Notification.browse()
        if vals_list:
            created = Notification.create(vals_list)

        visible_count = len(existing_user_ids) + len(created)
        announcement.sudo().write({
            'target_user_count': len(users),
            'emitted_count': visible_count,
            'failed_batches': 0,
        })
        return {
            'target': len(users),
            'visible': visible_count,
            'created': len(created),
        }

    @api.model
    def get_announcements_page(self, query='', state='', page=1, page_size=20):
        self._check_admin()
        Announcement = (
            self.env['unitrade.announcement'].sudo()
            if self._has_model('unitrade.announcement') else None
        )
        if Announcement is None:
            return {
                'rows': [],
                'stats': {'total': 0, 'draft': 0, 'published': 0, 'failed_batches': 0},
                'filters': {'q': query or '', 'state': state or ''},
                'pager': {'page': 1, 'pages': 1, 'total': 0},
            }

        page = max(1, int(page or 1))
        page_size = max(5, min(int(page_size or 20), 100))
        state = state if state in ('draft', 'published') else ''
        domain = []
        if state:
            domain.append(('state', '=', state))
        if query:
            domain += ['|', ('title', 'ilike', query), ('body', 'ilike', query)]

        total = Announcement.search_count(domain)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        announcements = Announcement.search(
            domain,
            order='create_date desc, id desc',
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        rows = []
        for announcement in announcements:
            meta = self._announcement_state_meta(announcement.state)
            rows.append({
                'id': announcement.id,
                'title': announcement.title or '-',
                'body': self._short_text(announcement.body or '-', limit=170),
                'action_url': announcement.action_url or '-',
                'state': announcement.state or 'draft',
                'state_label': meta['label'],
                'badge_class': meta['badge_class'],
                'published_at': self._datetime_label(announcement.published_at) if announcement.published_at else '-',
                'published_by': announcement.published_by.name or '-',
                'target_user_count': announcement.target_user_count,
                'emitted_count': announcement.emitted_count,
                'failed_batches': announcement.failed_batches,
                'created': self._datetime_label(announcement.create_date),
                'target_url': self._record_action_url('unitrade_notification.action_unitrade_announcement', announcement.id),
            })

        return {
            'rows': rows,
            'stats': {
                'total': Announcement.search_count([]),
                'draft': Announcement.search_count([('state', '=', 'draft')]),
                'published': Announcement.search_count([('state', '=', 'published')]),
                'failed_batches': sum(Announcement.search([]).mapped('failed_batches')),
            },
            'filters': {'q': query or '', 'state': state or ''},
            'pager': {
                'page': page,
                'pages': pages,
                'total': total,
                'has_prev': page > 1,
                'has_next': page < pages,
                'prev_page': max(1, page - 1),
                'next_page': min(pages, page + 1),
            },
        }

    @api.model
    def get_announcement_detail(self, announcement_id):
        self._check_admin()
        if not self._has_model('unitrade.announcement'):
            return {'ok': False, 'error': 'announcement module unavailable'}
        announcement = self.env['unitrade.announcement'].sudo().browse(int(announcement_id or 0)).exists()
        if not announcement:
            return {'ok': False, 'error': _('Pengumuman tidak ditemukan.')}

        meta = self._announcement_state_meta(announcement.state)
        notification_stats = {
            'total': 0,
            'unread': 0,
            'read': 0,
        }
        if self._has_model('unitrade.notification'):
            Notification = self.env['unitrade.notification'].sudo()
            domain = [
                ('event_code', '=', 'system.announcement'),
                ('reference_model', '=', announcement._name),
                ('reference_id', '=', announcement.id),
            ]
            if 'audience' in Notification._fields:
                domain.append(('audience', '=', 'user'))
            notification_stats = {
                'total': Notification.search_count(domain),
                'unread': Notification.search_count(domain + [('is_read', '=', False)]),
                'read': Notification.search_count(domain + [('is_read', '=', True)]),
            }

        return {
            'ok': True,
            'id': announcement.id,
            'title': announcement.title or '-',
            'body': announcement.body or '-',
            'action_url': announcement.action_url or '-',
            'state': announcement.state or 'draft',
            'state_label': meta['label'],
            'badge_class': meta['badge_class'],
            'created': self._datetime_label(announcement.create_date),
            'published_at': self._datetime_label(announcement.published_at) if announcement.published_at else '-',
            'published_by': announcement.published_by.name or '-',
            'target_user_count': announcement.target_user_count,
            'emitted_count': announcement.emitted_count,
            'failed_batches': announcement.failed_batches,
            'notification_stats': notification_stats,
        }

    @api.model
    def admin_create_announcement(self, values):
        self._check_admin()
        if not self._has_model('unitrade.announcement'):
            return {'ok': False, 'error': 'announcement module unavailable'}
        values = values or {}
        title = (values.get('title') or '').strip()
        body = (values.get('body') or '').strip()
        action_url = (values.get('action_url') or '').strip()
        if not title or not body:
            return {'ok': False, 'error': 'Judul dan isi pengumuman wajib diisi.'}
        announcement = self.env['unitrade.announcement'].sudo().create({
            'title': title,
            'body': body,
            'action_url': action_url,
        })
        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'announcement.create',
                description='Admin membuat draft pengumuman %s.' % announcement.title,
                record=announcement,
                severity='info',
            )
        return {'ok': True, 'id': announcement.id}

    @api.model
    def admin_publish_announcement(self, announcement_id):
        self._check_admin()
        if not self._has_model('unitrade.announcement'):
            return {'ok': False, 'error': 'announcement module unavailable'}
        announcement = self.env['unitrade.announcement'].sudo().browse(int(announcement_id or 0)).exists()
        if not announcement:
            return {'ok': False, 'error': 'announcement not found'}
        try:
            if announcement.state == 'draft':
                announcement.action_publish_and_broadcast()
            sync = self._ensure_announcement_notifications(announcement)
        except Exception as error:  # noqa: BLE001
            _logger.exception('Admin publish announcement failed')
            return {'ok': False, 'error': str(error)}
        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'announcement.publish',
                description='Admin publish pengumuman %s.' % announcement.title,
                record=announcement,
                severity='warning',
            )
        return {
            'ok': True,
            'id': announcement.id,
            'state': announcement.state,
            'target': sync.get('target', 0),
            'visible': sync.get('visible', 0),
            'created': sync.get('created', 0),
        }

    @api.model
    def admin_sync_announcement_notifications(self, announcement_id):
        self._check_admin()
        if not self._has_model('unitrade.announcement'):
            return {'ok': False, 'error': 'announcement module unavailable'}
        announcement = self.env['unitrade.announcement'].sudo().browse(int(announcement_id or 0)).exists()
        if not announcement:
            return {'ok': False, 'error': 'announcement not found'}
        if announcement.state != 'published':
            return {'ok': False, 'error': _('Pengumuman harus dipublish dulu sebelum sinkron notifikasi.')}
        try:
            sync = self._ensure_announcement_notifications(announcement)
        except Exception as error:  # noqa: BLE001
            _logger.exception('Admin sync announcement notifications failed')
            return {'ok': False, 'error': str(error)}
        if self._has_model('unitrade.admin.audit.log'):
            self.env['unitrade.admin.audit.log'].sudo().log_action(
                'announcement.notification.sync',
                description='Admin sinkron notifikasi pengumuman %s.' % announcement.title,
                record=announcement,
                severity='info',
                payload=sync,
            )
        return {'ok': True, 'id': announcement.id, **sync}

    # ---- notifications (persistent admin inbox) --------------------------

    def _task_notification_type(self, key):
        if key.startswith('ktm') or key == 'reported_sellers':
            return 'moderation'
        if key.startswith('disputes'):
            return 'refund'
        if key.startswith('customer'):
            return 'chat'
        if key.startswith('sponsorship'):
            return 'system'
        if key.startswith('delivery'):
            return 'delivery'
        if key.startswith('payout'):
            return 'payout'
        if key.startswith('orders') or key.startswith('escrow'):
            return 'order'
        if key.startswith('listing'):
            return 'payment'
        return 'system'

    def _sync_admin_notifications_from_tasks(self):
        Notification = self._notification_model()
        if Notification is None:
            return

        admin = self._current_admin_user()
        task_queue = self.get_task_queue()
        active_keys = set()
        for group in task_queue.get('groups', []):
            dedupe_key = 'admin-task:%s' % group['key']
            active_keys.add(dedupe_key)
            priority = 'urgent' if group['urgency'] == 'urgent' else 'warning'
            title = '%s: %s item' % (group['title'], group['count'])
            message = group['description']
            latest = group['items'][0] if group.get('items') else {}
            if latest.get('label'):
                message = '%s Terbaru: %s.' % (message, latest['label'])
            Notification.create_admin_notification(
                title=title,
                message=message,
                priority=priority,
                notification_type=self._task_notification_type(group['key']),
                target_url=group.get('target_url') or '/unitrade/admin/tasks',
                dedupe_key=dedupe_key,
                user_id=admin.id,
            )

        stale = Notification.search(
            self._notification_domain()
            + [('dedupe_key', 'like', 'admin-task:%'), ('dedupe_key', 'not in', list(active_keys or ['']))]
        )
        if stale:
            stale.write({
                'is_read': True,
                'read_at': fields.Datetime.now(),
                'read_by_id': admin.id,
            })

    def _notification_payloads(self, notifications):
        return [notification._admin_payload() for notification in notifications]

    @api.model
    def get_notifications(self, limit=8):
        """Return persistent notifications for the admin topbar."""
        self._check_admin()
        self._sync_admin_notifications_from_tasks()
        Notification = self._notification_model()
        if Notification is None:
            return {'items': [], 'total': 0, 'unread': 0}

        domain = self._notification_domain()
        notifications = Notification.search(
            domain,
            order='is_read asc, create_date desc',
            limit=int(limit or 8),
        )
        items = self._notification_payloads(notifications)
        if not items:
            items.append({
                'id': 0,
                'dedupe_key': 'all-clear',
                'level': 'info',
                'priority': 'info',
                'title': 'Semua antrian admin kosong.',
                'message': 'Tidak ada notifikasi mendesak.',
                'time_label': '',
                'target_url': '/unitrade/admin',
                'is_read': True,
                'notification_type': 'system',
            })
        summary = self._notification_summary()
        return {
            'items': items,
            'total': summary['total'],
            'unread': summary['unread'],
        }

    @api.model
    def get_notifications_page(self, status='', priority='', page=1, page_size=25):
        self._check_admin()
        self._sync_admin_notifications_from_tasks()
        Notification = self._notification_model()
        if Notification is None:
            return {
                'items': [],
                'counts': self._notification_summary(),
                'filters': {'status': status or '', 'priority': priority or ''},
                'pager': {'page': 1, 'pages': 1, 'total': 0},
            }

        try:
            page = max(1, int(page or 1))
        except (TypeError, ValueError):
            page = 1
        page_size = max(5, min(int(page_size or 25), 100))
        domain = self._notification_domain()
        if status == 'unread':
            domain.append(('is_read', '=', False))
        elif status == 'read':
            domain.append(('is_read', '=', True))
        if priority in ('info', 'warning', 'urgent', 'critical'):
            domain.append(('priority', '=', priority))

        total = Notification.search_count(domain)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        notifications = Notification.search(
            domain,
            order='is_read asc, create_date desc',
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return {
            'items': self._notification_payloads(notifications),
            'counts': self._notification_summary(),
            'filters': {'status': status or '', 'priority': priority or ''},
            'pager': {
                'page': page,
                'pages': pages,
                'total': total,
                'has_prev': page > 1,
                'has_next': page < pages,
                'prev_page': max(1, page - 1),
                'next_page': min(pages, page + 1),
            },
        }

    @api.model
    def mark_notification_read(self, notification_id):
        self._check_admin()
        Notification = self._notification_model()
        if Notification is None:
            return {'ok': False, 'error': 'notification module unavailable'}
        notification = Notification.search(
            self._notification_domain() + [('id', '=', int(notification_id or 0))],
            limit=1,
        )
        if not notification:
            return {'ok': False, 'error': 'notification not found'}
        notification.write({
            'is_read': True,
            'read_at': fields.Datetime.now(),
            'read_by_id': self._current_admin_user().id,
        })
        return {'ok': True, 'unread': self._notification_summary()['unread']}

    @api.model
    def mark_all_notifications_read(self):
        self._check_admin()
        Notification = self._notification_model()
        if Notification is None:
            return {'ok': False, 'error': 'notification module unavailable'}
        notifications = Notification.search(self._notification_domain() + [('is_read', '=', False)])
        notifications.write({
            'is_read': True,
            'read_at': fields.Datetime.now(),
            'read_by_id': self._current_admin_user().id,
        })
        return {'ok': True, 'unread': 0}

    @staticmethod
    def _humanize_time(dt):
        if not dt:
            return ''
        try:
            now = fields.Datetime.now()
            delta = now - dt
            seconds = int(delta.total_seconds())
            if seconds < 60:
                return 'Baru saja'
            minutes = seconds // 60
            if minutes < 60:
                return '%s menit lalu' % minutes
            hours = minutes // 60
            if hours < 24:
                return '%s jam lalu' % hours
            days = hours // 24
            if days < 7:
                return '%s hari lalu' % days
            return dt.strftime('%d %b %Y')
        except Exception:  # noqa: BLE001
            return ''

    @api.model
    def export_orders_csv(self, date_from='', date_to=''):
        """Return list-of-rows ready to be CSV-encoded by the controller."""
        self._check_admin()
        try:
            df = fields.Date.from_string(date_from) if date_from else None
            dt = fields.Date.from_string(date_to) if date_to else None
        except Exception:  # noqa: BLE001
            df = dt = None
        if not df:
            df = fields.Date.context_today(self) - timedelta(days=29)
        if not dt:
            dt = fields.Date.context_today(self)

        df_dt = fields.Datetime.to_datetime(df)
        dt_exclusive = fields.Datetime.to_datetime(dt + timedelta(days=1))

        Order = self.env['sale.order'].sudo()
        orders = Order.search(
            [('create_date', '>=', df_dt), ('create_date', '<', dt_exclusive)],
            order='create_date asc',
        )
        rows = [['ID', 'Tanggal', 'Buyer', 'Email', 'Status', 'Status Pembayaran', 'Nominal']]
        for o in orders:
            rows.append([
                o.name or '',
                fields.Datetime.to_string(o.create_date) if o.create_date else '',
                o.partner_id.name if o.partner_id else '',
                o.partner_id.email or '' if o.partner_id else '',
                dict(o._fields['state'].selection).get(o.state, o.state),
                getattr(o, 'x_payment_status', '') or '',
                int(round(o.amount_total or 0)),
            ])
        return rows

    @api.model
    def export_report_summary_csv(self, date_from='', date_to=''):
        """Return compact admin report summary rows for CSV export."""
        self._check_admin()
        report = self.get_reports(date_from=date_from, date_to=date_to)
        rows = [
            ['Periode', report['date_from'], report['date_to']],
            [],
            ['Bagian', 'Metrik', 'Nilai'],
            ['Transaksi', 'Total transaksi', report['transactions']['total']],
            ['Transaksi', 'Menunggu pembayaran', report['transactions']['pending_payment']],
            ['Transaksi', 'Diproses', report['transactions']['processing']],
            ['Transaksi', 'Selesai', report['transactions']['completed']],
            ['Transaksi', 'Refund', report['transactions']['refund']],
            ['Transaksi', 'Dibatalkan', report['transactions']['cancelled']],
            ['Transaksi', 'Bermasalah', report['transactions']['flagged']],
            ['Transaksi', 'Total GMV', int(round(report['transactions']['gmv_total'] or 0))],
            ['Pengguna', 'User baru', report['users']['new_users']],
            ['Pengguna', 'Seller baru', report['users']['new_sellers']],
            ['Pengguna', 'Seller terverifikasi', report['users']['verified_sellers']],
            ['Pengguna', 'User diblokir', report['users']['blocked']],
            ['Produk', 'Total produk', report['products']['total']],
            ['Produk', 'Produk aktif', report['products']['active']],
            ['Produk', 'Produk pending', report['products']['pending']],
            ['Produk', 'Menunggu fee', report['products']['fee_pending']],
            ['Produk', 'Expired', report['products']['expired']],
            ['Produk', 'Ditolak', report['products']['rejected']],
            ['Produk', 'Diarsipkan', report['products']['archived']],
            ['Produk', 'Baru periode ini', report['products']['new']],
            ['Refund', 'Total pengajuan', report['refunds']['total']],
            ['Refund', 'Aktif/ditinjau', report['refunds']['active']],
            ['Refund', 'Approved', report['refunds']['approved']],
            ['Refund', 'Rejected', report['refunds']['rejected']],
            ['Refund', 'Resolved', report['refunds']['resolved']],
            ['Refund', 'Cancelled', report['refunds']['cancelled']],
            ['Refund', 'Lewat SLA', report['refunds']['overdue']],
            ['Listing Fee', 'Total intent', report['listing_fee']['total']],
            ['Listing Fee', 'Paid', report['listing_fee']['paid']],
            ['Listing Fee', 'Pending', report['listing_fee']['pending']],
            ['Listing Fee', 'Failed', report['listing_fee']['failed']],
            ['Listing Fee', 'Expired', report['listing_fee']['expired']],
            ['Listing Fee', 'Produk diwaiver', report['listing_fee']['waived_products']],
            ['Listing Fee', 'Produk tidak wajib fee', report['listing_fee']['not_required_products']],
            ['Listing Fee', 'Revenue paid', int(round(report['listing_fee']['revenue'] or 0))],
        ]
        return rows

    # ---- detail providers (for modals) ------------------------------------

    def _verification_for_user(self, user, seller=False):
        if not self._has_model('unitrade.seller.verification') or not user.partner_id:
            return False
        Verification = self.env['unitrade.seller.verification'].sudo()
        domain = [('partner_id', '=', user.partner_id.id)]
        if seller and getattr(seller, 'nim', False):
            domain = ['|', ('partner_id', '=', user.partner_id.id), ('nim_extracted', '=', seller.nim)]
        return Verification.search(domain, order='create_date desc', limit=1)

    def _ktm_payload(self, user, seller=False):
        verification = self._verification_for_user(user, seller=seller)
        source = verification if verification and verification.ktm_image else seller
        source_type = 'verification' if verification and verification.ktm_image else 'seller'
        has_image = bool(source and getattr(source, 'ktm_image', False))

        state = verification.state if verification else (seller.status if seller else '')
        admin_status = self._verification_status_for_admin(verification) if verification else ''
        state_labels = {
            'draft': _('Draft'),
            'pending': _('Menunggu Verifikasi'),
            'manual_review': _('Manual Review'),
            'approved': _('Terverifikasi'),
            'verified': _('Terverifikasi'),
            'rejected': _('Ditolak'),
            'revoked': _('Dicabut'),
        }
        filename = ''
        if source:
            filename = getattr(source, 'ktm_filename', '') or ''

        confidence = 0.0
        if verification:
            confidence = (verification.name_confidence or 0.0) * 100
        elif seller:
            confidence = seller.ocr_confidence or 0.0

        created_on = verification.create_date if verification else (seller.create_date if seller else False)
        verified_on = (
            verification.reviewed_date if verification and verification.reviewed_date
            else seller.verified_date if seller and getattr(seller, 'verified_date', False)
            else False
        )

        return {
            'has_record': bool(verification or seller),
            'has_image': has_image,
            'image_url': (
                '/unitrade/admin/ktm/%s/%s' % (source_type, source.id)
                if has_image else ''
            ),
            'filename': filename,
            'state': state or '',
            'state_label': (
                _('Perlu Review Admin')
                if verification and admin_status == 'pending' and state == 'rejected'
                else state_labels.get(state, state or '-')
            ),
            'nim': (
                verification.nim_extracted if verification and verification.nim_extracted
                else seller.nim if seller else ''
            ),
            'seller_name': seller.name if seller else user.name,
            'student_name': (
                verification.student_name if verification and verification.student_name
                else seller.ocr_student_name if seller else ''
            ),
            'confidence': round(confidence, 1),
            'nim_match': bool(
                verification.nim_extracted if verification
                else seller.ocr_nim_match if seller else False
            ),
            'name_match': bool(
                verification.name_match_token if verification
                else seller.ocr_name_match if seller else False
            ),
            'created_on': fields.Datetime.to_string(created_on) if created_on else '',
            'verified_on': fields.Datetime.to_string(verified_on) if verified_on else '',
            'rejection_reason': (
                verification.rejection_reason if verification and verification.rejection_reason
                else seller.rejection_reason if seller else ''
            ),
        }

    @api.model
    def get_user_detail(self, user_id):
        self._check_admin()
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {}
        Seller = self.env['unitrade.seller'].sudo() if self._has_model('unitrade.seller') else None
        seller = Seller.search([('user_id', '=', user.id)], limit=1) if Seller is not None else False

        # Order count as buyer
        order_count = 0
        order_total_buyer = 0.0
        if user.partner_id:
            orders = self.env['sale.order'].sudo().search([
                ('partner_id', '=', user.partner_id.id),
                ('state', 'in', ('sale', 'done')),
            ])
            order_count = len(orders)
            order_total_buyer = sum(orders.mapped('amount_total'))

        # Product count (as seller)
        product_count = 0
        if seller and 'x_seller_id' in self.env['product.template']._fields:
            product_count = self.env['product.template'].sudo().search_count([('x_seller_id', '=', seller.id)])

        # Audit log: chatter messages on user.partner_id and seller record
        log_entries = []
        try:
            partner = user.partner_id
            if partner:
                msgs = self.env['mail.message'].sudo().search(
                    [('model', '=', 'res.partner'), ('res_id', '=', partner.id), ('subtype_id.internal', '=', True)],
                    order='date desc', limit=20,
                )
                for m in msgs:
                    log_entries.append({
                        'date': fields.Datetime.to_string(m.date),
                        'author': m.author_id.name if m.author_id else '',
                        'body': (m.body or '').replace('<', '&lt;').replace('>', '&gt;'),
                    })
            if seller:
                msgs = self.env['mail.message'].sudo().search(
                    [('model', '=', 'unitrade.seller'), ('res_id', '=', seller.id), ('subtype_id.internal', '=', True)],
                    order='date desc', limit=20,
                )
                for m in msgs:
                    log_entries.append({
                        'date': fields.Datetime.to_string(m.date),
                        'author': m.author_id.name if m.author_id else '',
                        'body': (m.body or '').replace('<', '&lt;').replace('>', '&gt;'),
                    })
        except Exception:  # noqa: BLE001
            _logger.exception('Failed reading audit log')

        return {
            'id': user.id,
            'name': user.name,
            'email': user.email or user.login,
            'phone': user.partner_id.phone or user.partner_id.mobile or '' if user.partner_id else '',
            'create_date': fields.Datetime.to_string(user.create_date) if user.create_date else '',
            'is_blocked': bool(getattr(user, 'x_unitrade_is_blocked', False)),
            'block_reason': getattr(user, 'x_unitrade_block_reason', '') or '',
            'admin_note': getattr(user, 'x_unitrade_admin_note', '') or '',
            'is_email_verified': bool(getattr(user, 'x_is_email_verified', False)),
            'seller': {
                'id': seller.id if seller else False,
                'status': seller.status if seller else 'none',
                'nim': seller.nim if seller else '',
                'verified_date': fields.Datetime.to_string(seller.verified_date) if seller and seller.verified_date else '',
                'rejection_reason': seller.rejection_reason if seller else '',
            } if seller else {'status': 'none'},
            'ktm': self._ktm_payload(user, seller=seller),
            'stats': {
                'orders': order_count,
                'orders_total': self._format_idr(order_total_buyer),
                'products': product_count,
            },
            'audit_log': log_entries[:20],
        }

    @api.model
    def get_order_detail(self, order_id):
        self._check_admin()
        order = self.env['sale.order'].sudo().browse(int(order_id)).exists()
        if not order.exists():
            return {}

        def _dt(value):
            return fields.Datetime.to_string(value) if value else ''

        def _amount(value):
            return 'Rp ' + self._format_idr(value)

        def _model_url(model_name, record_id):
            return '/web#id=%s&model=%s&view_type=form' % (record_id, model_name) if record_id else ''

        def _field_value(record, field_name):
            if record and field_name in record._fields:
                return record[field_name]
            return False

        status_steps = []

        def _add_step(title, status='', date=False, note='', tone=''):
            status_steps.append({
                'title': title,
                'status': status or '',
                'date': _dt(date),
                'note': note or '',
                'tone': tone or '',
            })

        # Order line summary
        lines = []
        seller_names = []
        for line in order.order_line:
            seller_name = ''
            template = line.product_id.product_tmpl_id
            if template and 'x_seller_id' in template._fields and template.x_seller_id:
                seller_name = template.x_seller_id.name or ''
                if seller_name and seller_name not in seller_names:
                    seller_names.append(seller_name)
            lines.append({
                'name': line.product_id.display_name or line.name,
                'qty': line.product_uom_qty,
                'subtotal': self._format_idr(line.price_subtotal),
                'seller_name': seller_name,
            })

        PaymentIntent = (
            self.env['unitrade.payment.intent'].sudo()
            if self._has_model('unitrade.payment.intent') else None
        )
        intent = False
        if PaymentIntent is not None:
            intent = (
                order.x_payment_intent_id.sudo().exists()
                if 'x_payment_intent_id' in order._fields and order.x_payment_intent_id else False
            )
            if not intent:
                intent = PaymentIntent.search([
                    ('sale_order_id', '=', order.id),
                    ('intent_type', '=', 'order_checkout'),
                ], order='create_date desc', limit=1)

        payment_method = ''
        if 'x_payment_method' in order._fields and order.x_payment_method:
            payment_method = order.x_payment_method
        if intent:
            payment_method = (
                intent.payment_method_label
                or intent.payment_method_code
                or intent.midtrans_payment_type
                or intent.xendit_channel_code
                or payment_method
            )
            if intent.midtrans_bank and intent.midtrans_bank.upper() not in (payment_method or '').upper():
                payment_method = '%s (%s)' % (payment_method or 'Midtrans', intent.midtrans_bank.upper())

        payment_reference = ''
        if intent:
            for field_name in (
                'payment_reference',
                'midtrans_order_id',
                'xendit_reference_id',
                'doku_invoice_number',
                'name',
            ):
                value = _field_value(intent, field_name)
                if value:
                    payment_reference = value
                    break
        if not payment_reference and 'x_midtrans_order_id' in order._fields:
            payment_reference = order.x_midtrans_order_id or ''

        payment_status = getattr(order, 'x_payment_status', '') or ''
        payment_status_label = (
            self._selection_label(order, 'x_payment_status')
            if 'x_payment_status' in order._fields and payment_status else ''
        )
        unitrade_state = getattr(order, 'x_unitrade_order_state', '') or ''
        unitrade_state_label = (
            self._selection_label(order, 'x_unitrade_order_state')
            if 'x_unitrade_order_state' in order._fields and unitrade_state else ''
        )
        escrow_state = getattr(order, 'x_escrow_state', '') or ''
        escrow_state_label = (
            self._selection_label(order, 'x_escrow_state')
            if 'x_escrow_state' in order._fields and escrow_state else ''
        )

        EscrowLedger = (
            self.env['unitrade.escrow.ledger'].sudo()
            if self._has_model('unitrade.escrow.ledger') else None
        )
        ledgers = (
            EscrowLedger.search([('order_id', '=', order.id)], order='create_date desc')
            if EscrowLedger is not None else False
        )
        escrow_rows = []
        for ledger in ledgers:
            escrow_rows.append({
                'id': ledger.id,
                'name': ledger.name,
                'seller_name': ledger.seller_id.name if ledger.seller_id else '',
                'state': ledger.state or '',
                'state_label': self._selection_label(ledger, 'state'),
                'payout_status': ledger.payout_status or '',
                'payout_status_label': self._selection_label(ledger, 'payout_status'),
                'amount_seller_display': _amount(ledger.amount_seller),
                'amount_total_display': _amount(ledger.amount_total),
                'released_at': _dt(ledger.released_at),
                'completed_at': _dt(ledger.completed_at),
                'url': _model_url('unitrade.escrow.ledger', ledger.id),
            })
        escrow_total_seller = sum(ledgers.mapped('amount_seller')) if ledgers else 0
        escrow_url = (
            _model_url('unitrade.escrow.ledger', ledgers[:1].id)
            if ledgers and len(ledgers) == 1
            else self._record_action_url('unitrade_payment.action_unitrade_escrow_ledger')
            if ledgers else ''
        )

        Dispute = self.env['unitrade.dispute'].sudo() if self._has_model('unitrade.dispute') else None
        disputes = (
            Dispute.search([('order_id', '=', order.id)], order='create_date desc')
            if Dispute is not None else False
        )
        latest_dispute = False
        if 'x_refund_dispute_id' in order._fields and order.x_refund_dispute_id:
            latest_dispute = order.x_refund_dispute_id.sudo().exists()
        if not latest_dispute and disputes:
            latest_dispute = disputes[:1]
        refund_state = getattr(order, 'x_refund_state', '') or ''
        refund_state_label = (
            self._selection_label(order, 'x_refund_state')
            if 'x_refund_state' in order._fields and refund_state else ''
        )
        if latest_dispute and (not refund_state_label or refund_state == 'none'):
            refund_state_label = self._selection_label(latest_dispute, 'state')
            refund_state = latest_dispute.state or ''
        refund_url = _model_url('unitrade.dispute', latest_dispute.id) if latest_dispute else ''

        Payout = (
            self.env['unitrade.seller.payout'].sudo()
            if self._has_model('unitrade.seller.payout') else None
        )
        payouts = (
            Payout.search([('ledger_ids', 'in', ledgers.ids)], order='create_date desc')
            if Payout is not None and ledgers else False
        )
        latest_payout = payouts[:1] if payouts else False
        payout_rows = []
        for payout in (payouts[:3] if payouts else []):
            payout_rows.append({
                'id': payout.id,
                'name': payout.name,
                'seller_name': payout.seller_id.name if payout.seller_id else '',
                'state': payout.state or '',
                'state_label': self._selection_label(payout, 'state'),
                'total_amount_display': _amount(payout.total_amount),
                'paid_at': _dt(payout.paid_at),
                'url': _model_url('unitrade.seller.payout', payout.id),
            })
        payout_url = (
            _model_url('unitrade.seller.payout', latest_payout.id)
            if latest_payout else ''
        )

        PaymentEvent = (
            self.env['unitrade.payment.event'].sudo()
            if self._has_model('unitrade.payment.event') else None
        )
        payment_events = []
        if PaymentEvent is not None:
            events = PaymentEvent.search([('order_id', '=', order.id)], order='create_date desc', limit=5)
            for event in events:
                payment_events.append({
                    'date': _dt(event.create_date),
                    'provider': self._selection_label(event, 'provider'),
                    'state_label': self._selection_label(event, 'state'),
                    'event_key': event.event_key or event.name,
                    'url': _model_url('unitrade.payment.event', event.id),
                })

        _add_step(
            _('Order dibuat'),
            dict(order._fields['state'].selection).get(order.state, order.state),
            order.create_date,
            _('Pesanan tercatat di sistem Odoo.'),
            'blue',
        )
        if payment_status or intent:
            payment_date = (
                getattr(order, 'x_paid_at', False)
                or (intent.paid_at if intent else False)
                or (intent.create_date if intent else False)
            )
            payment_note = payment_method or payment_reference or ''
            _add_step(
                _('Pembayaran'),
                payment_status_label or (self._selection_label(intent, 'state') if intent else ''),
                payment_date,
                payment_note,
                'green' if payment_status == 'paid' else 'yellow',
            )
        if escrow_state or ledgers:
            latest_ledger = ledgers[:1] if ledgers else False
            escrow_date = (
                latest_ledger.completed_at
                or latest_ledger.released_at
                or latest_ledger.create_date
                if latest_ledger else False
            )
            _add_step(
                _('Escrow'),
                escrow_state_label or (self._selection_label(latest_ledger, 'state') if latest_ledger else ''),
                escrow_date,
                _('%s ledger, dana seller %s') % (len(ledgers) if ledgers else 0, _amount(escrow_total_seller)),
                'blue',
            )
        if latest_dispute:
            dispute_date = (
                latest_dispute.resolved_at
                or latest_dispute.approved_at
                or latest_dispute.rejected_at
                or latest_dispute.review_started_at
                or latest_dispute.submitted_at
                or latest_dispute.create_date
            )
            _add_step(
                _('Refund / Dispute'),
                self._selection_label(latest_dispute, 'state'),
                dispute_date,
                latest_dispute.reason_note,
                'red' if latest_dispute.is_overdue else 'yellow',
            )
        if latest_payout:
            _add_step(
                _('Payout Seller'),
                self._selection_label(latest_payout, 'state'),
                latest_payout.paid_at or latest_payout.create_date,
                latest_payout.payment_reference or '',
                'green' if latest_payout.state == 'paid' else 'yellow',
            )
        if 'x_completed_at' in order._fields and order.x_completed_at:
            _add_step(
                _('Transaksi selesai'),
                _('Completed'),
                order.x_completed_at,
                _('Buyer menerima barang dan escrow selesai.'),
                'green',
            )

        # Status timeline (from chatter)
        timeline = []
        try:
            msgs = self.env['mail.message'].sudo().search([
                ('model', '=', 'sale.order'),
                ('res_id', '=', order.id),
            ], order='date asc', limit=30)
            for m in msgs:
                timeline.append({
                    'date': fields.Datetime.to_string(m.date),
                    'author': m.author_id.name if m.author_id else '',
                    'subject': m.subject or '',
                    'body': (m.body or '').replace('<', '&lt;').replace('>', '&gt;'),
                })
        except Exception:  # noqa: BLE001
            pass

        action_links = []
        if intent:
            action_links.append({
                'label': _('Payment Intent'),
                'url': _model_url('unitrade.payment.intent', intent.id),
                'count': 1,
            })
        if ledgers:
            action_links.append({
                'label': _('Escrow Ledger'),
                'url': escrow_url,
                'count': len(ledgers),
            })
        if latest_dispute:
            action_links.append({
                'label': _('Refund / Dispute'),
                'url': refund_url,
                'count': len(disputes) if disputes else 1,
            })
        if latest_payout:
            action_links.append({
                'label': _('Payout Seller'),
                'url': payout_url,
                'count': len(payouts) if payouts else 1,
            })

        return {
            'id': order.id,
            'name': order.name,
            'state': order.state,
            'state_label': dict(order._fields['state'].selection).get(order.state, order.state),
            'amount_display': 'Rp ' + self._format_idr(order.amount_total),
            'create_date': _dt(order.create_date),
            'buyer_name': order.partner_id.name if order.partner_id else '',
            'buyer_email': order.partner_id.email if order.partner_id else '',
            'seller_name': ', '.join(seller_names),
            'unitrade_state': unitrade_state,
            'unitrade_state_label': unitrade_state_label,
            'payment_status': payment_status,
            'payment_status_label': payment_status_label,
            'payment_method': payment_method or '',
            'payment_reference': payment_reference or '',
            'payment_provider_label': self._selection_label(intent, 'provider') if intent else '',
            'payment_intent_name': intent.name if intent else '',
            'payment_intent_state_label': self._selection_label(intent, 'state') if intent else '',
            'payment_intent_url': _model_url('unitrade.payment.intent', intent.id) if intent else '',
            'payment_paid_at': _dt(getattr(order, 'x_paid_at', False) or (intent.paid_at if intent else False)),
            'payment_expires_at': _dt(intent.expires_at if intent else False),
            'escrow_state': escrow_state,
            'escrow_state_label': escrow_state_label,
            'escrow': {
                'state': escrow_state,
                'state_label': escrow_state_label,
                'count': len(ledgers) if ledgers else 0,
                'total_seller_display': _amount(escrow_total_seller),
                'url': escrow_url,
                'rows': escrow_rows,
            },
            'refund': {
                'state': refund_state,
                'state_label': refund_state_label,
                'count': len(disputes) if disputes else 0,
                'latest_name': latest_dispute.name if latest_dispute else '',
                'latest_state_label': self._selection_label(latest_dispute, 'state') if latest_dispute else '',
                'admin_name': latest_dispute.admin_id.name if latest_dispute and latest_dispute.admin_id else '',
                'requested_amount_display': _amount(latest_dispute.requested_amount) if latest_dispute else '',
                'approved_amount_display': _amount(latest_dispute.approved_amount) if latest_dispute and latest_dispute.approved_amount else '',
                'is_overdue': bool(latest_dispute.is_overdue) if latest_dispute else False,
                'url': refund_url,
            },
            'payout': {
                'count': len(payouts) if payouts else 0,
                'latest_name': latest_payout.name if latest_payout else '',
                'latest_state_label': self._selection_label(latest_payout, 'state') if latest_payout else '',
                'total_amount_display': _amount(latest_payout.total_amount) if latest_payout else '',
                'paid_at': _dt(latest_payout.paid_at) if latest_payout else '',
                'url': payout_url,
                'rows': payout_rows,
            },
            'is_flagged': bool(getattr(order, 'x_admin_flagged', False)),
            'flag_reason': getattr(order, 'x_admin_flag_reason', '') or '',
            'lines': lines,
            'status_steps': status_steps,
            'timeline': timeline,
            'payment_events': payment_events,
            'action_links': action_links,
        }

    # ---- task action endpoints --------------------------------------------

    @api.model
    def open_pending_ktm(self):
        self._check_admin()
        action = self.env.ref(
            'unitrade_seller.action_unitrade_seller_pending', raise_if_not_found=False
        )
        return action.read()[0] if action else False

    @api.model
    def open_reported_sellers(self):
        self._check_admin()
        action = self.env.ref(
            'unitrade_seller.action_unitrade_seller_reported', raise_if_not_found=False
        )
        return action.read()[0] if action else False

    @api.model
    def open_seller_list(self):
        self._check_admin()
        action = self.env.ref(
            'unitrade_seller.action_unitrade_seller', raise_if_not_found=False
        )
        return action.read()[0] if action else False

    # ---- unified task queue (cross-module) --------------------------------

    @api.model
    def get_task_queue(self, urgency='', limit_per_group=50):
        """Return a unified task queue across UniTrade modules.

        Each group: {key, title, urgency, count, target_url, items[]}.
        ``urgency`` filter accepts ``urgent``, ``warning``, or empty (all).
        """
        self._check_admin()
        groups = []

        Order = self.env['sale.order'].sudo()
        Seller = self.env['unitrade.seller'].sudo() if self._has_model('unitrade.seller') else None
        Verification = (
            self.env['unitrade.seller.verification'].sudo()
            if self._has_model('unitrade.seller.verification') else None
        )
        Dispute = (
            self.env['unitrade.dispute'].sudo()
            if self._has_model('unitrade.dispute') else None
        )
        EscrowLedger = (
            self.env['unitrade.escrow.ledger'].sudo()
            if self._has_model('unitrade.escrow.ledger') else None
        )
        PaymentIntent = (
            self.env['unitrade.payment.intent'].sudo()
            if self._has_model('unitrade.payment.intent') else None
        )
        Ticket = (
            self.env['unitrade.customer.ticket'].sudo()
            if self._has_model('unitrade.customer.ticket') else None
        )
        Sponsorship = (
            self.env['unitrade.sponsorship.request'].sudo()
            if self._has_model('unitrade.sponsorship.request') else None
        )
        params = self.env['ir.config_parameter'].sudo()
        try:
            overdue_minutes = int(params.get_param('unitrade.notify.overdue_minutes', '60') or 60)
        except (TypeError, ValueError):
            overdue_minutes = 60

        # 1. KTM pending / manual review
        if Verification is not None:
            verifications = Verification.search(
                [('state', 'in', ('pending', 'manual_review', 'rejected'))],
                order='create_date asc',
                limit=limit_per_group,
            ).filtered(
                lambda verification: self._verification_status_for_admin(verification) == 'pending'
            )
            if verifications:
                groups.append({
                    'key': 'ktm_review',
                    'title': _('Verifikasi KTM'),
                    'description': _('KTM seller perlu dicek manual.'),
                    'urgency': 'urgent',
                    'count': len(verifications),
                    'target_url': '/unitrade/admin/users?seller_status=pending',
                    'items': [
                        {
                            'id': v.id,
                            'label': v.partner_id.name if v.partner_id else (v.name or '-'),
                            'subtitle': v.state,
                            'time_label': self._humanize_time(v.create_date),
                            'href': '/web#id=%s&model=res.partner&view_type=form' % v.partner_id.id if v.partner_id else '',
                        }
                        for v in verifications[:10]
                    ],
                })
        elif Seller is not None:
            pending = Seller.search([('status', '=', 'pending')], order='create_date asc', limit=limit_per_group)
            if pending:
                groups.append({
                    'key': 'ktm_review',
                    'title': _('Verifikasi Seller'),
                    'description': _('Seller pending review.'),
                    'urgency': 'urgent',
                    'count': len(pending),
                    'target_url': '/unitrade/admin/users?seller_status=pending',
                    'items': [
                        {
                            'id': s.id,
                            'label': s.name or s.user_id.name or '-',
                            'subtitle': s.status,
                            'time_label': self._humanize_time(s.create_date),
                            'href': '',
                        }
                        for s in pending[:10]
                    ],
                })

        # 2. Reported sellers
        if Seller is not None:
            reported = Seller.search(
                [('report_state', 'in', ('reported', 'under_review'))],
                order='last_reported_at desc',
                limit=limit_per_group,
            )
            if reported:
                groups.append({
                    'key': 'reported_sellers',
                    'title': _('Seller Dilaporkan'),
                    'description': _('Laporan seller perlu ditinjau sebelum dicabut.'),
                    'urgency': 'warning',
                    'count': len(reported),
                    'target_url': '/unitrade/admin/users',
                    'items': [
                        {
                            'id': s.id,
                            'label': s.name or '-',
                            'subtitle': s.report_state,
                            'time_label': self._humanize_time(s.last_reported_at or s.create_date),
                            'href': '',
                        }
                        for s in reported[:10]
                    ],
                })

        # 3. Refund/dispute aktif
        if Dispute is not None:
            active_states = (
                'submitted',
                'under_review',
                'need_buyer_evidence',
                'need_seller_response',
                'admin_review_final',
            )
            # 3a. Refund yang butuh KEPUTUSAN FINAL admin (paling mendesak)
            need_admin = Dispute.search(
                [('state', '=', 'admin_review_final')],
                order='create_date asc',
                limit=limit_per_group,
            )
            if need_admin:
                groups.append({
                    'key': 'refunds_need_admin',
                    'title': _('Refund Perlu Keputusan Admin'),
                    'description': _('Seller sudah meninjau. Admin harus approve/reject final.'),
                    'urgency': 'urgent',
                    'count': len(need_admin),
                    'target_url': '/unitrade/admin/refunds?status=need_admin',
                    'items': [
                        {
                            'id': d.id,
                            'label': d.name or '-',
                            'subtitle': 'Rp %s · %s' % (
                                self._format_idr(d.requested_amount), d.order_id.name or '',
                            ),
                            'time_label': self._humanize_time(d.submitted_at or d.create_date),
                            'href': '/unitrade/admin/refunds/%s' % d.id,
                        }
                        for d in need_admin[:10]
                    ],
                })

            disputes = Dispute.search(
                [('state', 'in', active_states)],
                order='create_date asc',
                limit=limit_per_group,
            )
            if disputes:
                groups.append({
                    'key': 'disputes_active',
                    'title': _('Refund / Dispute Aktif'),
                    'description': _('Semua pengajuan refund yang masih berjalan (semua tahap).'),
                    'urgency': 'warning',
                    'count': len(disputes),
                    'target_url': '/unitrade/admin/refunds?status=active',
                    'items': [
                        {
                            'id': d.id,
                            'label': d.name or '-',
                            'subtitle': '%s · %s' % (
                                self._refund_state_label(d.state), d.order_id.name or '',
                            ),
                            'time_label': self._humanize_time(d.submitted_at or d.create_date),
                            'href': '/unitrade/admin/refunds/%s' % d.id,
                        }
                        for d in disputes[:10]
                    ],
                })

        # 3b. Refund/dispute overdue (lewat SLA)
        if Dispute is not None and 'is_overdue' in Dispute._fields:
            overdue_disputes = Dispute.search(
                [('state', 'in', active_states), ('is_overdue', '=', True)],
                order='create_date asc',
                limit=limit_per_group,
            )
            if overdue_disputes:
                groups.append({
                    'key': 'disputes_overdue',
                    'title': _('Refund Lewat SLA'),
                    'description': _('Refund case yang sudah melewati deadline keputusan/respons.'),
                    'urgency': 'urgent',
                    'count': len(overdue_disputes),
                    'target_url': '/unitrade/admin/refunds?status=active',
                    'items': [
                        {
                            'id': d.id,
                            'label': d.name or '-',
                            'subtitle': '%s · %s' % (
                                self._refund_state_label(d.state), d.order_id.name or '',
                            ),
                            'time_label': self._humanize_time(d.submitted_at or d.create_date),
                            'href': '/unitrade/admin/refunds/%s' % d.id,
                        }
                        for d in overdue_disputes[:10]
                    ],
                })

        # 3c. Customer service tickets from buyer/user help flow
        if Ticket is not None:
            tickets = Ticket.search(
                [('status', 'in', ('pending', 'in_progress'))],
                order='create_date asc',
                limit=limit_per_group,
            )
            if tickets:
                groups.append({
                    'key': 'customer_tickets',
                    'title': _('Tiket Bantuan User'),
                    'description': _('Tiket customer service dari user menunggu tindak lanjut admin.'),
                    'urgency': 'urgent' if any(t.status == 'pending' for t in tickets) else 'warning',
                    'count': len(tickets),
                    'target_url': '/unitrade/admin/customer-service?queue=ticket',
                    'items': [
                        {
                            'id': t.id,
                            'label': t.name or t.title or '-',
                            'subtitle': '%s · %s' % (t.status, t.partner_id.name or '-'),
                            'time_label': self._humanize_time(t.create_date),
                            'href': '/web#id=%s&model=unitrade.customer.ticket&view_type=form' % t.id,
                        }
                        for t in tickets[:10]
                    ],
                })

        # 3d. Sponsorship requests from public marketing page
        if Sponsorship is not None:
            sponsorships = Sponsorship.search(
                [('status', '=', 'new')],
                order='create_date asc',
                limit=limit_per_group,
            )
            if sponsorships:
                groups.append({
                    'key': 'sponsorship_new',
                    'title': _('Sponsorship Baru'),
                    'description': _('Request sponsorship baru perlu dicek dan dihubungi admin.'),
                    'urgency': 'warning',
                    'count': len(sponsorships),
                    'target_url': '/unitrade/admin/sponsorships?status=new',
                    'items': [
                        {
                            'id': s.id,
                            'label': s.name or '-',
                            'subtitle': s.contact_name or s.email or s.phone or '-',
                            'time_label': self._humanize_time(s.create_date),
                            'href': '/unitrade/admin/sponsorships?q=%s#sponsorship-%s' % (
                                quote_plus(s.name or ''),
                                s.id,
                            ),
                        }
                        for s in sponsorships[:10]
                    ],
                })

        # 4. Payout siap (escrow releasable, payout belum sukses)
        if EscrowLedger is not None:
            payout_ready = EscrowLedger.search(
                [('state', '=', 'releasable'),
                 ('payout_status', 'not in', ('succeeded', 'processing'))],
                order='create_date asc',
                limit=limit_per_group,
            )
            if payout_ready:
                groups.append({
                    'key': 'payout_ready',
                    'title': _('Payout Siap Dirilis'),
                    'description': _('Escrow sudah releasable, payout belum dieksekusi.'),
                    'urgency': 'warning',
                    'count': len(payout_ready),
                    'target_url': '/web#action=unitrade_payment.action_unitrade_escrow_ledger',
                    'items': [
                        {
                            'id': l.id,
                            'label': l.name or '-',
                            'subtitle': 'Rp ' + self._format_idr(l.amount_seller),
                            'time_label': self._humanize_time(l.create_date),
                            'href': '',
                        }
                        for l in payout_ready[:10]
                    ],
                })

        # 4b. Payout batch belum diproses (draft/ready)
        Payout = (
            self.env['unitrade.seller.payout'].sudo()
            if self._has_model('unitrade.seller.payout') else None
        )
        if Payout is not None:
            pending_payouts = Payout.search(
                [('state', 'in', ('draft', 'ready'))],
                order='create_date asc',
                limit=limit_per_group,
            )
            if pending_payouts:
                groups.append({
                    'key': 'payouts_pending',
                    'title': _('Batch Payout Belum Selesai'),
                    'description': _('Payout draft atau ready menunggu konfirmasi PAID admin.'),
                    'urgency': 'warning',
                    'count': len(pending_payouts),
                    'target_url': '/web#action=unitrade_payment.action_unitrade_seller_payout',
                    'items': [
                        {
                            'id': p.id,
                            'label': p.name or '-',
                            'subtitle': '%s · Rp %s · %s ledger' % (
                                p.state, self._format_idr(p.total_amount), p.ledger_count,
                            ),
                            'time_label': self._humanize_time(p.create_date),
                            'href': '',
                        }
                        for p in pending_payouts[:10]
                    ],
                })

        # 5. Escrow stuck (held > 2x auto-confirm hours, tapi belum ada konfirmasi)
        if EscrowLedger is not None:
            try:
                auto_hours = int(params.get_param('unitrade.escrow.auto_confirm_receipt_hours', '48') or 48)
            except (TypeError, ValueError):
                auto_hours = 48
            stuck_floor = fields.Datetime.now() - timedelta(hours=auto_hours * 2)
            stuck = EscrowLedger.search(
                [('state', '=', 'held'),
                 ('seller_confirmed_at', '=', False),
                 ('create_date', '<', stuck_floor)],
                order='create_date asc',
                limit=limit_per_group,
            )
            if stuck:
                groups.append({
                    'key': 'escrow_stuck',
                    'title': _('Escrow Tertahan Lama'),
                    'description': _('Seller belum upload bukti barang melewati batas wajar.'),
                    'urgency': 'warning',
                    'count': len(stuck),
                    'target_url': '/web#action=unitrade_payment.action_unitrade_escrow_ledger',
                    'items': [
                        {
                            'id': l.id,
                            'label': l.name or '-',
                            'subtitle': 'Held %s' % self._humanize_time(l.create_date),
                            'time_label': self._humanize_time(l.create_date),
                            'href': '',
                        }
                        for l in stuck[:10]
                    ],
                })

        # 6. Listing fee pending/expired
        if PaymentIntent is not None:
            listing_pending = PaymentIntent.search(
                [('intent_type', '=', 'listing_fee'),
                 ('state', 'in', ('pending', 'expired', 'failed'))],
                order='create_date asc',
                limit=limit_per_group,
            )
            if listing_pending:
                groups.append({
                    'key': 'listing_fee_pending',
                    'title': _('Listing Fee Belum Lunas'),
                    'description': _('Produk seller menunggu fee upload.'),
                    'urgency': 'warning',
                    'count': len(listing_pending),
                    'target_url': '/web#action=unitrade_payment.action_unitrade_payment_intent',
                    'items': [
                        {
                            'id': p.id,
                            'label': p.name or '-',
                            'subtitle': '%s · Rp %s' % (p.state, self._format_idr(p.amount)),
                            'time_label': self._humanize_time(p.create_date),
                            'href': '',
                        }
                        for p in listing_pending[:10]
                    ],
                })

        # 7. Transaction overdue (paid tapi seller belum confirm)
        if 'x_payment_status' in Order._fields:
            overdue_floor = fields.Datetime.now() - timedelta(minutes=overdue_minutes)
            domain = [
                ('x_payment_status', '=', 'paid'),
                ('create_date', '<', overdue_floor),
            ]
            if 'x_unitrade_order_state' in Order._fields:
                domain.append(('x_unitrade_order_state', 'in', ('payment_pending', 'processing')))
            overdue_orders = Order.search(domain, order='create_date asc', limit=limit_per_group)
            if overdue_orders:
                groups.append({
                    'key': 'orders_overdue',
                    'title': _('Order Lewat Batas'),
                    'description': _('Order paid yang belum diproses melewati batas waktu.'),
                    'urgency': 'urgent',
                    'count': len(overdue_orders),
                    'target_url': '/unitrade/admin/transactions?state=processing',
                    'items': [
                        {
                            'id': o.id,
                            'label': o.name or '-',
                            'subtitle': 'Rp ' + self._format_idr(o.amount_total),
                            'time_label': self._humanize_time(o.create_date),
                            'href': '',
                        }
                        for o in overdue_orders[:10]
                    ],
                })

        # 8. Flagged orders
        if 'x_admin_flagged' in Order._fields:
            flagged = Order.search(
                [('x_admin_flagged', '=', True)],
                order='x_admin_flagged_at desc',
                limit=limit_per_group,
            )
            if flagged:
                groups.append({
                    'key': 'orders_flagged',
                    'title': _('Transaksi Bermasalah'),
                    'description': _('Order yang ditandai admin perlu tindak lanjut.'),
                    'urgency': 'warning',
                    'count': len(flagged),
                    'target_url': '/unitrade/admin/transactions?state=flagged',
                    'items': [
                        {
                            'id': o.id,
                            'label': o.name or '-',
                            'subtitle': getattr(o, 'x_admin_flag_reason', '') or '',
                            'time_label': self._humanize_time(getattr(o, 'x_admin_flagged_at', False) or o.write_date),
                            'href': '',
                        }
                        for o in flagged[:10]
                    ],
                })

        # Filter berdasarkan urgency jika diminta
        if urgency in ('urgent', 'warning'):
            groups = [g for g in groups if g['urgency'] == urgency]

        urgent_total = sum(g['count'] for g in groups if g['urgency'] == 'urgent')
        warning_total = sum(g['count'] for g in groups if g['urgency'] == 'warning')
        all_total = sum(g['count'] for g in groups)

        return {
            'groups': groups,
            'totals': {
                'all': all_total,
                'urgent': urgent_total,
                'warning': warning_total,
            },
            'filter': urgency,
        }

    # ---- refund / dispute management --------------------------------------

    REFUND_STATE_LABELS = {
        'draft': 'Draft',
        'submitted': 'Diajukan',
        'under_review': 'Ditinjau Admin',
        'need_buyer_evidence': 'Menunggu Bukti Buyer',
        'need_seller_response': 'Menunggu Seller',
        'admin_review_final': 'Perlu Keputusan Admin',
        'approved': 'Disetujui',
        'rejected': 'Ditolak',
        'resolved': 'Selesai',
        'cancelled': 'Dibatalkan',
    }

    REFUND_ACTIVE_STATES = (
        'submitted', 'under_review', 'need_buyer_evidence',
        'need_seller_response', 'admin_review_final',
    )

    def _refund_state_label(self, state):
        return self.REFUND_STATE_LABELS.get(state, state or '-')

    def _refund_status_key(self, state):
        if state == 'admin_review_final':
            return 'need_admin'
        if state in ('need_seller_response', 'need_buyer_evidence'):
            return 'waiting'
        if state in ('submitted', 'under_review'):
            return 'review'
        if state in ('approved', 'resolved'):
            return 'approved'
        if state == 'rejected':
            return 'rejected'
        if state == 'cancelled':
            return 'cancelled'
        return 'draft'

    @api.model
    def get_refunds_page(self, query='', status='', page=1, page_size=20):
        """Paginated dispute/refund list for the admin dashboard."""
        self._check_admin()
        if not self._has_model('unitrade.dispute'):
            return {
                'rows': [], 'page': 1, 'page_size': page_size, 'total': 0,
                'total_pages': 1, 'query': query, 'status': status, 'stats': {},
            }
        Dispute = self.env['unitrade.dispute'].sudo()

        domain = []
        if query:
            domain += ['|', '|', '|',
                       ('name', 'ilike', query),
                       ('order_id.name', 'ilike', query),
                       ('buyer_id.name', 'ilike', query),
                       ('seller_id.name', 'ilike', query)]

        status_map = {
            'need_admin': [('state', '=', 'admin_review_final')],
            'waiting': [('state', 'in', ('need_seller_response', 'need_buyer_evidence'))],
            'review': [('state', 'in', ('submitted', 'under_review'))],
            'active': [('state', 'in', list(self.REFUND_ACTIVE_STATES))],
            'approved': [('state', 'in', ('approved', 'resolved'))],
            'rejected': [('state', '=', 'rejected')],
            'cancelled': [('state', '=', 'cancelled')],
        }
        if status in status_map:
            domain += status_map[status]

        total = Dispute.search_count(domain)
        page = max(1, int(page or 1))
        page_size = int(page_size or 20)
        offset = (page - 1) * page_size
        disputes = Dispute.search(domain, limit=page_size, offset=offset, order='create_date desc')

        rows = []
        for d in disputes:
            rows.append({
                'id': d.id,
                'name': d.name or '-',
                'order_name': d.order_id.name or '-',
                'buyer_name': d.buyer_id.name or '-',
                'buyer_initials': self._initials(d.buyer_id.name),
                'seller_name': d.seller_id.name if d.seller_id else 'Penjual UniTrade',
                'reason_label': dict(d._fields['reason_code'].selection).get(d.reason_code, d.reason_code),
                'requested_amount': d.requested_amount,
                'requested_amount_display': 'Rp ' + self._format_idr(d.requested_amount),
                'state': d.state,
                'state_label': self._refund_state_label(d.state),
                'status_key': self._refund_status_key(d.state),
                'is_overdue': bool(d.is_overdue),
                'submitted_label': self._humanize_time(d.submitted_at or d.create_date),
                'detail_url': '/unitrade/admin/refunds/%s' % d.id,
            })

        total_pages = max(1, (total + page_size - 1) // page_size)
        stats = {
            'need_admin': Dispute.search_count([('state', '=', 'admin_review_final')]),
            'waiting': Dispute.search_count([('state', 'in', ('need_seller_response', 'need_buyer_evidence'))]),
            'review': Dispute.search_count([('state', 'in', ('submitted', 'under_review'))]),
            'active': Dispute.search_count([('state', 'in', list(self.REFUND_ACTIVE_STATES))]),
            'approved': Dispute.search_count([('state', 'in', ('approved', 'resolved'))]),
            'rejected': Dispute.search_count([('state', '=', 'rejected')]),
        }
        return {
            'rows': rows,
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages,
            'query': query,
            'status': status,
            'stats': stats,
        }

    @api.model
    def get_refund_detail(self, dispute_id):
        """Full detail of one dispute for the admin decision page."""
        self._check_admin()
        if not self._has_model('unitrade.dispute'):
            return {}
        dispute = self.env['unitrade.dispute'].sudo().browse(int(dispute_id)).exists()
        if not dispute:
            return {}

        currency = dispute.currency_id or self.env.company.currency_id

        # Evidence list
        evidence = []
        for ev in dispute.evidence_ids:
            mimetype = ev.attachment_id.mimetype if ev.attachment_id else ''
            is_image = mimetype in ('image/jpeg', 'image/png', 'image/webp')
            evidence.append({
                'id': ev.id,
                'type': ev.evidence_type,
                'type_label': dict(ev._fields['evidence_type'].selection).get(ev.evidence_type, ev.evidence_type),
                'note': ev.note or '',
                'url': ev.url or '',
                'has_attachment': bool(ev.attachment_id),
                'is_image': is_image,
                'image_url': '/unitrade/refund/evidence/%s/image' % ev.id if is_image else '',
                'download_url': '/unitrade/refund/evidence/%s/download' % ev.id if ev.attachment_id else '',
                'submitted_by': ev.submitted_by_id.name if ev.submitted_by_id else '',
                'created_label': self._humanize_time(ev.created_at or ev.create_date),
            })

        # Timeline
        timeline = []
        if 'timeline_ids' in dispute._fields:
            for tl in dispute.timeline_ids.sorted(lambda t: (t.sequence, t.event_time or t.create_date)):
                timeline.append({
                    'label': tl.label or tl.event_key,
                    'status': tl.status,
                    'note': tl.note or '',
                    'time_label': self._humanize_time(tl.event_time or tl.create_date),
                })

        return {
            'id': dispute.id,
            'name': dispute.name or '-',
            'state': dispute.state,
            'state_label': self._refund_state_label(dispute.state),
            'status_key': self._refund_status_key(dispute.state),
            'is_overdue': bool(dispute.is_overdue),
            'reason_code': dispute.reason_code,
            'reason_label': dict(dispute._fields['reason_code'].selection).get(dispute.reason_code, dispute.reason_code),
            'reason_note': dispute.reason_note or '',
            'requested_amount': dispute.requested_amount,
            'requested_amount_display': 'Rp ' + self._format_idr(dispute.requested_amount),
            'approved_amount': dispute.approved_amount,
            'approved_amount_display': 'Rp ' + self._format_idr(dispute.approved_amount),
            'admin_fee': dispute.refund_admin_fee_amount,
            'total_refund_display': 'Rp ' + self._format_idr(dispute.total_refund_amount),
            'admin_decision_note': dispute.admin_decision_note or '',
            'seller_decision_note': dispute.seller_decision_note or '',
            'admin_name': dispute.admin_id.name if dispute.admin_id else '',
            'final_decision_role': dispute.final_decision_role or '',
            'final_decision_by': dispute.final_decision_user_id.name if dispute.final_decision_user_id else '',
            'order': {
                'id': dispute.order_id.id,
                'name': dispute.order_id.name or '-',
                'escrow_state': getattr(dispute.order_id, 'x_escrow_state', '') or '',
                'backend_url': '/odoo/action-unitrade_dispute.action_unitrade_dispute/%s' % dispute.id,
            },
            'buyer': {
                'name': dispute.buyer_id.name or '-',
                'email': dispute.buyer_id.email or '',
                'initials': self._initials(dispute.buyer_id.name),
            },
            'seller': {
                'name': dispute.seller_id.name if dispute.seller_id else 'Penjual UniTrade',
                'initials': self._initials(dispute.seller_id.name if dispute.seller_id else 'P'),
            },
            'submitted_label': self._humanize_time(dispute.submitted_at or dispute.create_date),
            'evidence': evidence,
            'timeline': timeline,
            'actions': {
                'can_start_review': dispute.state in ('submitted', 'under_review', 'need_buyer_evidence', 'need_seller_response', 'admin_review_final'),
                'can_request_buyer_evidence': dispute.state == 'under_review',
                'can_request_seller_response': dispute.state == 'under_review',
                'can_decide': dispute.state == 'admin_review_final',
                'can_cancel': dispute.state in self.REFUND_ACTIVE_STATES,
            },
        }

    @api.model
    def admin_refund_action(self, dispute_id, action, note='', approved_amount=None, admin_fee=None):
        """Run an admin refund action, syncing the shared dispute model.

        Must be called with the REAL admin user (controller should NOT sudo
        this endpoint) so final_decision_user_id and audit reflect the actor.
        """
        self._check_admin()
        if not self._has_model('unitrade.dispute'):
            return {'ok': False, 'error': 'Dispute module tidak tersedia.'}
        dispute = self.env['unitrade.dispute'].browse(int(dispute_id)).exists()
        if not dispute:
            return {'ok': False, 'error': 'Refund tidak ditemukan.'}

        note = (note or '').strip()
        try:
            if action == 'start_review':
                dispute.action_start_review()
                msg = 'Anda kini menjadi penengah refund ini.'
            elif action == 'need_buyer_evidence':
                dispute.action_need_buyer_evidence()
                msg = 'Permintaan bukti tambahan dikirim ke buyer.'
            elif action == 'need_seller_response':
                dispute.action_need_seller_response()
                msg = 'Permintaan respons dikirim ke seller.'
            elif action == 'approve':
                # Tulis catatan + nominal sebelum approve (action model membaca field ini)
                write_vals = {'admin_decision_note': note}
                if approved_amount not in (None, ''):
                    try:
                        write_vals['approved_amount'] = float(approved_amount)
                    except (TypeError, ValueError):
                        pass
                if admin_fee not in (None, ''):
                    try:
                        write_vals['refund_admin_fee_amount'] = float(admin_fee)
                    except (TypeError, ValueError):
                        pass
                dispute.write(write_vals)
                dispute.action_approve_refund()
                msg = 'Refund disetujui. Dana akan dikembalikan ke buyer.'
            elif action == 'reject':
                dispute.write({'admin_decision_note': note})
                dispute.action_reject_refund()
                msg = 'Refund ditolak. Escrow dikembalikan ke jalur seller.'
            elif action == 'cancel':
                if note:
                    dispute.write({'admin_decision_note': note})
                dispute.action_cancel()
                msg = 'Refund case dibatalkan.'
            else:
                return {'ok': False, 'error': 'Aksi tidak dikenal.'}
        except (UserError, ValidationError, AccessError) as error:
            return {'ok': False, 'error': error.args[0] if error.args else str(error)}
        except Exception as error:  # noqa: BLE001
            _logger.exception('Admin refund action %s failed for dispute %s', action, dispute_id)
            return {'ok': False, 'error': str(error) or 'Aksi refund gagal diproses.'}

        return {'ok': True, 'message': msg, 'detail': self.get_refund_detail(dispute.id)}
