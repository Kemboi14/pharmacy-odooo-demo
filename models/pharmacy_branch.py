# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PharmacyBranch(models.Model):
    _name = 'pharmacy.branch'
    _description = 'Pharmacy Branch'
    _order = 'code'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Branch Name', required=True, tracking=True)
    code = fields.Char('Branch Code', required=True, tracking=True, copy=False)
    display_name = fields.Char(compute='_compute_display_name', store=True)
    
    # Address fields
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one('res.country.state', 'State')
    zip = fields.Char('Zip')
    country_id = fields.Many2one('res.country', 'Country')
    
    # Contact information
    phone = fields.Char('Phone')
    email = fields.Char('Email')
    website = fields.Char('Website')
    
    # Financial configuration
    currency_id = fields.Many2one('res.currency', 'Currency', required=True,
                                  default=lambda self: self.env.company.currency_id)
    default_pricelist_id = fields.Many2one('product.pricelist', 'Default Pricelist')
    
    # Kenyan tax configuration
    tax_calculation_rounding_method = fields.Selection([
        ('round_globally', 'Round per invoice'),
        ('round_per_line', 'Round per line'),
    ], default='round_globally', string='Tax Rounding Method')
    
    default_customer_tax_id = fields.Many2one('account.tax', string='Default Customer Tax')
    default_supplier_tax_id = fields.Many2one('account.tax', string='Default Supplier Tax')
    default_fiscal_position_id = fields.Many2one('account.fiscal.position', string='Default Fiscal Position')
    
    # Payment terms for different customer types
    cash_payment_term_id = fields.Many2one('account.payment.term', string='Cash Payment Terms')
    insurance_payment_term_id = fields.Many2one('account.payment.term', string='Insurance Payment Terms')
    supplier_payment_term_id = fields.Many2one('account.payment.term', string='Supplier Payment Terms')
    
    # Related records
    location_ids = fields.One2many('stock.location', 'branch_id', 'Stock Locations')
    pos_config_ids = fields.One2many('pos.config', 'branch_id', 'POS Configurations')
    journal_ids = fields.One2many('account.journal', 'branch_id', 'Journals')
    
    # Management
    manager_id = fields.Many2one('res.users', 'Branch Manager', tracking=True)
    user_ids = fields.Many2many('res.users', 'pharmacy_branch_user_rel',
                                'branch_id', 'user_id', 'Assigned Users',
                                help='Users assigned to this branch')
    company_id = fields.Many2one('res.company', 'Company', required=True,
                                default=lambda self: self.env.company)
    active = fields.Boolean('Active', default=True, tracking=True)
    
    # Statistics
    total_sales = fields.Float(compute='_compute_statistics', store=True)
    total_claims = fields.Float(compute='_compute_statistics', store=True)
    stock_value = fields.Float(compute='_compute_statistics', store=True)
    
    @api.depends('name', 'code')
    def _compute_display_name(self):
        for branch in self:
            branch.display_name = f"[{branch.code}] {branch.name}"
    
    @api.depends('pos_config_ids', 'location_ids')
    def _compute_statistics(self):
        for branch in self:
            # Total sales from POS orders
            sales = self.env['pos.order'].search([
                ('branch_id', '=', branch.id),
                ('state', 'in', ['paid', 'done', 'invoiced'])
            ])
            branch.total_sales = sum(sales.mapped('amount_total'))
            
            # Total claims amount
            claims = self.env['pharmacy.claim'].search([
                ('branch_id', '=', branch.id),
                ('status', 'in', ['approved', 'partially_approved', 'paid'])
            ])
            branch.total_claims = sum(claims.mapped('approved_amount'))
            
            # Stock value calculation
            branch.stock_value = 0.0
            for location in branch.location_ids:
                quants = self.env['stock.quant'].search([
                    ('location_id', '=', location.id),
                    ('quantity', '>', 0)
                ])
                for quant in quants:
                    branch.stock_value += quant.quantity * quant.product_id.standard_price
    
    @api.constrains('code')
    def _check_code_unique(self):
        for branch in self:
            if self.search_count([('code', '=', branch.code), ('id', '!=', branch.id)]):
                raise ValidationError(_('Branch code must be unique!'))
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Auto-generate branch code if not provided
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('pharmacy.branch') or 'BR001'
        
        records = super().create(vals_list)
        for record in records:
            record._create_default_locations()
            record._create_default_journals()
        return records
    
    def _create_default_locations(self):
        """Create default stock locations for the branch"""
        location_data = [
            {'name': f'{self.name} - Shop Floor', 'usage': 'internal', 'barcode': f'SHOP-{self.code}'},
            {'name': f'{self.name} - Store', 'usage': 'internal', 'barcode': f'STORE-{self.code}'},
            {'name': f'{self.name} - Returns/Quarantine', 'usage': 'internal', 'barcode': f'RETURNS-{self.code}'},
            {'name': f'{self.name} - Transit', 'usage': 'transit', 'barcode': f'TRANSIT-{self.code}'},
        ]
        
        for data in location_data:
            existing = self.env['stock.location'].search([
                ('branch_id', '=', self.id),
                ('company_id', '=', self.company_id.id),
                ('barcode', '=', data['barcode']),
            ], limit=1)
            if existing:
                continue
            self.env['stock.location'].create({
                'branch_id': self.id,
                'company_id': self.company_id.id,
                **data
            })
    
    def _create_default_journals(self):
        """Create default journals for the branch"""
        # Odoo enforces unique (company_id, code) for journals and the code has
        # a short length limit. Generate stable, short codes from branch code.
        branch_code = (self.code or '').replace(' ', '').upper()
        suffix = branch_code[-3:] if branch_code else str(self.id)
        journal_data = [
            {'name': f'{self.name} - Cash', 'type': 'cash', 'code': f'CS{suffix}'},
            {'name': f'{self.name} - Bank', 'type': 'bank', 'code': f'BK{suffix}'},
            {'name': f'{self.name} - M-Pesa', 'type': 'bank', 'code': f'MP{suffix}'},
            {'name': f'{self.name} - Insurance', 'type': 'sale', 'code': f'IN{suffix}'},
        ]
        
        for data in journal_data:
            existing = self.env['account.journal'].search([
                ('company_id', '=', self.company_id.id),
                ('code', '=', data['code']),
            ], limit=1)
            if existing:
                continue
            self.env['account.journal'].create({
                'branch_id': self.id,
                'company_id': self.company_id.id,
                'currency_id': self.currency_id.id,
                **data
            })
    
    def action_view_sales(self):
        """View sales for this branch"""
        return {
            'name': _('Sales'),
            'type': 'ir.actions.act_window',
            'res_model': 'pos.order',
            'view_mode': 'list,form',
            'domain': [('branch_id', '=', self.id)],
            'context': {'default_branch_id': self.id},
        }
    
    def action_view_claims(self):
        """View claims for this branch"""
        return {
            'name': _('Insurance Claims'),
            'type': 'ir.actions.act_window',
            'res_model': 'pharmacy.claim',
            'view_mode': 'list,form',
            'domain': [('branch_id', '=', self.id)],
            'context': {'default_branch_id': self.id},
        }
    
    def action_view_stock(self):
        """View stock for this branch"""
        return {
            'name': _('Stock'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.quant',
            'view_mode': 'list,form',
            'domain': [('location_id', 'in', self.location_ids.ids)],
            'context': {'search_default_location_group': 1},
        }
    
    def get_shop_floor_location(self):
        """Get the shop floor location for POS operations"""
        return self.env['stock.location'].search([
            ('branch_id', '=', self.id),
            ('name', 'ilike', 'Shop Floor')
        ], limit=1)
    
    def get_store_location(self):
        """Get the store location"""
        return self.env['stock.location'].search([
            ('branch_id', '=', self.id),
            ('name', 'ilike', 'Store')
        ], limit=1)
    
    def get_quarantine_location(self):
        """Get the quarantine location"""
        return self.env['stock.location'].search([
            ('branch_id', '=', self.id),
            ('name', 'ilike', 'Returns/Quarantine')
        ], limit=1)
    
    def get_transit_location(self):
        """Get the transit location"""
        return self.env['stock.location'].search([
            ('branch_id', '=', self.id),
            ('name', 'ilike', 'Transit')
        ], limit=1)
