{
    'name': 'UniTrade Seller',
    'version': '17.0.1.0.0',
    'summary': 'Seller verification with KTM OCR and OTP system',
    'description': """
        UniTrade Seller Module:
        - Seller registration and KTM verification
        - PaddleOCR integration for automatic KTM text extraction
        - OTP email verification for user accounts
        - Seller status workflow: draft → pending → verified / rejected
        - Admin verification dashboard
    """,
    'author': 'Tim 1 - UNISA Yogyakarta',
    'website': 'https://unitrade.dev',
    'category': 'Website',
    'depends': ['base', 'website', 'sale', 'mail', 'unitrade_theme'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/listing_fee_config.xml',
        'data/mail_template.xml',
        'data/demo_students.xml',
        'views/seller_views.xml',
        'views/seller_onboarding_templates.xml',
        'views/seller_templates.xml',
        'views/seller_menus.xml',
        'views/seller_verification_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'unitrade_seller/static/src/css/seller_dashboard.css',
            'unitrade_seller/static/src/xml/seller_sidebar_owl.xml',
            'unitrade_seller/static/src/xml/seller_dashboard_owl.xml',
            'unitrade_seller/static/src/xml/seller_orders_owl.xml',
            'unitrade_seller/static/src/xml/seller_products_owl.xml',
            'unitrade_seller/static/src/xml/seller_product_create_owl.xml',
            'unitrade_seller/static/src/xml/seller_settings_owl.xml',
            'unitrade_seller/static/src/xml/seller_profile_owl.xml',
            'unitrade_seller/static/src/js/seller_sidebar.js',
            'unitrade_seller/static/src/js/seller_dashboard.js',
            'unitrade_seller/static/src/js/seller_orders.js',
            'unitrade_seller/static/src/js/seller_products.js',
            'unitrade_seller/static/src/js/seller_product_create.js',
            'unitrade_seller/static/src/js/seller_settings.js',
            'unitrade_seller/static/src/js/seller_profile_owl.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
