import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class UnitradeCsPortal(http.Controller):
    """Endpoint chatbot Customer Service AI (dipakai oleh floating widget)."""

    def _json_error(self, message, code='error'):
        return {'success': False, 'error': code, 'message': message}

    def _session(self, session_id):
        try:
            session_id = int(session_id or 0)
        except (TypeError, ValueError):
            session_id = 0
        session = request.env['unitrade.cs.session'].sudo().browse(session_id).exists()
        if not session:
            raise UserError('Sesi tidak ditemukan.')
        session._check_participant(request.env.user)
        return session

    def _active_session(self, session_id=None):
        if session_id:
            return self._session(session_id)
        return request.env['unitrade.cs.session'].get_or_create_active(request.env.user)

    def _history_payload(self, session):
        return [message._message_payload() for message in session.message_ids.sorted('id')]

    @http.route('/customer-service/chat/session', type='json', auth='user', website=True, methods=['POST'])
    def cs_chat_session(self, **kwargs):
        try:
            session = request.env['unitrade.cs.session'].get_or_create_active(request.env.user)
            return {
                'success': True,
                'session': session._session_payload(request.env.user),
                'messages': self._history_payload(session),
                'quick_replies': request.env['unitrade.cs.session']._quick_replies(),
            }
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))
        except Exception:
            _logger.exception('CS session bootstrap failed')
            return self._json_error('Customer Service gagal dimuat.', code='bootstrap_failed')

    @http.route('/customer-service/chat/send', type='json', auth='user', website=True, methods=['POST'])
    def cs_chat_send(self, session_id=None, body=None, **kwargs):
        try:
            session = self._active_session(session_id)
            result = session.post_user_message(body)
            payload = {
                'success': True,
                'session': session._session_payload(request.env.user),
                'user_message': result['user_message']._message_payload(),
            }
            if result.get('ai_message'):
                payload['ai_message'] = result['ai_message']._message_payload()
            return payload
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))
        except Exception:
            _logger.exception('CS send failed')
            return self._json_error('Pesan gagal dikirim.', code='send_failed')

    @http.route('/customer-service/chat/escalate', type='json', auth='user', website=True, methods=['POST'])
    def cs_chat_escalate(self, session_id=None, **kwargs):
        try:
            session = self._active_session(session_id)
            session.escalate_to_admin()
            return {'success': True, 'session': session._session_payload(request.env.user)}
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))
        except Exception:
            _logger.exception('CS escalate failed')
            return self._json_error('Eskalasi gagal.', code='escalate_failed')

    @http.route('/customer-service/chat/history', type='json', auth='user', website=True, methods=['POST'])
    def cs_chat_history(self, session_id=None, **kwargs):
        try:
            session = self._session(session_id)
            return {
                'success': True,
                'session': session._session_payload(request.env.user),
                'messages': self._history_payload(session),
            }
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))
