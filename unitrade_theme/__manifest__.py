{
    'name': 'UniTrade Theme',
    'version': '17.0.1.0.0',
    'summary': 'UniTrade Marketplace Theme with Tailwind CSS',
    'description': """
        Custom theme for UniTrade C2C Marketplace.
        - Tailwind CSS with tw- prefix
        - Custom QWeb templates
        - Storefront homepage
        - Responsive layout
    """,
    'author': 'Tim 1 - UNISA Yogyakarta',
    'website': 'https://unitrade.dev',
    'category': 'Website/Theme',
    'depends': ['website', 'website_sale', 'portal', 'auth_signup', 'auth_oauth'],
    'data': [
        'security/ir.model.access.csv',
        'data/oauth_provider.xml',
        'views/templates.xml',
        'views/product_card_templates.xml',
        'views/homepage.xml',
        'views/shop_templates.xml',
        'views/product_templates.xml',
        'views/snippets.xml',
        'views/login_templates.xml',
        'views/otp_templates.xml',
        'views/profile_templates.xml',
        'views/seller_verification.xml',
        'views/cart_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'unitrade_theme/static/src/css/output.css',
            'unitrade_theme/static/src/xml/shop_filter.xml',
            'unitrade_theme/static/src/xml/product_detail.xml',
            'unitrade_theme/static/src/xml/orders.xml',
            'unitrade_theme/static/src/js/main.js',
            'unitrade_theme/static/src/js/shop_filter.js',
            'unitrade_theme/static/src/js/product_detail_owl.js',
            'unitrade_theme/static/src/js/product_detail.js',
            'unitrade_theme/static/src/js/profile.js',
            'unitrade_theme/static/src/js/orders.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
