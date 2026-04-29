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
    confidence_flag = fields.Selection([
        ('low', 'Low Confidence'),
        ('high', 'High Confidence'),
    ], string='Confidence Flag',
        readonly=True,
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Menunggu Review'),
        ('approved', 'Disetujui'),
        ('rejected', 'Ditolak'),
    ], string='Status',
        default='draft',
        tracking=True,
        index=True,
    )

    def action_approve(self):
        """Admin approves the KTM verification."""
        for record in self:
            try:
                record.write({'state': 'approved'})
                # Set x_is_seller = True on the related user
                user = self.env['res.users'].sudo().search([
                    ('partner_id', '=', record.partner_id.id),
                ], limit=1)
                if user:
                    user.sudo().write({'x_is_seller': True})
                    _logger.info(
                        'Verification %s approved for partner %s — user %s marked as seller',
                        record.id, record.partner_id.name, user.name,
                    )
                else:
                    _logger.warning('No user found for partner %s', record.partner_id.id)
            except Exception as e:
                _logger.exception('Failed to approve verification %s: %s', record.id, e)
                raise

    def action_reject(self):
        """Admin rejects the KTM verification."""
        for record in self:
            try:
                record.write({'state': 'rejected'})
                # Unset x_is_seller on the related user
                user = self.env['res.users'].sudo().search([
                    ('partner_id', '=', record.partner_id.id),
                ], limit=1)
                if user:
                    user.sudo().write({'x_is_seller': False})
                _logger.info(
                    'Verification %s rejected for partner %s by %s',
                    record.id, record.partner_id.name, self.env.user.name,
                )
            except Exception as e:
                _logger.exception('Failed to reject verification %s: %s', record.id, e)
                raise
