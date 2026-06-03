MIDTRANS_PAYMENT_METHODS = {
    'bca_va': {'label': 'BCA Virtual Account', 'type': 'VA', 'payment_type': 'bank_transfer', 'bank': 'bca'},
    'bni_va': {'label': 'BNI Virtual Account', 'type': 'VA', 'payment_type': 'bank_transfer', 'bank': 'bni'},
    'bri_va': {'label': 'BRI Virtual Account', 'type': 'VA', 'payment_type': 'bank_transfer', 'bank': 'bri'},
    'permata_va': {'label': 'Permata Virtual Account', 'type': 'VA', 'payment_type': 'bank_transfer', 'bank': 'permata'},
    'mandiri_bill': {'label': 'Mandiri Bill Payment', 'type': 'VA', 'payment_type': 'echannel'},
    'qris': {'label': 'QRIS', 'type': 'QRIS', 'payment_type': 'qris'},
    'gopay': {'label': 'GoPay', 'type': 'EWALLET', 'payment_type': 'gopay'},
    'shopeepay': {'label': 'ShopeePay', 'type': 'EWALLET', 'payment_type': 'shopeepay'},
    'indomaret': {'label': 'Indomaret', 'type': 'CSTORE', 'payment_type': 'cstore', 'store': 'indomaret'},
    'alfamart': {'label': 'Alfamart', 'type': 'CSTORE', 'payment_type': 'cstore', 'store': 'alfamart'},
}


def midtrans_method_enabled(config, method_key, method):
    param_name = 'unitrade.midtrans.method.%s.enabled' % method_key
    raw = config.get_param(param_name, default='1')
    return str(raw).lower() not in ('0', 'false', 'no', 'off')
