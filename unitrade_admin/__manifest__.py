{
    'name': 'UniTrade Admin Dashboard',
    'version': '17.0.3.1.0',
    'summary': 'Admin orchestration: dashboard, task queue, audit log, settings, reports',
    'description': """
        UniTrade Admin Dashboard - layer orkestrasi admin marketplace.

        Module ini TIDAK menduplikasi business logic. Refund/dispute, escrow
        ledger, payout, dan listing fee tetap di modul masing-masing
        (unitrade_dispute, unitrade_payment, unitrade_seller). Module ini
        hanya:

        - Dashboard ringkasan + task queue lintas modul
        - User & seller management (extend res.users, view list user)
        - Transaction monitoring (filter sale.order + flag bermasalah)
        - System settings UI (ir.config_parameter)
        - Audit log lintas modul (unitrade.admin.audit.log)
        - Reports & CSV export
        - Admin notification dropdown (live derived)
        - Voucher checkout management
    """,
    'author': 'Tim 1 - UNISA Yogyakarta',
    'website': 'https://unitrade.dev',
    'category': 'Website',
    'depends': [
        'base',
        'web',
        'website',
        'mail',
        'sale',
        'unitrade_theme',
        'unitrade_seller',
        'unitrade_payment',
        'unitrade_dispute',
        'unitrade_notification',
        'unitrade_review',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/admin_dashboard_views.xml',
        'views/admin_dashboard_templates.xml',
        'views/backend_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'unitrade_admin/static/src/scss/dashboard.scss',
            'unitrade_admin/static/src/js/dashboard.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
