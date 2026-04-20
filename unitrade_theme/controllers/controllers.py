import logging
import re
import werkzeug

from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError
from odoo.addons.auth_signup.models.res_users import SignupError
from odoo.addons.auth_signup.controllers.main import AuthSignupHome

_logger = logging.getLogger(__name__)


def _is_email(value):
    """Check if a string looks like an email address."""
    return bool(re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', value or ''))


def _is_phone(value):
    """Check if a string looks like a phone number."""
    return bool(re.match(r'^(\+62|62|08)[0-9]{8,13}$', (value or '').replace(' ', '')))


class UnitradeAuthSignup(AuthSignupHome):
    """Override signup to redirect to OTP verification page after successful registration."""

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
