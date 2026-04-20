from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class UnitradeDeliveryController(http.Controller):

    @http.route('/unitrade/delivery/webhook', type='json', auth='none', csrf=False, methods=['POST'])
    def delivery_webhook(self, **kwargs):
        """Handle GoSend delivery status webhook"""
        data = request.jsonrequest
        _logger.info('GoSend webhook received: %s', data)

        gosend_order_id = data.get('order_id')
        status = data.get('status')

        delivery = request.env['unitrade.delivery'].sudo().search([
            ('gosend_order_id', '=', gosend_order_id)
        ], limit=1)

        if not delivery:
            return {'status': 'error', 'message': 'Delivery not found'}

        status_map = {
            'PICKING_UP': 'picked_up',
            'IN_TRANSIT': 'in_transit',
            'DELIVERED': 'delivered',
            'FAILED': 'failed',
        }

        new_status = status_map.get(status)
        if new_status:
            delivery.write({
                'status': new_status,
                'driver_name': data.get('driver', {}).get('name', ''),
                'driver_phone': data.get('driver', {}).get('phone', ''),
            })

        return {'status': 'ok'}
