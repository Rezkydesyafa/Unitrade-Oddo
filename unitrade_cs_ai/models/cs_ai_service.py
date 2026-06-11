import json
import logging
import time

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GEMINI_API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models'
GEMINI_TIMEOUT_SECONDS = 20
AI_HISTORY_LIMIT = 5
GEMINI_MAX_RETRIES = 3            # total percobaan (1 awal + 2 retry)
GEMINI_RETRY_BACKOFF = 1.2        # jeda dasar detik antar percobaan (naik tiap percobaan)
GEMINI_RETRYABLE_STATUS = (500, 502, 503, 504)


class UnitradeCsAiService(models.AbstractModel):
    _name = 'unitrade.cs.ai.service'
    _description = 'UniTrade Customer Service AI Service (Gemini)'

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def _config(self, key, default=''):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    def _api_key(self):
        return (self._config('unitrade.gemini.api_key', '') or '').strip()

    def _model_name(self):
        return (self._config('unitrade.gemini.model', 'gemini-2.5-flash') or 'gemini-2.5-flash').strip()

    def _ai_enabled(self):
        raw = self._config('unitrade.cs.ai_enabled', 'True')
        return str(raw or '').lower() in ('true', '1', 'yes', 'y')

    def _rate_limit(self):
        try:
            return int(float(self._config('unitrade.cs.ai_rate_limit', '10') or 10))
        except (TypeError, ValueError):
            return 10

    # ------------------------------------------------------------------
    # Prompt building (tanpa konteks pesanan, sesuai keputusan prototype)
    # ------------------------------------------------------------------
    def _build_system_prompt(self, session):
        return _(
            "Kamu adalah asisten Customer Service UniTrade, marketplace jual-beli C2C "
            "untuk mahasiswa UNISA Yogyakarta. Jawab dengan ramah, ringkas, dan dalam "
            "Bahasa Indonesia. Bantu pertanyaan seputar cara belanja, pembayaran (Midtrans), "
            "pengiriman (Ambil Sendiri / GoSend), status escrow, dan kebijakan umum. "
            "Jika pertanyaan menyangkut data pribadi, pembatalan kompleks, refund, sengketa, "
            "atau hal yang tidak kamu ketahui, sarankan customer menekan tombol "
            "'Chat dengan Customer Service'. Jangan mengarang kebijakan yang tidak pasti."
        )

    def _build_contents(self, session, user_message):
        """Bangun array `contents` Gemini dari 5 pesan terakhir + pesan baru."""
        history = session.message_ids.sorted('id')[-AI_HISTORY_LIMIT:]
        contents = []
        for message in history:
            if message.author_type == 'user':
                role = 'user'
            else:
                role = 'model'  # ai & admin diperlakukan sebagai konteks model
            contents.append({'role': role, 'parts': [{'text': message.body or ''}]})
        # Pastikan pesan terbaru customer ikut (bila belum ada di history)
        if not contents or contents[-1]['role'] != 'user':
            contents.append({'role': 'user', 'parts': [{'text': user_message or ''}]})
        return contents

    # ------------------------------------------------------------------
    # API call
    # ------------------------------------------------------------------
    def generate_reply(self, session, user_message):
        if not self._ai_enabled():
            raise UserError(_('AI Customer Service sedang dinonaktifkan.'))
        api_key = self._api_key()
        if not api_key:
            raise UserError(_('Konfigurasi Gemini belum lengkap (API key kosong).'))

        payload = {
            'system_instruction': {'parts': [{'text': self._build_system_prompt(session)}]},
            'contents': self._build_contents(session, user_message),
            'generationConfig': {'temperature': 0.4, 'maxOutputTokens': 512},
        }
        url = '%s/%s:generateContent?key=%s' % (GEMINI_API_BASE, self._model_name(), api_key)
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json'}

        response = None
        last_error = ''
        for attempt in range(1, GEMINI_MAX_RETRIES + 1):
            try:
                response = requests.post(url, data=body, headers=headers, timeout=GEMINI_TIMEOUT_SECONDS)
            except requests.RequestException as error:
                # Error koneksi/timeout: anggap sementara, coba lagi.
                last_error = str(error)
                _logger.warning('Gemini request error (attempt %s/%s): %s', attempt, GEMINI_MAX_RETRIES, last_error)
                if attempt < GEMINI_MAX_RETRIES:
                    time.sleep(GEMINI_RETRY_BACKOFF * attempt)
                    continue
                raise UserError(_('Gagal menghubungi layanan AI. Coba lagi sebentar.')) from error

            if response.status_code in GEMINI_RETRYABLE_STATUS:
                # Model sibuk / overload sementara (mis. 503 UNAVAILABLE): retry.
                last_error = (response.text or '')[:300]
                _logger.warning(
                    'Gemini API %s (attempt %s/%s): %s',
                    response.status_code, attempt, GEMINI_MAX_RETRIES, last_error,
                )
                if attempt < GEMINI_MAX_RETRIES:
                    time.sleep(GEMINI_RETRY_BACKOFF * attempt)
                    continue
                raise UserError(_('Layanan AI sedang sibuk. Coba lagi sebentar.'))

            # Status final (sukses atau error non-retryable): keluar dari loop.
            break

        if response.status_code == 429:
            raise UserError(_('Batas pemakaian AI tercapai. Coba lagi sebentar.'))
        if response.status_code >= 400:
            # Jangan log URL (mengandung API key); log status & body ringkas.
            _logger.warning('Gemini API error %s: %s', response.status_code, (response.text or '')[:500])
            raise UserError(_('Layanan AI menolak permintaan.'))
        try:
            data = response.json()
        except ValueError as error:
            raise UserError(_('Respons AI tidak valid.')) from error
        return self._extract_text(data)

    def _extract_text(self, data):
        candidates = (data or {}).get('candidates') or []
        if not candidates:
            return ''
        parts = (candidates[0].get('content') or {}).get('parts') or []
        texts = [part.get('text', '') for part in parts if part.get('text')]
        return '\n'.join(texts).strip()
