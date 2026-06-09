import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class UnitradeCsAdmin(http.Controller):

    def _json_error(self, message, code='error'):
        return {'success': False, 'error': code, 'message': message}

    def _is_admin(self):
        user = request.env.user
        return (
            user.has_group('unitrade_seller.group_unitrade_admin')
            or user.has_group('base.group_system')
        )

    def _session(self, session_id):
        try:
            session_id = int(session_id or 0)
        except (TypeError, ValueError):
            session_id = 0
        session = request.env['unitrade.cs.session'].sudo().browse(session_id).exists()
        if not session:
            raise UserError('Sesi tidak ditemukan.')
        return session

    @http.route('/unitrade/admin/api/cs/queue', type='json', auth='user', website=True, methods=['POST'])
    def queue(self, **kwargs):
        if not self._is_admin():
            return self._json_error('Akses ditolak.', code='forbidden')
        sessions = request.env['unitrade.cs.session'].sudo().search([
            ('state', 'in', ('waiting_admin', 'admin_handling')),
        ], order='last_activity desc')
        return {
            'success': True,
            'sessions': [{
                **session._session_payload(request.env.user),
                'user_name': session.user_id.name,
                'last_activity': session.last_activity and session.last_activity.strftime('%Y-%m-%d %H:%M'),
                'ticket_id': session.ticket_id.id or False,
            } for session in sessions],
        }

    @http.route('/unitrade/admin/api/cs/detail', type='json', auth='user', website=True, methods=['POST'])
    def detail(self, session_id=None, **kwargs):
        if not self._is_admin():
            return self._json_error('Akses ditolak.', code='forbidden')
        try:
            session = self._session(session_id)
            return {
                'success': True,
                'session': session._session_payload(request.env.user),
                'messages': [message._message_payload() for message in session.message_ids.sorted('id')],
            }
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))

    @http.route('/unitrade/admin/api/cs/reply', type='json', auth='user', website=True, methods=['POST'])
    def reply(self, session_id=None, body=None, **kwargs):
        if not self._is_admin():
            return self._json_error('Akses ditolak.', code='forbidden')
        try:
            session = self._session(session_id)
            message = session.admin_reply(body, admin=request.env.user)
            return {
                'success': True,
                'session': session._session_payload(request.env.user),
                'message': message._message_payload(),
            }
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))

    @http.route('/unitrade/admin/api/cs/close', type='json', auth='user', website=True, methods=['POST'])
    def close(self, session_id=None, **kwargs):
        if not self._is_admin():
            return self._json_error('Akses ditolak.', code='forbidden')
        try:
            session = self._session(session_id)
            session.close_session(admin=request.env.user)
            return {'success': True, 'session': session._session_payload(request.env.user)}
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))
