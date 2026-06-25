import logging
import uuid

from odoo import _, api, models, fields
from odoo.exceptions import AccessDenied

_logger = logging.getLogger(__name__)
UNITRADE_CHAT_ONLINE_SECONDS = 90


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_otp_verified = fields.Boolean(string='Is OTP Verified', default=False)
    x_gender = fields.Selection([
        ('male', 'Laki-laki'),
        ('female', 'Perempuan'),
    ], string='Jenis Kelamin')
    x_birth_date = fields.Date(string='Tanggal Lahir')
    x_notify_all = fields.Boolean(string='Semua Notifikasi UniTrade', default=True)
    x_notify_transaction = fields.Boolean(string='Notifikasi Transaksi UniTrade', default=True)
    x_notify_promo = fields.Boolean(string='Notifikasi Promo UniTrade', default=True)
    x_terms_privacy_accepted = fields.Boolean(string='Terms & Privacy Accepted', default=False, readonly=True)
    x_terms_privacy_accepted_at = fields.Datetime(string='Terms & Privacy Accepted At', readonly=True)
    x_terms_privacy_version = fields.Char(string='Terms & Privacy Version', readonly=True)
    x_terms_privacy_ip = fields.Char(string='Terms & Privacy IP', readonly=True)
    x_terms_privacy_user_agent = fields.Char(string='Terms & Privacy User Agent', readonly=True)
    x_privacy_deactivated = fields.Boolean(string='Privacy Deactivated', default=False, readonly=True)
    x_privacy_deactivated_at = fields.Datetime(string='Privacy Deactivated At', readonly=True)
    x_privacy_anonymized_ref = fields.Char(string='Privacy Anonymized Reference', readonly=True)

    def _unitrade_chat_is_online(self):
        """Shared UniTrade chat presence check used by chat and storefront."""
        self.ensure_one()
        if 'x_unitrade_chat_last_seen' not in self._fields or not self.x_unitrade_chat_last_seen:
            return False
        delta = fields.Datetime.now() - self.x_unitrade_chat_last_seen
        return delta.total_seconds() <= UNITRADE_CHAT_ONLINE_SECONDS

    def unitrade_allows_notification(self, category):
        """Return whether UniTrade may send a non-security notification to this user."""
        self.ensure_one()
        if category == 'transaction':
            return bool(self.x_notify_all and self.x_notify_transaction)
        if category == 'promo':
            return bool(self.x_notify_all and self.x_notify_promo)
        return bool(self.x_notify_all)

    def unitrade_accept_terms_privacy(self, ip_address=False, user_agent=False, session_id=False):
        """Persist Terms & Privacy consent metadata for signup and audit."""
        version = self.env['ir.config_parameter'].sudo().get_param(
            'unitrade.terms_privacy_version',
            '2026-05-17',
        )
        activity_model = self.env['unitrade.security.activity'].sudo()
        for user in self.sudo():
            user.write({
                'x_terms_privacy_accepted': True,
                'x_terms_privacy_accepted_at': fields.Datetime.now(),
                'x_terms_privacy_version': version,
                'x_terms_privacy_ip': ip_address or '',
                'x_terms_privacy_user_agent': user_agent or '',
            })
            activity_model.record_activity(
                user,
                'consent_accepted',
                title='Terms & Privacy disetujui',
                detail='Versi dokumen %s' % version,
                ip_address=ip_address,
                user_agent=user_agent,
                session_id=session_id,
            )
        return True

    def unitrade_record_security_activity(self, event_type, title=False, detail=False,
                                          ip_address=False, user_agent=False, session_id=False):
        activity_model = self.env['unitrade.security.activity'].sudo()
        activities = self.env['unitrade.security.activity'].sudo().browse()
        for user in self.sudo():
            activities |= activity_model.record_activity(
                user,
                event_type,
                title=title,
                detail=detail,
                ip_address=ip_address,
                user_agent=user_agent,
                session_id=session_id,
            )
        return activities

    def unitrade_privacy_deactivate(self, reason=False, ip_address=False, user_agent=False, session_id=False):
        """Privacy-safe account deletion: deactivate and mask personal data, keep audit/order rows."""
        for user in self.sudo():
            anonymized_ref = 'deleted-user-%s-%s' % (user.id, uuid.uuid4().hex[:10])
            partner = user.partner_id.sudo()
            partner_vals = {
                'name': 'Pengguna Dihapus',
                'email': False,
                'phone': False,
                'mobile': False,
                'street': False,
                'street2': False,
                'city': False,
                'zip': False,
            }
            for field_name in (
                'x_unitrade_province',
                'x_unitrade_city',
                'x_unitrade_district',
                'x_unitrade_village',
                'x_unitrade_address_label',
                'x_unitrade_mapbox_place_id',
            ):
                if field_name in partner._fields:
                    partner_vals[field_name] = False
            for field_name in ('x_unitrade_latitude', 'x_unitrade_longitude'):
                if field_name in partner._fields:
                    partner_vals[field_name] = 0.0
            if partner.exists():
                partner.write(partner_vals)

            if 'unitrade.seller' in self.env.registry:
                sellers = self.env['unitrade.seller'].sudo().search([('user_id', '=', user.id)])
                sellers.write({
                    'x_store_active': False,
                    'x_delete_requested': True,
                    'x_delete_requested_at': fields.Datetime.now(),
                })

            vals = {
                'name': 'Pengguna Dihapus',
                'login': anonymized_ref,
                'email': False,
                'active': False,
                'x_privacy_deactivated': True,
                'x_privacy_deactivated_at': fields.Datetime.now(),
                'x_privacy_anonymized_ref': anonymized_ref,
                'x_gender': False,
                'x_birth_date': False,
                'x_notify_all': False,
                'x_notify_transaction': False,
                'x_notify_promo': False,
            }
            for field_name in ('oauth_uid', 'oauth_provider_id', 'oauth_access_token'):
                if field_name in user._fields:
                    vals[field_name] = False
            user.write(vals)
            user.unitrade_record_security_activity(
                'deactivate_anonymize',
                title='Akun dinonaktifkan dan dianonimkan',
                detail=reason or 'Permintaan hapus akun dari halaman pengaturan.',
                ip_address=ip_address,
                user_agent=user_agent,
                session_id=session_id,
            )
        return True

    def unitrade_send_notification_email(self, category, subject, body_html, email_values=None):
        """Send an email only when the user's UniTrade notification preference allows it."""
        self.ensure_one()
        if not self.unitrade_allows_notification(category):
            _logger.info(
                "Skipped UniTrade %s notification for user %s because it is disabled.",
                category, self.login,
            )
            return False

        email_to = self.email or self.partner_id.email
        if not email_to:
            _logger.info("Skipped UniTrade %s notification for user %s because email is empty.", category, self.login)
            return False

        values = {
            'email_to': email_to,
            'subject': subject,
            'body_html': body_html,
            'auto_delete': True,
        }
        if email_values:
            values.update(email_values)
        return self.env['mail.mail'].sudo().create(values).send()

    @api.model
    def _auth_oauth_signin(self, provider, validation, params):
        """Override to link existing users by email when signing in via OAuth.
        
        If a user registered via normal signup with the same email,
        link their account to the OAuth provider instead of failing.
        """
        oauth_uid = validation['user_id']
        
        # First, try the standard flow: search by oauth_uid + provider
        oauth_user = self.search([
            ("oauth_uid", "=", oauth_uid),
            ('oauth_provider_id', '=', provider)
        ])
        if oauth_user:
            oauth_user.write({'oauth_access_token': params['access_token']})
            return oauth_user.login

        # Not found by oauth_uid — try to find existing user by email
        email = validation.get('email')
        if email:
            if (
                'unitrade.account.blacklist' in self.env.registry
                and self.env['unitrade.account.blacklist'].sudo().is_contact_blocked(email=email)
            ):
                raise AccessDenied(_('Email ini tidak dapat digunakan untuk masuk ke UniTrade.'))
            existing_user = self.search([('login', '=', email)], limit=1)
            if existing_user:
                # Link the existing account to Google OAuth
                existing_user.write({
                    'oauth_provider_id': provider,
                    'oauth_uid': oauth_uid,
                    'oauth_access_token': params['access_token'],
                })
                _logger.info(
                    "Linked existing user %s to OAuth provider %s",
                    existing_user.login, provider
                )
                return existing_user.login

        # No existing user found — fall back to default signup flow
        return super()._auth_oauth_signin(provider, validation, params)
