import math


XENDIT_PAYMENT_METHODS = {
    'bca_va': {
        'label': 'BCA Virtual Account',
        'group': 'Transfer Virtual Account',
        'type': 'VIRTUAL_ACCOUNT',
        'channel_code': 'BCA_VIRTUAL_ACCOUNT',
        'logo': '/unitrade_theme/static/src/img/payment/bca.svg',
        'fee_type': 'fixed',
        'fee_fixed': 4000,
        'fee_percent': 0.0,
        'enabled_default': True,
        'sequence': 10,
        'reference_label': 'Nomor Virtual Account',
        'badge': 'BCA',
    },
    'mandiri_va': {
        'label': 'Mandiri Virtual Account',
        'group': 'Transfer Virtual Account',
        'type': 'VIRTUAL_ACCOUNT',
        'channel_code': 'MANDIRI_VIRTUAL_ACCOUNT',
        'logo': '/unitrade_theme/static/src/img/payment/mandiri.svg',
        'fee_type': 'fixed',
        'fee_fixed': 4000,
        'fee_percent': 0.0,
        'enabled_default': True,
        'sequence': 20,
        'reference_label': 'Nomor Virtual Account',
        'badge': 'MANDIRI',
    },
    'bni_va': {
        'label': 'BNI Virtual Account',
        'group': 'Transfer Virtual Account',
        'type': 'VIRTUAL_ACCOUNT',
        'channel_code': 'BNI_VIRTUAL_ACCOUNT',
        'logo': '/unitrade_theme/static/src/img/payment/bni.svg',
        'fee_type': 'fixed',
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
        'type': 'VIRTUAL_ACCOUNT',
        'channel_code': 'BRI_VIRTUAL_ACCOUNT',
        'logo': '/unitrade_theme/static/src/img/payment/bri.svg',
        'fee_type': 'fixed',
        'fee_fixed': 4000,
        'fee_percent': 0.0,
        'enabled_default': True,
        'sequence': 40,
        'reference_label': 'Nomor Virtual Account',
        'badge': 'BRI',
    },
    'qris': {
        'label': 'QRIS',
        'group': 'E-Wallet & QRIS',
        'type': 'QR_CODE',
        'channel_code': 'QRIS',
        'logo': '/unitrade_theme/static/src/img/payment/qris.svg',
        'fee_type': 'percent',
        'fee_fixed': 0,
        'fee_percent': 0.0063,
        'enabled_default': True,
        'sequence': 50,
        'reference_label': 'Invoice Xendit',
        'badge': 'QRIS',
    },
    'ovo': {
        'label': 'OVO',
        'group': 'E-Wallet & QRIS',
        'type': 'EWALLET',
        'channel_code': 'OVO',
        'logo': '/unitrade_theme/static/src/img/payment/ovo.svg',
        'fee_type': 'percent',
        'fee_fixed': 0,
        'fee_percent': 0.015,
        'enabled_default': False,
        'sequence': 60,
        'reference_label': 'Invoice Xendit',
        'badge': 'OVO',
    },
    'dana': {
        'label': 'DANA',
        'group': 'E-Wallet & QRIS',
        'type': 'EWALLET',
        'channel_code': 'DANA',
        'logo': '/unitrade_theme/static/src/img/payment/dana.svg',
        'fee_type': 'percent',
        'fee_fixed': 0,
        'fee_percent': 0.015,
        'enabled_default': False,
        'sequence': 70,
        'reference_label': 'Invoice Xendit',
        'badge': 'DANA',
    },
    'card': {
        'label': 'Visa / Mastercard / JCB',
        'group': 'Kartu Kredit/Debit',
        'type': 'CARD',
        'channel_code': 'CARDS',
        'logo': '',
        'fee_type': 'percent_plus_fixed',
        'fee_fixed': 2000,
        'fee_percent': 0.029,
        'enabled_default': False,
        'sequence': 80,
        'reference_label': 'Invoice Xendit',
        'badge': 'CARD',
        'disabled_reason': 'Kartu membutuhkan Xendit component/PCI-safe flow.',
    },
}


def xendit_method_enabled(config, key, method):
    raw = config.get_param(
        'unitrade.xendit.method.%s.enabled' % key,
        default='True' if method.get('enabled_default') else 'False',
    )
    return str(raw or '').lower() in ('true', '1', 'yes', 'y')


def xendit_method_fee(config, key, method, base_amount):
    fixed = _config_float(
        config,
        'unitrade.xendit.method.%s.fee_fixed' % key,
        method.get('fee_fixed', 0.0),
    )
    percent = _config_float(
        config,
        'unitrade.xendit.method.%s.fee_percent' % key,
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
