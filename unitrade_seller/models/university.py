# -*- coding: utf-8 -*-
from odoo import fields, models


class UnitradeUniversity(models.Model):
    _name = 'unitrade.university'
    _description = 'UniTrade University'
    _order = 'sequence, name'

    name = fields.Char(string='Nama Universitas', required=True, index=True)
    status = fields.Char(string='Status')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Nama universitas harus unik!'),
    ]
