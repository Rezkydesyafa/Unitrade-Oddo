# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import re

_logger = logging.getLogger(__name__)


class UnisaStudent(models.Model):
    """Reference table for UNISA Yogyakarta students."""
    _name = 'unisa.student'
    _description = 'UNISA Student Reference'
    _order = 'nim'

    nim = fields.Char(
        string='NIM',
        required=True,
        index=True,
    )
    name = fields.Char(
        string='Nama Mahasiswa',
        required=True,
    )
    faculty = fields.Char(
        string='Fakultas',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )

    _sql_constraints = [
        ('nim_unique', 'UNIQUE(nim)', 'NIM sudah terdaftar!'),
    ]


class SellerVerification(models.Model):
    """KTM verification record for seller onboarding."""
    _name = 'unitrade.seller.verification'
    _description = 'Seller KTM Verification'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        tracking=True,
        ondelete='cascade',
    )
    university_id = fields.Many2one(
        'unitrade.university',
        string='Universitas',
        tracking=True,
        ondelete='restrict',
    )
    university_other = fields.Char(
        string='Universitas Lainnya',
        tracking=True,
    )
    ktm_image = fields.Binary(
        string='Foto KTM',
        attachment=True,
    )
    ktm_filename = fields.Char(
        string='Nama File KTM',
    )
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Attachment',
    )

    # OCR results
    ocr_raw_text = fields.Text(
        string='Hasil OCR (Raw)',
        readonly=True,
    )
    nim_extracted = fields.Char(
        string='NIM Terdeteksi',
        readonly=True,
        tracking=True,
    )
    nim_valid = fields.Boolean(
        string='NIM Format Valid',
        readonly=True,
        default=False,
    )
    nim_registered = fields.Boolean(
        string='NIM Terdaftar',
        readonly=True,
        default=False,
    )
    name_confidence = fields.Float(
        string='Name Confidence Score',
        digits=(4, 3),
        readonly=True,
        default=0.0,
    )
    student_name = fields.Char(
        string='Nama Mahasiswa DB',
        readonly=True,
    )
    name_match_token = fields.Char(
        string='Token Nama Cocok',
        readonly=True,
    )
    confidence_flag = fields.Selection([
        ('low', 'Low Confidence'),
        ('high', 'High Confidence'),
    ], string='Confidence Flag',
        readonly=True,
    )
    duplicate_seller_id = fields.Many2one(
        'unitrade.seller',
        string='Duplikasi Seller',
        readonly=True,
    )
    duplicate_warning = fields.Boolean(
        string='Ada Duplikasi NIM',
        readonly=True,
    )
    image_width = fields.Integer(
        string='Lebar Gambar',
        readonly=True,
    )
    image_height = fields.Integer(
        string='Tinggi Gambar',
        readonly=True,
    )
    upload_attempt_count = fields.Integer(
        string='Jumlah Upload Window Ini',
        default=0,
        readonly=True,
    )
    upload_window_start = fields.Datetime(
        string='Awal Window Upload',
        readonly=True,
    )
    rejection_reason = fields.Text(
        string='Alasan Penolakan',
        tracking=True,
    )
    reviewed_by = fields.Many2one(
        'res.users',
        string='Direview Oleh',
        readonly=True,
    )
    reviewed_date = fields.Datetime(
        string='Tanggal Review',
        readonly=True,
    )
    review_note = fields.Text(
        string='Catatan Review',
        tracking=True,
    )
    state_changed_by = fields.Many2one(
        'res.users',
        string='Status Diubah Oleh',
        readonly=True,
    )
    state_changed_at = fields.Datetime(
        string='Status Diubah Pada',
        readonly=True,
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Menunggu Review'),
        ('manual_review', 'Manual Review'),
        ('approved', 'Disetujui'),
        ('rejected', 'Ditolak'),
    ], string='Status',
        default='draft',
        tracking=True,
        index=True,
    )

    def write(self, vals):
        old_states = {record.id: record.state for record in self} if 'state' in vals else {}
        if 'state' in vals:
            vals = dict(vals)
            vals.setdefault('state_changed_by', self.env.uid)
            vals.setdefault('state_changed_at', fields.Datetime.now())

        result = super().write(vals)

        if old_states:
            for record in self:
                previous_state = old_states.get(record.id)
                if previous_state and previous_state != record.state:
                    record.message_post(
                        body=_('Status verifikasi berubah dari %s menjadi %s.') % (
                            dict(record._fields['state'].selection).get(previous_state, previous_state),
                            dict(record._fields['state'].selection).get(record.state, record.state),
                        )
                    )
        return result

    def _user_for_partner(self):
        self.ensure_one()
        return self.env['res.users'].sudo().search([
            ('partner_id', '=', self.partner_id.id),
        ], limit=1)

    def _send_verification_template(self, xmlid):
        self.ensure_one()
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if template:
            template.sudo().send_mail(self.id, force_send=True)

    def _prepare_seller_vals(self, user):
        self.ensure_one()
        return {
            'user_id': user.id,
            'university_id': self.university_id.id,
            'university_other': self.university_other or '',
            'nim': self.nim_extracted,
            'ktm_image': self.ktm_image,
            'ktm_filename': self.ktm_filename,
            'ocr_result': self.ocr_raw_text,
            'ocr_confidence': (self.name_confidence or 0.0) * 100,
            'ocr_nim_match': bool(self.nim_extracted),
            'ocr_name_match': bool(self.name_match_token),
            'ocr_student_name': self.student_name or '',
            'ocr_name_match_token': self.name_match_token or '',
            'status': 'verified',
            'verified_date': fields.Datetime.now(),
            'verified_by': self.env.uid,
        }

    def _approve_to_seller(self):
        self.ensure_one()
        user = self._user_for_partner()
        if not user:
            raise ValidationError(_('User untuk partner ini tidak ditemukan.'))
        if not self.nim_extracted:
            raise ValidationError(_('NIM belum terdeteksi.'))

        duplicate = self.env['unitrade.seller'].sudo().search([
            ('nim', '=', self.nim_extracted),
            ('status', '=', 'verified'),
            ('user_id', '!=', user.id),
        ], limit=1)
        if duplicate:
            self.write({
                'duplicate_seller_id': duplicate.id,
                'duplicate_warning': True,
                'rejection_reason': _('NIM sudah digunakan oleh akun penjual lain.'),
            })
            raise ValidationError(_('KTM/NIM ini sudah digunakan oleh akun penjual lain.'))

        seller = self.env['unitrade.seller'].sudo().search([
            ('user_id', '=', user.id),
        ], limit=1)
        seller_vals = self._prepare_seller_vals(user)
        if seller:
            seller.write(seller_vals)
        else:
            seller = self.env['unitrade.seller'].sudo().create(seller_vals)

        user.sudo().write({
            'x_is_seller': True,
            'x_seller_id': seller.id,
        })
        return seller

    def action_approve(self):
        """Admin approves the KTM verification."""
        for record in self:
            try:
                seller = record._approve_to_seller()
                record.write({
                    'state': 'approved',
                    'reviewed_by': self.env.uid,
                    'reviewed_date': fields.Datetime.now(),
                })
                template = self.env.ref(
                    'unitrade_seller.mail_template_seller_verified',
                    raise_if_not_found=False,
                )
                if template:
                    template.sudo().send_mail(seller.id, force_send=True)
                _logger.info(
                    'Verification %s approved for partner %s by %s',
                    record.id, record.partner_id.name, self.env.user.name,
                )
            except Exception as e:
                _logger.exception('Failed to approve verification %s: %s', record.id, e)
                raise

    def action_reject(self):
        """Admin rejects the KTM verification."""
        for record in self:
            try:
                reason = record.rejection_reason or _('Verifikasi ditolak oleh admin.')
                record.write({
                    'state': 'rejected',
                    'rejection_reason': reason,
                    'reviewed_by': self.env.uid,
                    'reviewed_date': fields.Datetime.now(),
                })
                user = record._user_for_partner()
                if user:
                    user.sudo().write({'x_is_seller': False})
                record._send_verification_template('unitrade_seller.mail_template_seller_verification_rejected')
                _logger.info(
                    'Verification %s rejected for partner %s by %s',
                    record.id, record.partner_id.name, self.env.user.name,
                )
            except Exception as e:
                _logger.exception('Failed to reject verification %s: %s', record.id, e)
                raise
