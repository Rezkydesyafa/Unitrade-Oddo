import base64

from odoo import http
from odoo.http import request


class UnitradeAdminController(http.Controller):
    """Website-side admin dashboard for UniTrade."""

    # ---- helpers ----------------------------------------------------------

    def _is_admin(self):
        user = request.env.user
        return user.has_group('base.group_system') or user.has_group(
            'unitrade_seller.group_unitrade_admin'
        )

    def _forbidden(self, reason):
        return request.render(
            'unitrade_admin.admin_forbidden',
            {'reason': reason},
        )

    @staticmethod
    def _to_int(value, default=1):
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return default

    def _stats(self):
        return request.env['unitrade.admin.stats'].with_context(
            unitrade_admin_user_id=request.env.user.id,
        ).sudo()

    # ---- main pages -------------------------------------------------------

    @http.route('/unitrade/admin', type='http', auth='user', website=True)
    def admin_dashboard(self, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        data = self._stats().get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_dashboard_page',
            {'dashboard': data},
        )

    @http.route('/unitrade/admin/users', type='http', auth='user', website=True)
    def admin_users(self, q='', status='', seller_status='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        page = self._to_int(page, 1)
        users_data = Stats.get_users_page(
            query=q or '',
            status=status or '',
            seller_status=seller_status or '',
            page=page,
            page_size=20,
        )
        # Re-use dashboard data for sidebar header
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_users_page',
            {
                'dashboard': dashboard,
                'users': users_data,
            },
        )

    @http.route('/unitrade/admin/customer-service', type='http', auth='user', website=True)
    def admin_customer_service(self, queue='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        cs_data = Stats.get_customer_service_page(
            queue=queue or '',
            page=self._to_int(page, 1),
            page_size=20,
        )
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_customer_service_page',
            {
                'dashboard': dashboard,
                'customer_service': cs_data,
            },
        )

    @http.route('/unitrade/admin/sponsorships', type='http', auth='user', website=True)
    def admin_sponsorships(self, q='', status='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        sponsorships = Stats.get_sponsorships_page(
            query=q or '',
            status=status or '',
            page=self._to_int(page, 1),
            page_size=20,
        )
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_sponsorships_page',
            {
                'dashboard': dashboard,
                'sponsorships': sponsorships,
            },
        )

    @http.route('/unitrade/admin/deliveries', type='http', auth='user', website=True)
    def admin_deliveries(self, q='', status='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        return request.redirect('/unitrade/admin/transactions')

    @http.route(['/unitrade/admin/reviews', '/unitrade/admin/review'], type='http', auth='user', website=True)
    def admin_reviews(self, q='', visibility='', rating=0, page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        reviews = Stats.get_reviews_page(
            query=q or '',
            visibility=visibility or '',
            rating=rating or 0,
            page=self._to_int(page, 1),
            page_size=20,
        )
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_reviews_page',
            {
                'dashboard': dashboard,
                'reviews': reviews,
            },
        )

    @http.route(['/unitrade/admin/payouts', '/unitrade/admin/payout'], type='http', auth='user', website=True)
    def admin_payouts(self, q='', state='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        payouts = Stats.get_payouts_page(
            query=q or '',
            state=state or '',
            page=self._to_int(page, 1),
            page_size=20,
        )
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_payouts_page',
            {
                'dashboard': dashboard,
                'payouts': payouts,
            },
        )

    @http.route(['/unitrade/admin/announcements', '/unitrade/admin/announcement'], type='http', auth='user', website=True)
    def admin_announcements(self, q='', state='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        announcements = Stats.get_announcements_page(
            query=q or '',
            state=state or '',
            page=self._to_int(page, 1),
            page_size=20,
        )
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_announcements_page',
            {
                'dashboard': dashboard,
                'announcements': announcements,
            },
        )

    @http.route('/unitrade/admin/products', type='http', auth='user', website=True)
    def admin_products(self, q='', status='', fee_status='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        product_data = Stats.get_products_page(
            query=q or '',
            status=status or '',
            fee_status=fee_status or '',
            page=self._to_int(page, 1),
            page_size=20,
        )
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_products_page',
            {
                'dashboard': dashboard,
                'products': product_data,
            },
        )

    @http.route('/unitrade/admin/transactions', type='http', auth='user', website=True)
    def admin_transactions(self, q='', state='', date_from='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        page = self._to_int(page, 1)
        tx_data = Stats.get_transactions_page(
            query=q or '',
            state=state or '',
            date_from=date_from or '',
            page=page,
            page_size=20,
        )
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_transactions_page',
            {
                'dashboard': dashboard,
                'transactions': tx_data,
            },
        )

    @http.route('/unitrade/admin/vouchers', type='http', auth='user', website=True)
    def admin_vouchers(self, q='', status='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        voucher_data = Stats.get_vouchers_page(
            query=q or '',
            status=status or '',
            page=self._to_int(page, 1),
            page_size=20,
        )
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_vouchers_page',
            {
                'dashboard': dashboard,
                'vouchers': voucher_data,
            },
        )

    @http.route('/unitrade/admin/reports', type='http', auth='user', website=True)
    def admin_reports(self, date_from='', date_to='', **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        report_data = Stats.get_reports(date_from=date_from, date_to=date_to)
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_reports_page',
            {
                'dashboard': dashboard,
                'report': report_data,
            },
        )

    @http.route('/unitrade/admin/audit-logs', type='http', auth='user', website=True)
    def admin_audit_logs(self, q='', severity='', actor_id=0, date_from='', date_to='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        audit_logs = Stats.get_audit_logs_page(
            query=q or '',
            severity=severity or '',
            actor_id=actor_id or 0,
            date_from=date_from or '',
            date_to=date_to or '',
            page=self._to_int(page, 1),
            page_size=25,
        )
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_audit_logs_page',
            {
                'dashboard': dashboard,
                'audit_logs': audit_logs,
            },
        )

    @http.route('/unitrade/admin/reports/export.csv', type='http', auth='user')
    def admin_reports_export(self, date_from='', date_to='', **kwargs):
        if not self._is_admin():
            return request.not_found()
        rows = self._stats().export_orders_csv(
            date_from=date_from, date_to=date_to,
        )
        # CSV encode (manual to avoid import csv with file IO complexity)
        import io
        import csv
        buf = io.StringIO()
        writer = csv.writer(buf)
        for r in rows:
            writer.writerow(r)
        content = buf.getvalue()
        filename = 'unitrade-orders-{}-{}.csv'.format(
            date_from or 'all', date_to or 'all',
        )
        return request.make_response(
            content,
            headers=[
                ('Content-Type', 'text/csv; charset=utf-8'),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ],
        )

    @http.route('/unitrade/admin/reports/summary.csv', type='http', auth='user')
    def admin_reports_summary_export(self, date_from='', date_to='', **kwargs):
        if not self._is_admin():
            return request.not_found()
        rows = self._stats().export_report_summary_csv(
            date_from=date_from, date_to=date_to,
        )
        import io
        import csv
        buf = io.StringIO()
        writer = csv.writer(buf)
        for row in rows:
            writer.writerow(row)
        content = buf.getvalue()
        filename = 'unitrade-admin-summary-{}-{}.csv'.format(
            date_from or 'all', date_to or 'all',
        )
        return request.make_response(
            content,
            headers=[
                ('Content-Type', 'text/csv; charset=utf-8'),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ],
        )

    @http.route('/unitrade/admin/settings', type='http', auth='user', website=True)
    def admin_settings(self, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        settings_data = Stats.get_settings()
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_settings_page',
            {
                'dashboard': dashboard,
                'settings': settings_data,
            },
        )

    @http.route('/unitrade/admin/api/settings/save', type='json', auth='user')
    def api_save_settings(self, values=None, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().save_settings(values or {})

    @http.route('/unitrade/admin/api/customer-tickets/status', type='json', auth='user')
    def api_update_customer_ticket_status(self, ticket_id=0, status='', **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_update_customer_ticket_status(ticket_id, status)

    @http.route('/unitrade/admin/api/customer-service/detail', type='json', auth='user')
    def api_customer_service_detail(self, case_type='', case_id=0, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().get_customer_service_detail(case_type, case_id)

    @http.route('/unitrade/admin/api/audit-logs/detail', type='json', auth='user')
    def api_audit_log_detail(self, log_id=0, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().get_audit_log_detail(log_id)

    @http.route('/unitrade/admin/api/sponsorships/update', type='json', auth='user')
    def api_update_sponsorship(self, request_id=0, status='', note='', **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_update_sponsorship(request_id, status=status, note=note)

    @http.route('/unitrade/admin/api/deliveries/status', type='json', auth='user')
    def api_update_delivery_status(self, delivery_id=0, status='', **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return {
            'ok': False,
            'error': 'Monitoring delivery dinonaktifkan. Gunakan Monitoring Transaksi untuk alur serah terima.',
        }

    @http.route('/unitrade/admin/api/reviews/visibility', type='json', auth='user')
    def api_review_visibility(self, review_id=0, visible=False, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_toggle_review_visibility(review_id, visible)

    @http.route('/unitrade/admin/api/payouts/action', type='json', auth='user')
    def api_payout_action(self, payout_id=0, action='', payment_reference='', cancel_reason='', **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_run_payout_action(
            payout_id,
            action,
            payment_reference=payment_reference or '',
            cancel_reason=cancel_reason or '',
        )

    @http.route('/unitrade/admin/api/announcements/create', type='json', auth='user')
    def api_create_announcement(self, values=None, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_create_announcement(values or {})

    @http.route('/unitrade/admin/api/announcements/detail', type='json', auth='user')
    def api_announcement_detail(self, announcement_id=0, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().get_announcement_detail(announcement_id)

    @http.route('/unitrade/admin/api/announcements/publish', type='json', auth='user')
    def api_publish_announcement(self, announcement_id=0, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_publish_announcement(announcement_id)

    @http.route('/unitrade/admin/api/announcements/sync', type='json', auth='user')
    def api_sync_announcement_notifications(self, announcement_id=0, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_sync_announcement_notifications(announcement_id)

    @http.route('/unitrade/admin/api/notifications', type='json', auth='user')
    def api_notifications(self, **kwargs):
        if not self._is_admin():
            return {'items': [], 'total': 0}
        return self._stats().get_notifications()

    @http.route('/unitrade/admin/notifications', type='http', auth='user', website=True)
    def admin_notifications(self, status='', priority='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        notifications = Stats.get_notifications_page(
            status=status or '',
            priority=priority or '',
            page=self._to_int(page, 1),
        )
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_notifications_page',
            {
                'dashboard': dashboard,
                'notifications': notifications,
                'filter_status': status or '',
                'filter_priority': priority or '',
            },
        )

    @http.route('/unitrade/admin/api/notifications/read', type='json', auth='user')
    def api_notification_read(self, notification_id=0, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().mark_notification_read(notification_id)

    @http.route('/unitrade/admin/api/notifications/read_all', type='json', auth='user')
    def api_notifications_read_all(self, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().mark_all_notifications_read()

    @http.route('/unitrade/admin/tasks', type='http', auth='user', website=True)
    def admin_tasks(self, urgency='', **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        task_queue = Stats.get_task_queue(urgency=urgency or '')
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_tasks_page',
            {
                'dashboard': dashboard,
                'task_queue': task_queue,
                'filter_urgency': urgency or '',
            },
        )

    @http.route('/unitrade/admin/ktm/<string:source>/<int:record_id>', type='http', auth='user')
    def admin_ktm_image(self, source, record_id, **kwargs):
        if not self._is_admin():
            return request.not_found()

        if source == 'verification':
            model_name = 'unitrade.seller.verification'
        elif source == 'seller':
            model_name = 'unitrade.seller'
        else:
            return request.not_found()

        if model_name not in request.env:
            return request.not_found()

        record = request.env[model_name].sudo().browse(record_id).exists()
        if not record or not getattr(record, 'ktm_image', False):
            return request.not_found()

        raw = base64.b64decode(record.ktm_image)
        filename = (getattr(record, 'ktm_filename', '') or '').lower()
        if filename.endswith('.png'):
            content_type = 'image/png'
        elif filename.endswith('.webp'):
            content_type = 'image/webp'
        else:
            content_type = 'image/jpeg'

        return request.make_response(
            raw,
            headers=[
                ('Content-Type', content_type),
                ('Cache-Control', 'private, max-age=300'),
            ],
        )

    @http.route('/unitrade/admin/media/attachment/<int:attachment_id>', type='http', auth='user')
    def admin_attachment_media(self, attachment_id, download='', **kwargs):
        if not self._is_admin():
            return request.not_found()
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not attachment or not attachment.datas:
            return request.not_found()

        raw = base64.b64decode(attachment.datas or b'')
        filename = (attachment.name or 'unitrade-bukti').replace('"', '')
        disposition = 'attachment' if str(download).lower() in ('1', 'true', 'yes') else 'inline'
        return request.make_response(
            raw,
            headers=[
                ('Content-Type', attachment.mimetype or 'application/octet-stream'),
                ('Content-Disposition', '%s; filename="%s"' % (disposition, filename)),
                ('Cache-Control', 'private, max-age=300'),
            ],
        )

    @http.route('/unitrade/admin/media/escrow/<string:kind>/<int:ledger_id>', type='http', auth='user')
    def admin_escrow_media(self, kind, ledger_id, download='', **kwargs):
        if not self._is_admin() or kind not in ('seller', 'buyer'):
            return request.not_found()
        if 'unitrade.escrow.ledger' not in request.env:
            return request.not_found()

        ledger = request.env['unitrade.escrow.ledger'].sudo().browse(ledger_id).exists()
        if not ledger:
            return request.not_found()

        field_name = 'seller_handoff_image' if kind == 'seller' else 'buyer_received_image'
        filename_field = 'seller_handoff_filename' if kind == 'seller' else 'buyer_received_filename'
        if field_name not in ledger._fields or not ledger[field_name]:
            return request.not_found()

        raw = base64.b64decode(ledger[field_name])
        filename = (ledger[filename_field] if filename_field in ledger._fields else '') or 'bukti-%s.jpg' % kind
        filename = filename.replace('"', '')
        lower_name = filename.lower()
        content_type = 'image/jpeg'
        if lower_name.endswith('.png'):
            content_type = 'image/png'
        elif lower_name.endswith('.webp'):
            content_type = 'image/webp'
        disposition = 'attachment' if str(download).lower() in ('1', 'true', 'yes') else 'inline'
        return request.make_response(
            raw,
            headers=[
                ('Content-Type', content_type),
                ('Content-Disposition', '%s; filename="%s"' % (disposition, filename)),
                ('Cache-Control', 'private, max-age=300'),
            ],
        )

    @http.route('/unitrade/admin/api/tasks', type='json', auth='user')
    def api_tasks(self, urgency='', **kwargs):
        if not self._is_admin():
            return {'groups': [], 'totals': {'all': 0, 'urgent': 0, 'warning': 0}}
        return self._stats().get_task_queue(urgency=urgency or '')

    # ---- refund / dispute management -------------------------------------

    @http.route('/unitrade/admin/refunds', type='http', auth='user', website=True)
    def admin_refunds(self, q='', status='', page=1, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        page = self._to_int(page, 1)
        refunds = Stats.get_refunds_page(
            query=q or '', status=status or '', page=page, page_size=20,
        )
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_refunds_page',
            {'dashboard': dashboard, 'refunds': refunds},
        )

    @http.route('/unitrade/admin/refunds/<int:dispute_id>', type='http', auth='user', website=True)
    def admin_refund_detail(self, dispute_id, **kwargs):
        if not self._is_admin():
            return self._forbidden('Akun Anda tidak memiliki akses admin UniTrade.')
        Stats = self._stats()
        detail = Stats.get_refund_detail(dispute_id)
        if not detail:
            return request.not_found()
        dashboard = Stats.get_dashboard_data()
        return request.render(
            'unitrade_admin.admin_refund_detail_page',
            {'dashboard': dashboard, 'refund': detail},
        )

    @http.route('/unitrade/admin/api/refunds', type='json', auth='user')
    def api_refunds(self, q='', status='', page=1, **kwargs):
        if not self._is_admin():
            return {'rows': [], 'total': 0}
        return self._stats().get_refunds_page(
            query=q or '', status=status or '', page=self._to_int(page, 1), page_size=20,
        )

    @http.route('/unitrade/admin/api/refunds/detail', type='json', auth='user')
    def api_refund_detail(self, dispute_id, **kwargs):
        if not self._is_admin():
            return {}
        return self._stats().get_refund_detail(dispute_id)

    @http.route('/unitrade/admin/api/refunds/action', type='json', auth='user')
    def api_refund_action(self, dispute_id, action, note='', approved_amount=None, admin_fee=None, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        # NOTE: NOT using sudo() so the dispute action records the real admin
        # user as final_decision_user_id and audit actor.
        return request.env['unitrade.admin.stats'].admin_refund_action(
            dispute_id, action, note=note,
            approved_amount=approved_amount, admin_fee=admin_fee,
        )

    # ---- JSON endpoints for write actions --------------------------------

    @http.route('/unitrade/admin/api/users/block', type='json', auth='user')
    def api_block_user(self, user_id, reason='', **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_block_user(user_id, reason)

    @http.route('/unitrade/admin/api/users/unblock', type='json', auth='user')
    def api_unblock_user(self, user_id, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_unblock_user(user_id)

    @http.route('/unitrade/admin/api/admins/create', type='json', auth='user')
    def api_create_admin_user(self, values=None, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_create_admin_user(values or {})

    @http.route('/unitrade/admin/api/sellers/approve', type='json', auth='user')
    def api_approve_seller(self, seller_id, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_approve_seller(seller_id)

    @http.route('/unitrade/admin/api/sellers/reject', type='json', auth='user')
    def api_reject_seller(self, seller_id, reason='', **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_reject_seller(seller_id, reason)

    @http.route('/unitrade/admin/api/verifications/approve', type='json', auth='user')
    def api_approve_verification(self, verification_id, nim='', **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_approve_verification(verification_id, nim=nim)

    @http.route('/unitrade/admin/api/verifications/reject', type='json', auth='user')
    def api_reject_verification(self, verification_id, reason='', **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_reject_verification(verification_id, reason)

    @http.route('/unitrade/admin/api/sellers/reset', type='json', auth='user')
    def api_reset_seller(self, seller_id, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_reset_seller_to_draft(seller_id)

    @http.route('/unitrade/admin/api/users/note', type='json', auth='user')
    def api_save_user_note(self, user_id, note='', **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_save_user_note(user_id, note)

    @http.route('/unitrade/admin/api/users/resend_otp', type='json', auth='user')
    def api_resend_otp(self, user_id, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_resend_verification_email(user_id)

    @http.route('/unitrade/admin/api/users/detail', type='json', auth='user')
    def api_user_detail(self, user_id, **kwargs):
        if not self._is_admin():
            return {}
        return self._stats().get_user_detail(user_id)

    @http.route('/unitrade/admin/api/orders/flag', type='json', auth='user')
    def api_flag_order(self, order_id, reason='', **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_flag_order(order_id, reason)

    @http.route('/unitrade/admin/api/orders/unflag', type='json', auth='user')
    def api_unflag_order(self, order_id, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_unflag_order(order_id)

    @http.route('/unitrade/admin/api/orders/detail', type='json', auth='user')
    def api_order_detail(self, order_id, **kwargs):
        if not self._is_admin():
            return {}
        return self._stats().get_order_detail(order_id)

    @http.route('/unitrade/admin/api/products/detail', type='json', auth='user')
    def api_product_detail(self, product_id=0, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().get_product_detail(product_id)

    @http.route('/unitrade/admin/api/products/action', type='json', auth='user')
    def api_product_action(self, product_id=0, action='', reason='', publish_after=True, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_run_product_action(
            product_id,
            action=action,
            reason=reason,
            publish_after=publish_after,
        )

    @http.route('/unitrade/admin/api/vouchers/create', type='json', auth='user')
    def api_create_voucher(self, values=None, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_create_voucher(values or {})

    @http.route('/unitrade/admin/api/vouchers/update', type='json', auth='user')
    def api_update_voucher(self, voucher_id=0, values=None, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_update_voucher(voucher_id, values or {})

    @http.route('/unitrade/admin/api/vouchers/toggle', type='json', auth='user')
    def api_toggle_voucher(self, voucher_id=0, active=None, **kwargs):
        if not self._is_admin():
            return {'ok': False, 'error': 'forbidden'}
        return self._stats().admin_toggle_voucher(voucher_id, active)

    # ---- raw data endpoint (kept for convenience) ------------------------

    @http.route('/unitrade/admin/data', type='json', auth='user')
    def admin_dashboard_data(self, **kwargs):
        if not self._is_admin():
            return {'error': 'forbidden'}
        return self._stats().get_dashboard_data()
