<<<<<<< HEAD
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
=======
import math


MIDTRANS_PAYMENT_METHODS = {
    'bca_va': {
        'label': 'BCA Virtual Account',
        'group': 'Transfer Virtual Account',
        'type': 'BANK_TRANSFER',
        'payment_type': 'bank_transfer',
        'bank': 'bca',
        'channel_code': 'BCA_VA',
        'logo': '/unitrade_theme/static/src/img/payment/bca.svg',
        'fee_fixed': 4000,
        'fee_percent': 0.0,
        'enabled_default': True,
        'sequence': 10,
        'reference_label': 'Nomor Virtual Account',
        'badge': 'BCA',
    },
    'mandiri_bill': {
        'label': 'Mandiri Bill Payment',
        'group': 'Transfer Virtual Account',
        'type': 'ECHANNEL',
        'payment_type': 'echannel',
        'bank': 'mandiri',
        'channel_code': 'MANDIRI_BILL',
        'logo': '/unitrade_theme/static/src/img/payment/mandiri.svg',
        'fee_fixed': 4000,
        'fee_percent': 0.0,
        'enabled_default': True,
        'sequence': 20,
        'reference_label': 'Biller Code / Bill Key',
        'badge': 'MANDIRI',
    },
    'bni_va': {
        'label': 'BNI Virtual Account',
        'group': 'Transfer Virtual Account',
        'type': 'BANK_TRANSFER',
        'payment_type': 'bank_transfer',
        'bank': 'bni',
        'channel_code': 'BNI_VA',
        'logo': '/unitrade_theme/static/src/img/payment/bni.svg',
        'fee_fixed': 4000,
        'fee_percent': 0.0,
        'enabled_default': True,
        'sequence': 30,
        'reference_label': 'Nomor Virtual Account',
        'badge': 'BNI',
    },
    'bri_va': {
        'label': 'BRI Virtual Account',
        'group': 'Transfer Virtual Account',
        'type': 'BANK_TRANSFER',
        'payment_type': 'bank_transfer',
        'bank': 'bri',
        'channel_code': 'BRI_VA',
        'logo': '/unitrade_theme/static/src/img/payment/bri.svg',
        'fee_fixed': 4000,
        'fee_percent': 0.0,
        'enabled_default': True,
        'sequence': 40,
        'reference_label': 'Nomor Virtual Account',
        'badge': 'BRI',
    },
    'permata_va': {
        'label': 'Permata Virtual Account',
        'group': 'Transfer Virtual Account',
        'type': 'PERMATA',
        'payment_type': 'permata',
        'bank': 'permata',
        'channel_code': 'PERMATA_VA',
        'logo': '/unitrade_theme/static/src/img/payment/permata.svg',
        'fee_fixed': 4000,
        'fee_percent': 0.0,
        'enabled_default': True,
        'sequence': 50,
        'reference_label': 'Nomor Virtual Account',
        'badge': 'PERMATA',
    },
    'cimb_va': {
        'label': 'CIMB Virtual Account',
        'group': 'Transfer Virtual Account',
        'type': 'BANK_TRANSFER',
        'payment_type': 'bank_transfer',
        'bank': 'cimb',
        'channel_code': 'CIMB_VA',
        'logo': '/unitrade_theme/static/src/img/payment/cimb.svg',
        'fee_fixed': 4000,
        'fee_percent': 0.0,
        'enabled_default': False,
        'sequence': 60,
        'reference_label': 'Nomor Virtual Account',
        'badge': 'CIMB',
        'disabled_reason': 'Aktifkan CIMB VA di Midtrans Dashboard sebelum dipakai.',
    },
    'qris': {
        'label': 'QRIS',
        'group': 'E-Wallet & QRIS',
        'type': 'QRIS',
        'payment_type': 'qris',
        'channel_code': 'QRIS',
        'logo': '/unitrade_theme/static/src/img/payment/qris.svg',
        'fee_fixed': 0,
        'fee_percent': 0.007,
        'enabled_default': True,
        'sequence': 70,
        'reference_label': 'Order ID Midtrans',
        'badge': 'QRIS',
    },
    'gopay': {
        'label': 'GoPay',
        'group': 'E-Wallet & QRIS',
        'type': 'GOPAY',
        'payment_type': 'gopay',
        'channel_code': 'GOPAY',
        'logo': '/unitrade_theme/static/src/img/payment/gopay.svg',
        'fee_fixed': 0,
        'fee_percent': 0.02,
        'enabled_default': True,
        'sequence': 80,
        'reference_label': 'Order ID Midtrans',
        'badge': 'GOPAY',
    },
    'shopeepay': {
        'label': 'ShopeePay',
        'group': 'E-Wallet & QRIS',
        'type': 'SHOPEEPAY',
        'payment_type': 'shopeepay',
        'channel_code': 'SHOPEEPAY',
        'logo': '/unitrade_theme/static/src/img/payment/shopeepay.svg',
        'fee_fixed': 0,
        'fee_percent': 0.02,
        'enabled_default': False,
        'sequence': 90,
        'reference_label': 'Order ID Midtrans',
        'badge': 'SHOPEEPAY',
        'disabled_reason': 'Aktifkan ShopeePay di Midtrans Dashboard sebelum dipakai.',
    },
    'indomaret': {
        'label': 'Indomaret',
        'group': 'Convenience Store',
        'type': 'CSTORE',
        'payment_type': 'cstore',
        'store': 'indomaret',
        'channel_code': 'INDOMARET',
        'logo': '/unitrade_theme/static/src/img/payment/indomaret.svg',
        'fee_fixed': 5000,
        'fee_percent': 0.0,
        'enabled_default': False,
        'sequence': 100,
        'reference_label': 'Kode Pembayaran',
        'badge': 'INDOMARET',
        'disabled_reason': 'Aktifkan Indomaret di Midtrans Dashboard sebelum dipakai.',
    },
    'alfamart': {
        'label': 'Alfamart / Alfamidi / Dan+Dan',
        'group': 'Convenience Store',
        'type': 'CSTORE',
        'payment_type': 'cstore',
        'store': 'alfamart',
        'channel_code': 'ALFAMART',
        'logo': '/unitrade_theme/static/src/img/payment/alfamart.svg',
        'fee_fixed': 5000,
        'fee_percent': 0.0,
        'enabled_default': False,
        'sequence': 110,
        'reference_label': 'Kode Pembayaran',
        'badge': 'ALFAMART',
        'disabled_reason': 'Aktifkan Alfamart di Midtrans Dashboard sebelum dipakai.',
    },
    'card': {
        'label': 'Visa / Mastercard / JCB',
        'group': 'Kartu Kredit/Debit',
        'type': 'CARD',
        'payment_type': 'credit_card',
        'channel_code': 'CARD',
        'logo': '/unitrade_theme/static/src/img/payment/visa-mastercard-jcb.svg',
        'fee_fixed': 2000,
        'fee_percent': 0.029,
        'enabled_default': False,
        'sequence': 120,
        'reference_label': 'Order ID Midtrans',
        'badge': 'CARD',
        'disabled_reason': 'Kartu membutuhkan tokenisasi client-side agar tetap PCI-safe.',
    },
}


def midtrans_method_enabled(config, key, method):
    raw = config.get_param(
        'unitrade.midtrans.method.%s.enabled' % key,
        default='True' if method.get('enabled_default') else 'False',
    )
    return str(raw or '').lower() in ('true', '1', 'yes', 'y')


def midtrans_method_fee(config, key, method, base_amount):
    fixed = _config_float(
        config,
        'unitrade.midtrans.method.%s.fee_fixed' % key,
        method.get('fee_fixed', 0.0),
    )
    percent = _config_float(
        config,
        'unitrade.midtrans.method.%s.fee_percent' % key,
        method.get('fee_percent', 0.0),
    )
    amount = max(float(base_amount or 0.0), 0.0)
    if amount <= 0:
        return 0
    if percent >= 1:
        return int(math.ceil(fixed))
    gross_amount = math.ceil((amount + fixed) / (1 - percent))
    return int(max(gross_amount - amount, 0))


def _config_float(config, key, default=0.0):
    raw = config.get_param(key, default=str(default))
    try:
        return float(raw or 0.0)
    except (TypeError, ValueError):
        return float(default or 0.0)
>>>>>>> origin/main
