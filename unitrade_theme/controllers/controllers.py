import logging
import re
import werkzeug
import base64
import json
import glob
import os

from odoo import http, _, SUPERUSER_ID, fields, tools
from odoo.http import request
from odoo.exceptions import UserError, AccessDenied
from odoo.service import security
from odoo.addons.auth_signup.models.res_users import SignupError
from odoo.addons.auth_oauth.controllers.main import OAuthLogin, OAuthController
from odoo.addons.portal.controllers.portal import get_error
from odoo.addons.sale.controllers.portal import CustomerPortal
from odoo.addons.website.controllers.main import Website
from werkzeug import urls

_logger = logging.getLogger(__name__)


def _is_email(value):
    """Check if a string looks like an email address."""
    return bool(re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', value or ''))


def _is_phone(value):
    """Check if a string looks like a phone number."""
    return bool(re.match(r'^(\+62|62|08)[0-9]{8,13}$', (value or '').replace(' ', '')))


class UnitradeAuthSignup(OAuthLogin):
    """Override signup and login to redirect to OTP verification page."""

    @http.route()
    def web_login(self, *args, **kw):
        """Override web_login to enforce OTP verification for unverified portal users."""
        response = super().web_login(*args, **kw)

        if request.httprequest.method == 'POST' and request.session.uid:
            user = request.env['res.users'].sudo().browse(request.session.uid)

            # Only enforce OTP for portal/public users, skip internal/admin
            if user.exists() and not user.is_otp_verified and not user.has_group('base.group_user'):
                _logger.info("User %s logged in but OTP not verified. Redirecting to OTP.", user.login)

                # Save user info, then logout to prevent bypassing OTP
                user_sudo = user.sudo()
                login_val = user.login
                request.session.logout(keep_db=True)
                request.env['ir.http']._auth_method_public()

                return self._generate_and_redirect_otp(user_sudo, login_val)

        return response

    @http.route('/web/signup', type='http', auth='public', website=True, sitemap=False)
    def web_auth_signup(self, *args, **kw):
        """Override signup: on success, generate OTP and redirect to verification page."""
        qcontext = self.get_auth_signup_qcontext()

        if not qcontext.get('token') and not qcontext.get('signup_enabled'):
            raise werkzeug.exceptions.NotFound()

        if 'error' not in qcontext and request.httprequest.method == 'POST':
            try:
                if not request.env['ir.http']._verify_request_recaptcha_token('signup'):
                    raise UserError(_("Suspicious activity detected by Google reCaptcha."))

                self.do_signup(qcontext)

                if request.session.uid is None:
                    public_user = request.env.ref('base.public_user')
                    request.update_env(user=public_user)

                # --- OTP FLOW ---
                login_value = qcontext.get('login', '')
                user_sudo = request.env['res.users'].sudo().search(
                    [('login', '=', login_value)], limit=1
                )

                if user_sudo:
                    return self._generate_and_redirect_otp(user_sudo, login_value)
                else:
                    return self.web_login(*args, **kw)

            except UserError as e:
                qcontext['error'] = e.args[0]
            except (SignupError, AssertionError) as e:
                existing_user = request.env["res.users"].sudo().search(
                    [("login", "=", qcontext.get("login"))], limit=1
                )
                if existing_user:
                    # User already exists — try to authenticate and send OTP
                    try:
                        login_value = qcontext.get('login', '')
                        pre_uid = request.session.authenticate(
                            request.db, login_value, qcontext.get('password')
                        )
                        if pre_uid:
                            return self._generate_and_redirect_otp(existing_user, login_value)
                        else:
                            qcontext["error"] = _("Email/No.HP sudah terdaftar. Password salah.")
                    except Exception:
                        qcontext["error"] = _("Email/No.HP sudah terdaftar. Silakan masuk.")
                else:
                    _logger.warning("%s", e)
                    qcontext['error'] = _("Could not create a new account.") + "\n" + str(e)

        elif 'signup_email' in qcontext:
            from werkzeug.urls import url_encode
            user = request.env['res.users'].sudo().search(
                [('email', '=', qcontext.get('signup_email')), ('state', '!=', 'new')], limit=1
            )
            if user:
                return request.redirect('/web/login?%s' % url_encode({
                    'login': user.login, 'redirect': '/web'
                }))

        response = request.render('auth_signup.signup', qcontext)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    @http.route('/web/signup/check_email', type='json', auth='public', methods=['POST'], csrf=False)
    def check_email_exists(self, **kw):
        """Check if an email or phone number already exists in the database."""
        login = kw.get('login', '').strip()
        if not login:
            return {'exists': False}
        existing_user = request.env['res.users'].sudo().search(
            [('login', '=', login)], limit=1
        )
        return {'exists': bool(existing_user)}

    @http.route('/web/reset_password', type='http', auth='public', website=True, sitemap=False)
    def web_auth_reset_password(self, *args, **kw):
        """Override reset password to show success message instead of auto-login after password change."""
        qcontext = self.get_auth_signup_qcontext()

        if not qcontext.get('token') and not qcontext.get('reset_password_enabled'):
            raise werkzeug.exceptions.NotFound()

        if 'error' not in qcontext and request.httprequest.method == 'POST':
            try:
                if not request.env['ir.http']._verify_request_recaptcha_token('password_reset'):
                    raise UserError(_("Suspicious activity detected by Google reCaptcha."))
                if qcontext.get('token'):
                    self.do_signup(qcontext)
                    # Instead of calling web_login (which triggers OTP and shows 'login' error),
                    # set a flag and render the reset password page with a success message.
                    qcontext['password_changed'] = True
                    _logger.info("Password successfully changed, showing success message.")
                else:
                    login = qcontext.get('login')
                    assert login, _("No login provided.")
                    _logger.info(
                        "Password reset attempt for <%s> by user <%s> from %s",
                        login, request.env.user.login, request.httprequest.remote_addr)
                    request.env['res.users'].sudo().reset_password(login)
                    qcontext['message'] = _("Password reset instructions sent to your email")
            except UserError as e:
                qcontext['error'] = e.args[0]
            except SignupError:
                qcontext['error'] = _("Could not reset your password")
                _logger.exception('error when resetting password')
            except Exception as e:
                qcontext['error'] = str(e)

        elif 'signup_email' in qcontext:
            from werkzeug.urls import url_encode
            user = request.env['res.users'].sudo().search(
                [('email', '=', qcontext.get('signup_email')), ('state', '!=', 'new')], limit=1)
            if user:
                return request.redirect('/web/login?%s' % url_encode({'login': user.login, 'redirect': '/web'}))

        response = request.render('auth_signup.reset_password', qcontext)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    def _generate_and_redirect_otp(self, user_sudo, login_value):
        """Generate OTP, send it, store session, and redirect to verify page."""
        try:
            otp_model = request.env['unitrade.otp'].sudo()
            otp_record = otp_model.generate_otp(user_sudo.id, login_value)
            otp_code = otp_record.code

            is_email_login = _is_email(login_value)
            sent_via = 'none'

            if is_email_login:
                # Send OTP via email
                self._send_otp_email(user_sudo, otp_code)
                sent_via = 'email'
            else:
                # Phone number — can't send SMS without third-party API
                # Log the code for development purposes
                _logger.warning(
                    "========== OTP CODE FOR %s: %s ==========",
                    login_value, otp_code
                )
                sent_via = 'phone'

            # Store in session
            request.session['otp_user_id'] = user_sudo.id
            request.session['otp_email'] = login_value
            request.session['otp_verified'] = False
            request.session['otp_sent_via'] = sent_via
            request.session['otp_code_dev'] = otp_code  # Dev only — remove in production!

            _logger.info("OTP generated for %s via %s, redirecting to verify", login_value, sent_via)
            return request.redirect('/web/verify-otp')

        except Exception as e:
            _logger.error("OTP generation failed for %s: %s", login_value, str(e))
            return self.web_login()

    def _build_otp_email_html(self, code, user_name=''):
        """Build professional HTML email template for OTP."""
        display_name = user_name or 'Pengguna UniTrade'
        year = '2026'
        return f"""
<!DOCTYPE html>
<html lang="id">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/></head>
<body style="margin:0;padding:0;background-color:#f4f4f5;font-family:'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f5;padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="520" cellpadding="0" cellspacing="0" style="max-width:520px;width:100%;">

  <!-- HEADER BANNER -->
  <tr><td style="background-color:#ffffff;border-radius:12px 12px 0 0;padding:40px 40px 24px;text-align:center;border-bottom:1px solid #e5e5e5;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td align="center">
        <!-- Logo instead of shield icon -->
        <img src="/unitrade_theme/static/src/img/logo-unitrade.png" alt="UniTrade Logo" style="height:32px;display:block;margin:0 auto 16px;"/>
        <h1 style="margin:0;font-size:22px;font-weight:700;color:#171717;letter-spacing:-0.3px;">Verifikasi Akun</h1>
      </td>
    </tr></table>
  </td></tr>

  <!-- BODY -->
  <tr><td style="background-color:#ffffff;padding:32px 40px;">
    <p style="margin:0 0 6px;font-size:14px;color:#737373;">Halo,</p>
    <p style="margin:0 0 24px;font-size:17px;font-weight:600;color:#171717;">{display_name} &#x1F44B;</p>

    <p style="margin:0 0 24px;font-size:14px;line-height:22px;color:#525252;">
      Kami menerima permintaan untuk memverifikasi akun UniTrade Anda.
      Gunakan kode verifikasi di bawah ini untuk menyelesaikan proses pendaftaran:
    </p>

    <!-- OTP CODE BOX -->
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
    <tr><td style="background:linear-gradient(135deg,#fafafa 0%,#f0f0f0 100%);border:2px dashed #d4d4d4;border-radius:12px;padding:28px 20px;text-align:center;">
      <p style="margin:0 0 8px;font-size:11px;font-weight:600;color:#a3a3a3;text-transform:uppercase;letter-spacing:2px;">Kode Verifikasi</p>
      <p style="margin:0;font-size:36px;font-weight:800;color:#171717;letter-spacing:10px;font-family:'Courier New',monospace;">{code}</p>
    </td></tr>
    </table>

    <!-- EXPIRY WARNING -->
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
    <tr><td style="background-color:#fffbeb;border-left:4px solid #f59e0b;border-radius:0 8px 8px 0;padding:12px 16px;">
      <p style="margin:0;font-size:13px;color:#92400e;">
        &#x23F1; Kode ini berlaku selama <strong>5 menit</strong>. Segera masukkan sebelum kedaluwarsa.
      </p>
    </td></tr>
    </table>

    <!-- DIVIDER -->
    <hr style="border:none;border-top:1px solid #e5e5e5;margin:0 0 24px;"/>

    <!-- SECURITY TIPS -->
    <p style="margin:0 0 8px;font-size:13px;font-weight:600;color:#171717;"> Tips Keamanan:</p>
    <p style="margin:0;font-size:13px;color:#525252;line-height:20px;">
        Jangan bagikan kode ini kepada siapapun. UniTrade tidak pernah meminta kode verifikasi melalui telepon. Jika Anda tidak merasa mendaftar, abaikan email ini.
    </p>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background-color:#fafafa;border-radius:0 0 12px 12px;padding:24px 40px;border-top:1px solid #e5e5e5;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td align="center" style="padding-bottom:16px;">
        <p style="margin:0;font-size:15px;font-weight:700;color:#171717;">UniTrade</p>
        <p style="margin:4px 0 0;font-size:11px;color:#a3a3a3;">Marketplace Terpercaya Indonesia</p>
      </td></tr>
      <tr><td align="center" style="padding-bottom:16px;">
        <table role="presentation" cellpadding="0" cellspacing="0"><tr>
          <td style="padding:0 8px;"><a href="https://unitrade.dev" style="display:inline-block;width:32px;height:32px;background:#171717;border-radius:50%;text-align:center;line-height:32px;text-decoration:none;"><span style="color:#fff;font-size:14px;">&#x1F310;</span></a></td>
          <td style="padding:0 8px;"><a href="#" style="display:inline-block;width:32px;height:32px;background:#171717;border-radius:50%;text-align:center;line-height:32px;text-decoration:none;"><span style="color:#fff;font-size:14px;">&#x1F426;</span></a></td>
          <td style="padding:0 8px;"><a href="#" style="display:inline-block;width:32px;height:32px;background:#171717;border-radius:50%;text-align:center;line-height:32px;text-decoration:none;"><span style="color:#fff;font-size:14px;">&#x1F4F7;</span></a></td>
        </tr></table>
      </td></tr>
      <tr><td align="center">
        <p style="margin:0 0 4px;font-size:11px;color:#a3a3a3;line-height:18px;">
          Email ini dikirim secara otomatis. Mohon jangan membalas email ini.
        </p>
        <p style="margin:0;font-size:11px;color:#d4d4d4;">
          &copy; {year} UniTrade. Hak cipta dilindungi undang-undang.
        </p>
      </td></tr>
    </table>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>
"""

    def _send_otp_email(self, user, code):
        """Send OTP code via email using Odoo's mail system."""
        try:
            email_to = user.login if _is_email(user.login) else (user.email or user.login)
            user_name = user.name or user.login
            template_values = {
                'email_from': request.env.company.email or 'noreply@unitrade.dev',
                'email_to': email_to,
                'subject': 'UniTrade - Kode Verifikasi Akun Anda',
                'body_html': self._build_otp_email_html(code, user_name),
                'auto_delete': True,
            }
            mail = request.env['mail.mail'].sudo().create(template_values)
            mail.send()
            _logger.info("OTP email sent to %s", email_to)
        except Exception as e:
            _logger.error("Failed to send OTP email: %s", str(e))

    @http.route('/web/send-otp-email', type='json', auth='public', website=True)
    def send_otp_to_email(self, email='', **kw):
        """Send OTP to a specific email address (when user signed up with phone)."""
        user_id = request.session.get('otp_user_id')
        if not user_id:
            return {'success': False, 'message': 'Session expired.'}

        if not _is_email(email):
            return {'success': False, 'message': 'Masukkan email yang valid.'}

        try:
            user = request.env['res.users'].sudo().browse(user_id)
            otp_model = request.env['unitrade.otp'].sudo()
            otp_record = otp_model.generate_otp(user_id, email)

            self._send_otp_email_direct(email, otp_record.code)

            # Update session
            request.session['otp_sent_via'] = 'email'
            request.session['otp_code_dev'] = otp_record.code

            return {'success': True, 'message': f'Kode OTP telah dikirim ke {email}'}
        except Exception as e:
            _logger.error("Failed to send OTP to email %s: %s", email, str(e))
            return {'success': False, 'message': 'Gagal mengirim. Coba lagi nanti.'}

    def _send_otp_email_direct(self, email_to, code):
        """Send OTP code directly to a specified email address."""
        try:
            template_values = {
                'email_from': request.env.company.email or 'noreply@unitrade.dev',
                'email_to': email_to,
                'subject': '🔐 UniTrade - Kode Verifikasi Akun Anda',
                'body_html': self._build_otp_email_html(code, email_to),
                'auto_delete': True,
            }
            mail = request.env['mail.mail'].sudo().create(template_values)
            mail.send()
            _logger.info("OTP email sent directly to %s", email_to)
        except Exception as e:
            _logger.error("Failed to send OTP email to %s: %s", email_to, str(e))


class UnitradeOTPController(http.Controller):
    """Controller for OTP verification page."""

    @http.route('/web/verify-otp', type='http', auth='public', website=True, sitemap=False)
    def verify_otp_page(self, **kw):
        """Render the OTP verification page."""
        user_id = request.session.get('otp_user_id')
        email = request.session.get('otp_email', '')
        sent_via = request.session.get('otp_sent_via', 'email')
        otp_code_dev = request.session.get('otp_code_dev', '')

        if not user_id:
            return request.redirect('/web/login')

        masked = self._mask_value(email)

        values = {
            'masked_email': masked,
            'login_value': email,
            'sent_via': sent_via,
            'is_phone': _is_phone(email),
            'is_email': _is_email(email),
            'otp_code_dev': otp_code_dev,  # Dev only
            'error': kw.get('error', ''),
        }
        return request.render('unitrade_theme.verify_otp_page', values)

    @http.route('/web/verify-otp/submit', type='http', auth='public', website=True, sitemap=False, methods=['POST'])
    def verify_otp_submit(self, **kw):
        """Handle OTP form submission."""
        user_id = request.session.get('otp_user_id')

        if not user_id:
            return request.redirect('/web/login')

        code = ''
        for i in range(1, 7):
            digit = kw.get(f'digit{i}', '')
            code += digit

        if len(code) != 6:
            return request.redirect('/web/verify-otp?error=Masukkan 6 digit kode verifikasi')

        otp_model = request.env['unitrade.otp'].sudo()
        is_valid = otp_model.verify_otp(user_id, code)

        if is_valid:
            # Mark user as verified
            try:
                user = request.env['res.users'].sudo().browse(user_id)
                user.write({'is_otp_verified': True})
            except Exception as e:
                _logger.error("Failed to mark user as OTP verified: %s", str(e))

            # Re-authenticate the user (they were logged out before OTP)
            user = request.env['res.users'].sudo().browse(user_id)
            request.session.uid = user_id
            request.session.login = user.login
            request.session.db = request.db
            request.update_env(user=user_id)
            request.session.session_token = security.compute_session_token(request.session, request.env)
            request.session.rotate = True
            _logger.info("User %s authenticated after OTP verification", user.login)

            request.session['otp_verified'] = True
            for key in ('otp_user_id', 'otp_email', 'otp_code_dev', 'otp_sent_via'):
                request.session.pop(key, None)
            return request.redirect('/')
        else:
            return request.redirect('/web/verify-otp?error=Kode verifikasi salah atau sudah kedaluwarsa')

    @http.route('/web/resend-otp', type='json', auth='public', website=True)
    def resend_otp(self, **kw):
        """Handle resend OTP request (AJAX)."""
        user_id = request.session.get('otp_user_id')
        email = request.session.get('otp_email')

        if not user_id or not email:
            return {'success': False, 'message': 'Session expired.'}

        try:
            user = request.env['res.users'].sudo().browse(user_id)
            otp_model = request.env['unitrade.otp'].sudo()
            otp_record = otp_model.generate_otp(user_id, email)

            if _is_email(email):
                signup_ctrl = UnitradeAuthSignup()
                signup_ctrl._send_otp_email(user, otp_record.code)

            request.session['otp_code_dev'] = otp_record.code

            _logger.warning("========== RESEND OTP FOR %s: %s ==========", email, otp_record.code)

            return {'success': True, 'message': 'Kode baru telah dikirim!', 'code_dev': otp_record.code}
        except Exception as e:
            _logger.error("Failed to resend OTP: %s", str(e))
            return {'success': False, 'message': 'Gagal mengirim ulang kode.'}

    def _mask_value(self, value):
        """Mask email or phone for display."""
        if not value:
            return '****'
        if _is_phone(value):
            if len(value) > 4:
                return value[:4] + '****' + value[-2:]
            return '****'
        if '@' in value:
            local, domain = value.split('@', 1)
            if len(local) <= 1:
                return '*@' + domain
            return local[0] + '***@' + domain
        return '****'


class UnitradePortalProfile(CustomerPortal):
    """Render and update the UniTrade user profile page."""

    _MAX_AVATAR_BYTES = 2 * 1024 * 1024
    _ORDER_STATUSES = ('all', 'unpaid', 'done', 'cancel')

    @http.route(['/my/account'], type='http', auth='user', website=True)
    def account(self, redirect=None, **post):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        user = request.env.user
        error = {}
        error_message = []

        if post and request.httprequest.method == 'POST':
            error, error_message, partner_vals, user_vals = self._prepare_unitrade_profile_values(post)
            values.update(post)

            if not error:
                if partner_vals:
                    partner.sudo().write(partner_vals)
                if user_vals:
                    user.sudo().write(user_vals)
                return request.redirect(redirect or '/my/account?profile_saved=1')

        values.update({
            'partner': partner,
            'user_profile': user,
            'form_values': dict(post or {}),
            'error': error,
            'error_message': error_message,
            'redirect': redirect,
            'page_name': 'my_details',
            'profile_saved': request.params.get('profile_saved') == '1',
        })

        response = request.render('portal.portal_my_details', values)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    @http.route('/my/security', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def security(self, **post):
        """Keep old Odoo portal URL as a redirect to the UniTrade settings URL."""
        return request.redirect('/my/settings')

    @http.route('/my/settings', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def settings(self, **post):
        """Render and process the UniTrade settings page."""
        values = self._prepare_unitrade_settings_values()

        if request.httprequest.method == 'POST':
            operation = post.get('op')
            if operation == 'password':
                values.update(self._update_password(
                    (post.get('old') or '').strip(),
                    (post.get('new1') or '').strip(),
                    (post.get('new2') or '').strip()
                ))

        response = request.render('portal.portal_my_security', values)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    @http.route('/my/settings/notifications', type='json', auth='user', website=True, methods=['POST'])
    def update_settings_notifications(self, field=None, value=None, **kwargs):
        """Persist notification switches from the settings page."""
        field_name = field if field in {
            'x_notify_all',
            'x_notify_transaction',
            'x_notify_promo',
        } else None
        if not field_name:
            return {'success': False, 'message': _('Pengaturan notifikasi tidak valid.')}

        enabled = bool(value)
        user = request.env.user.sudo()
        vals = {field_name: enabled}
        if field_name == 'x_notify_all':
            vals.update({
                'x_notify_transaction': enabled,
                'x_notify_promo': enabled,
            })
        else:
            transaction = enabled if field_name == 'x_notify_transaction' else user.x_notify_transaction
            promo = enabled if field_name == 'x_notify_promo' else user.x_notify_promo
            vals['x_notify_all'] = bool(transaction and promo)
        user.write(vals)
        return {
            'success': True,
            'values': {
                'x_notify_all': user.x_notify_all,
                'x_notify_transaction': user.x_notify_transaction,
                'x_notify_promo': user.x_notify_promo,
            },
        }

    @http.route('/my/settings/session/revoke', type='http', auth='user', website=True, methods=['POST'])
    def revoke_settings_session(self, sid=None, **post):
        """Revoke one session owned by the current user."""
        if not sid:
            return request.redirect('/my/settings')

        if sid == request.session.sid:
            request.session.logout()
            return request.redirect('/web/login?redirect=/')

        session_store = http.root.session_store
        if session_store.is_valid_key(sid):
            session = session_store.get(sid)
            if session.get('uid') == request.env.uid:
                session_store.delete(session)
        return request.redirect('/my/settings')

    @http.route('/my/deactivate_account', type='http', auth='user', website=True, methods=['POST'])
    def deactivate_account(self, validation, password, **post):
        """Render UniTrade settings again when account deactivation validation fails."""
        values = self._prepare_unitrade_settings_values()
        values['open_deactivate_modal'] = True

        if validation != request.env.user.login:
            values['errors'] = {'deactivate': 'validation'}
        else:
            try:
                request.env['res.users']._check_credentials(password, {'interactive': True})
                request.env.user.sudo()._deactivate_portal_user(**post)
                request.session.logout()
                return request.redirect('/web/login?message=%s' % urls.url_quote(_('Account deleted!')))
            except AccessDenied:
                values['errors'] = {'deactivate': 'password'}
            except UserError as e:
                values['errors'] = {'deactivate': {'other': str(e)}}

        response = request.render('portal.portal_my_security', values)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    def _prepare_unitrade_settings_values(self):
        self._touch_unitrade_session_activity()
        user = request.env.user.sudo()
        values = self._prepare_portal_layout_values()
        values.update({
            'get_error': get_error,
            'errors': {},
            'success': {},
            'allow_api_keys': bool(request.env['ir.config_parameter'].sudo().get_param('portal.allow_api_keys')),
            'open_deactivate_modal': False,
            'page_name': 'my_settings',
            'notify_all': user.x_notify_all,
            'notify_transaction': user.x_notify_transaction,
            'notify_promo': user.x_notify_promo,
            'session_activity': self._unitrade_session_activity(),
        })
        return values

    def _touch_unitrade_session_activity(self):
        session = request.session
        session['unitrade_user_agent'] = request.httprequest.headers.get('User-Agent', '')
        session['unitrade_remote_addr'] = request.httprequest.remote_addr or ''
        session['unitrade_last_seen'] = fields.Datetime.to_string(fields.Datetime.now())

    def _unitrade_session_activity(self):
        session_store = http.root.session_store
        path = getattr(session_store, 'path', '')
        pattern = os.path.join(path, '*', '*')
        rows = []
        for filename in glob.iglob(pattern):
            sid = os.path.basename(filename)
            if sid.endswith('.__wz_sess') or not session_store.is_valid_key(sid):
                continue
            try:
                session = session_store.get(sid)
            except Exception:
                _logger.debug("Unable to read portal session %s", sid, exc_info=True)
                continue
            if session.get('uid') != request.env.uid:
                continue
            rows.append({
                'sid': sid,
                'is_current': sid == request.session.sid,
                'device_name': self._unitrade_device_name(session.get('unitrade_user_agent') or ''),
                'ip_label': session.get('unitrade_remote_addr') or '-',
                'last_seen': self._unitrade_session_last_seen(session.get('unitrade_last_seen')),
            })

        rows.sort(key=lambda row: (not row['is_current'], row['device_name']))
        if not rows:
            rows.append({
                'sid': request.session.sid,
                'is_current': True,
                'device_name': self._unitrade_device_name(request.httprequest.headers.get('User-Agent', '')),
                'ip_label': request.httprequest.remote_addr or '-',
                'last_seen': _('Sedang aktif'),
            })
        return rows[:4]

    @staticmethod
    def _unitrade_device_name(user_agent):
        user_agent_l = (user_agent or '').lower()
        if 'android' in user_agent_l:
            return 'Android'
        if 'iphone' in user_agent_l or 'ipad' in user_agent_l:
            return 'iOS'
        if 'windows' in user_agent_l:
            if 'chrome' in user_agent_l:
                return 'Chrome di windows 11'
            return 'Windows'
        if 'mac os' in user_agent_l:
            return 'MacOS'
        return 'Browser'

    @staticmethod
    def _unitrade_session_last_seen(value):
        if not value:
            return _('Sedang aktif')
        try:
            dt_value = fields.Datetime.from_string(value)
            return 'Aktif %s' % fields.Datetime.context_timestamp(request.env.user, dt_value).strftime('%d %B %Y, %H:%M')
        except Exception:
            return _('Sedang aktif')

    def _prepare_unitrade_profile_values(self, post):
        error = {}
        error_message = []
        partner_vals = {}
        user_vals = {}

        name = (post.get('name') or '').strip()
        email = (post.get('email') or '').strip()
        gender = (post.get('x_gender') or '').strip()
        birth_date = (post.get('x_birth_date') or '').strip()
        phone = (post.get('phone') or '').strip()
        street = (post.get('street') or '').strip()
        zipcode = (post.get('zipcode') or '').strip()

        if not name:
            error['name'] = 'missing'
            error_message.append(_('Nama pengguna wajib diisi.'))

        if email and not tools.single_email_re.match(email):
            error['email'] = 'error'
            error_message.append(_('Masukkan email yang valid.'))

        if birth_date:
            try:
                user_vals['x_birth_date'] = fields.Date.to_date(birth_date)
            except ValueError:
                error['x_birth_date'] = 'error'
                error_message.append(_('Format tanggal lahir tidak valid.'))
        else:
            user_vals['x_birth_date'] = False

        if gender in ('male', 'female'):
            user_vals['x_gender'] = gender
        else:
            user_vals['x_gender'] = False

        avatar_file = post.get('avatar_upload')
        if avatar_file and getattr(avatar_file, 'filename', ''):
            avatar_content = avatar_file.read()
            content_type = (getattr(avatar_file, 'content_type', '') or '').lower()
            if len(avatar_content) > self._MAX_AVATAR_BYTES:
                error['avatar_upload'] = 'too_large'
                error_message.append(_('Ukuran foto profil maksimal 2MB.'))
            elif content_type and not content_type.startswith('image/'):
                error['avatar_upload'] = 'invalid'
                error_message.append(_('Foto profil harus berupa file gambar.'))
            else:
                user_vals['image_1920'] = base64.b64encode(avatar_content)

        partner_vals.update({
            'name': name,
            'email': email,
            'phone': phone,
            'street': street,
            'zip': zipcode,
        })

        return error, error_message, partner_vals, user_vals

    @http.route([
        '/my/orders',
        '/my/orders/page/<int:page>',
        '/my/account/orders',
    ], type='http', auth='user', website=True)
    def portal_my_orders(self, page=1, status='all', **kwargs):
        """Render the UniTrade customer orders page with dynamic sale.order data."""
        values = self._prepare_portal_layout_values()
        active_status = status if status in self._ORDER_STATUSES else 'all'
        order_items = self._unitrade_customer_order_items()
        request.session['my_orders_history'] = list({
            item['order'].id for item in order_items
        })[:100]
        status_counts = {
            'all': len(order_items),
            'unpaid': len([item for item in order_items if item['status'] == 'unpaid']),
            'done': len([item for item in order_items if item['status'] == 'done']),
            'cancel': len([item for item in order_items if item['status'] == 'cancel']),
        }

        values.update({
            'page_name': 'my_orders',
            'order_items': order_items,
            'order_status_counts': status_counts,
            'order_status_counts_json': json.dumps(status_counts),
            'active_order_status': active_status,
        })
        response = request.render('unitrade_theme.unitrade_portal_my_orders', values)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    def _unitrade_customer_order_items(self):
        partner = request.env.user.partner_id.commercial_partner_id
        partners = request.env['res.partner'].sudo().search([('commercial_partner_id', '=', partner.id)])
        orders = request.env['sale.order'].sudo().search([
            ('partner_id', 'in', partners.ids),
            ('state', 'in', ['sent', 'sale', 'done', 'cancel']),
        ], order='date_order desc', limit=80)

        Review = request.env['unitrade.review'].sudo() if 'unitrade.review' in request.env.registry else False
        items = []
        for order in orders:
            status_key = self._unitrade_order_status_key(order)
            order_lines = order.order_line.filtered(lambda line: not line.display_type and line.product_id)
            for line in order_lines:
                product = line.product_id.product_tmpl_id
                seller = product.x_seller_id if 'x_seller_id' in product._fields and product.x_seller_id else False
                seller_ref = seller.x_profile_uuid or seller.id if seller else ''
                review_exists = False
                if Review and status_key == 'done':
                    review_exists = bool(Review.search_count([
                        ('order_id', '=', order.id),
                        ('product_id', '=', product.id),
                        ('user_id', '=', request.env.uid),
                    ]))

                can_buy_again = self._unitrade_can_buy_again(product, line.product_id)
                items.append({
                    'id': '%s-%s' % (order.id, line.id),
                    'status': status_key,
                    'order': order,
                    'line': line,
                    'product': product,
                    'seller': seller,
                    'seller_name': seller.name if seller else (order.user_id.name or 'Penjual UniTrade'),
                    'seller_avatar_url': self._unitrade_seller_avatar_url(seller),
                    'seller_url': '/seller-profile/%s' % seller_ref if seller_ref else '#',
                    'seller_chat_url': '/seller-profile/%s/chat' % seller_ref if seller_ref else '#',
                    'product_url': product.website_url or '/shop/product/%s' % product.id,
                    'review_url': (product.website_url or '/shop/product/%s' % product.id) + '#tab-ulasan',
                    'buy_again_url': product.website_url or '/shop/product/%s' % product.id,
                    'can_buy_again': can_buy_again,
                    'image_url': '/web/image/product.template/%s/image_512' % product.id,
                    'category': product.categ_id.name if product.categ_id else '-',
                    'quantity': self._unitrade_quantity_label(line.product_uom_qty),
                    'rating': self._unitrade_rating_label(product),
                    'price': self._unitrade_format_money(line.price_total, order.currency_id),
                    'can_review': status_key == 'done' and not review_exists,
                    'review_exists': review_exists,
                })
        return items

    @staticmethod
    def _unitrade_can_buy_again(product, variant):
        if not product or not product.exists():
            return False
        if not product.sale_ok or not product.website_published:
            return False
        if 'qty_available' in variant._fields:
            return variant.qty_available > 0
        if 'qty_available' in product._fields:
            return product.qty_available > 0
        return True

    @staticmethod
    def _unitrade_order_status_key(order):
        if order.state == 'cancel':
            return 'cancel'
        if order.state in ('sale', 'done'):
            return 'done'
        return 'unpaid'

    @staticmethod
    def _unitrade_quantity_label(quantity):
        if float(quantity or 0).is_integer():
            return str(int(quantity))
        return ('%.2f' % quantity).rstrip('0').rstrip('.')

    @staticmethod
    def _unitrade_rating_label(product):
        rating = product.x_average_rating if 'x_average_rating' in product._fields else 0.0
        return '%.1f' % (rating or 0.0)

    @staticmethod
    def _unitrade_format_money(amount, currency):
        symbol = currency.symbol or 'Rp'
        formatted = ('{:,.0f}'.format(amount or 0.0)).replace(',', '.')
        if currency.position == 'after':
            return '%s %s' % (formatted, symbol)
        return '%s %s' % (symbol, formatted)

    @staticmethod
    def _unitrade_seller_avatar_url(seller):
        if seller and seller.user_id:
            return '/web/image/res.users/%s/image_128?unique=%s' % (
                seller.user_id.id,
                seller.user_id.write_date or '',
            )
        return '/web/static/img/user_menu_avatar.png'


class UnitradeOAuthController(OAuthController):
    """Override OAuth signin to auto-verify Google users (skip OTP)."""

    @http.route('/auth_oauth/signin', type='http', auth='none')
    def signin(self, **kw):
        """After Google OAuth signin, auto-set is_otp_verified = True."""
        response = super().signin(**kw)

        # If login was successful (session.uid is set), mark user as OTP verified
        if request.session.uid:
            try:
                user = request.env['res.users'].sudo().browse(request.session.uid)
                if user.exists() and not user.is_otp_verified:
                    user.write({'is_otp_verified': True})
                    _logger.info("Google OAuth user %s auto-verified (OTP skipped).", user.login)
            except Exception as e:
                _logger.error("Failed to auto-verify OAuth user: %s", str(e))

        return response


class UnitradeWebsite(Website):
    """Override website homepage to inject Best Quality products."""

    @http.route('/', type='http', auth="public", website=True, sitemap=True)
    def index(self, **kw):
        """Override homepage route to pass 'products' variable for Kualitas Terbaik section."""
        # Get response from original website controller
        response = super(UnitradeWebsite, self).index(**kw)
        
        # Fetch published products
        Product = request.env['product.template'].sudo()
        published_products = Product.search([('website_published', '=', True)])
        
        # Sort by rating_avg (desc) and sales_count (desc), then take top 8
        best_products = published_products.sorted(
            key=lambda p: (p.rating_avg or 0.0, p.sales_count or 0.0),
            reverse=True
        )[:8]

        # Inject into qcontext so template can render them
        if hasattr(response, 'qcontext'):
            response.qcontext['products'] = best_products
            
        return response
