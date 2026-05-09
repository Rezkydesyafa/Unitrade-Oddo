import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_unitrade_address_label = fields.Selection([
        ('home', 'Rumah'),
        ('office', 'Kantor'),
        ('school', 'Sekolah'),
        ('other', 'Lainnya'),
    ], string='Label Alamat UniTrade', default='home')
    x_unitrade_province = fields.Char(string='Provinsi UniTrade')
    x_unitrade_city = fields.Char(string='Kota/Kabupaten UniTrade')
    x_unitrade_district = fields.Char(string='Kecamatan UniTrade')
    x_unitrade_village = fields.Char(string='Kelurahan UniTrade')
    x_unitrade_latitude = fields.Float(string='Latitude UniTrade', digits=(10, 7))
    x_unitrade_longitude = fields.Float(string='Longitude UniTrade', digits=(10, 7))
    x_unitrade_mapbox_place_id = fields.Char(string='Mapbox Place ID')
