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

    def _load_records_create(self, vals_list):
        """Attach seed XML IDs to existing universities during module updates."""
        records = self.browse()
        for vals in vals_list:
            existing = self.search([('name', '=', vals.get('name'))], limit=1) if vals.get('name') else self.browse()
            if existing:
                update_vals = {key: value for key, value in vals.items() if key != 'name'}
                if update_vals:
                    existing.write(update_vals)
                records += existing
            else:
                records += super(UnitradeUniversity, self)._load_records_create([vals])
        return records
