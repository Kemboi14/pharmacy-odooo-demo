# -*- coding: utf-8 -*-
{
    "name": "Pharmacy Management System",
    "version": "18.0.1.0.0",
    "category": "Pharmacy",
    "summary": "Comprehensive Pharmacy Management with Multi-branch, Insurance, and POS",
    "description": """
Pharmacy Management System for Odoo 18
=====================================

A comprehensive, production-ready Pharmacy Management System that handles:
- Multi-branch operations with data isolation
- Insurance claims and reconciliation
- Batch/expiry tracking with FEFO logic
- Full POS integration for Kenyan market
- Prescription management
- Controlled substances tracking
- M-Pesa integration
- eTIMS compliance

Key Features:
------------
* Multi-branch architecture with enforced data ownership
* Complete insurance workflow from coverage rules to claims payment
* Mandatory batch/expiry tracking with FEFO implementation
* Enhanced POS with prescription and controlled substance workflows
* Comprehensive reporting and dashboards
* Full accounting integration
* Security and access control by role
    """,
    "author": "Pharmacy Solutions",
    "website": "https://github.com/pharmacy-solutions",
    "license": "LGPL-3",
    "assets": {
        "web._assets_core": [
            "Pharmacy/static/src/js/pharmacy_main.js",
            "Pharmacy/static/src/js/pharmacy_pos.js",
        ],
        "point_of_sale._assets_pos": [
            "Pharmacy/static/src/css/pharmacy_pos.css",
        ],
    },
    "depends": [
        "base",
        "mail",
        "contacts",
        "product",
        "stock",
        "point_of_sale",
        "account",
        "web",
        "l10n_ke",
    ],
    "data": [
        # Security
        "security/pharmacy_security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/pharmacy_accounts.xml",
        "data/pharmacy_journal.xml",
        "data/pharmacy_tax_data.xml",
        "data/pharmacy_payment_methods.xml",
        "data/pharmacy_company_config.xml",
        "data/pharmacy_data.xml",
        "data/pharmacy_sequence.xml",
        "data/pharmacy_scheduled_actions.xml",
        # Views
        "views/pharmacy_branch_views.xml",
        "views/pharmacy_patient_views.xml",
        "views/pharmacy_coverage_rule_views.xml",
        "views/pharmacy_controlled_substance_actions.xml",
        "views/pharmacy_controlled_substance_register_views.xml",
        "views/pharmacy_dosage_form_views.xml",
        "views/pharmacy_discount_rule_views.xml",
        "views/pharmacy_insurer_views.xml",
        "views/pharmacy_accounting_views.xml",
        "views/pharmacy_pricing_views.xml",
        "views/pharmacy_stock_lot_views.xml",
        "views/pos_order_pharmacy_views.xml",
        "views/pharmacy_menu.xml",
        "views/pharmacy_financial_reports_views.xml",
        "views/pharmacy_assets.xml",
        "views/pharmacy_company_views.xml",
        # Reports
        "reports/pharmacy_report_views.xml",
        # POS
        # Wizards
        "wizards/pharmacy_wizard_views.xml",
        # Configuration
        # 'data/pharmacy_config_data.xml',
    ],
    'demo': [
        'demo/pharmacy_demo.xml',
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
    "sequence": 100,
    # 'images': [                              # Commented out - directory doesn't exist
    #     'static/description/banner.png',
    #     'static/description/main.png',
    # ],
    "price": 0.00,
    "currency": "KES",
    "live_test_url": "https://pharmacy-demo.odoo.com",
    "post_init_hook": "post_init_hook",
    # 'uninstall_hook': 'uninstall_hook',      # Commented out - function doesn't exist
}
