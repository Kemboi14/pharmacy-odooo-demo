# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Pharmacy-specific fields
    generic_name = fields.Char("Generic Name", tracking=True)
    strength = fields.Char("Strength", help="e.g., 500mg", tracking=True)
    dosage_form_id = fields.Many2one(
        "pharmacy.dosage.form", "Dosage Form", tracking=True
    )
    dosage_form = fields.Selection(
        [
            ("tablet", "Tablet"),
            ("capsule", "Capsule"),
            ("syrup", "Syrup"),
            ("injection", "Injection"),
            ("cream", "Cream"),
            ("ointment", "Ointment"),
            ("drops", "Drops"),
            ("inhaler", "Inhaler"),
            ("suppository", "Suppository"),
            ("patch", "Patch"),
            ("other", "Other"),
        ],
        string="Dosage Form Category",
        compute="_compute_dosage_form",
        store=True,
    )

    pack_size = fields.Integer(
        "Pack Size", help="Tablets per strip, strips per box, etc.", tracking=True
    )

    # Regulatory fields
    is_prescription_required = fields.Boolean(
        "Prescription Required", default=False, tracking=True
    )
    is_controlled_substance = fields.Boolean(
        "Controlled Substance", default=False, tracking=True
    )
    controlled_substance_schedule = fields.Selection(
        [
            ("1", "Schedule I"),
            ("2", "Schedule II"),
            ("3", "Schedule III"),
            ("4", "Schedule IV"),
            ("5", "Schedule V"),
            ("unscheduled", "Unscheduled"),
        ],
        "Controlled Substance Schedule",
        default="unscheduled",
        tracking=True,
    )
    requires_pharmacist_approval = fields.Boolean(
        "Requires Pharmacist Approval", default=False, tracking=True
    )
    requires_id_capture = fields.Boolean(
        "Requires ID Capture", default=False, tracking=True
    )

    # Storage and handling
    storage_conditions = fields.Text("Storage Conditions")
    interaction_warnings = fields.Text("Interaction Warnings")
    min_expiry_days = fields.Integer(
        "Minimum Expiry Days",
        default=30,
        help="Minimum days before expiry to allow sale",
    )

    # Default instructions
    dosage_instructions = fields.Text("Default Dosage Instructions")

    # Pricing and margins
    wholesale_price = fields.Float("Wholesale Price", digits="Product Price")
    min_margin_percentage = fields.Float(
        "Minimum Margin %", default=20.0, help="Minimum margin percentage for pricing"
    )

    # Regulatory codes
    drug_registration_number = fields.Char("Drug Registration Number")
    ndc_code = fields.Char("NDC Code", help="National Drug Code")
    atc_code = fields.Char(
        "ATC Code", help="Anatomical Therapeutic Chemical Classification"
    )

    # Supplier information
    preferred_supplier_ids = fields.Many2many(
        "res.partner",
        "product_preferred_supplier_rel",
        "product_id",
        "supplier_id",
        "Preferred Suppliers",
    )

    # Insurance pricing
    insurance_pricelist_ids = fields.Many2many(
        "product.pricelist",
        "product_insurance_pricelist_rel",
        "product_id",
        "pricelist_id",
        "Insurance Pricelists",
        help="Pricelists specific to insurance providers",
    )

    # Tax configuration for Kenyan pharmacy
    supplier_taxes_id = fields.Many2many(
        "account.tax",
        string="Supplier Taxes",
        domain=[("type_tax_use", "=", "purchase")],
    )
    customer_taxes_id = fields.Many2many(
        "account.tax", string="Customer Taxes", domain=[("type_tax_use", "=", "sale")]
    )

    # Computed fields
    is_pharma_product = fields.Boolean(compute="_compute_is_pharma_product", store=True)
    expiry_status = fields.Selection(
        [("expired", "Expired"), ("expiring_soon", "Expiring Soon"), ("good", "Good")],
        compute="_compute_expiry_status",
        store=True,
    )

    @api.depends("is_prescription_required", "is_controlled_substance")
    def _compute_is_pharma_product(self):
        for product in self:
            product.is_pharma_product = (
                product.is_prescription_required or product.is_controlled_substance
            )

    def _compute_expiry_status(self):
        """Compute expiry status based on available stock"""
        for product in self:
            # Get all lots for this product
            lots = self.env["stock.lot"].search(
                [("product_id.product_tmpl_id", "=", product.id)]
            )

            if not lots:
                product.expiry_status = "good"
                continue

            # Check if any lot is expired
            expired_lots = lots.filtered(lambda l: l.is_expired)
            if expired_lots:
                product.expiry_status = "expired"
                continue

            # Check if any lot is expiring soon
            expiring_lots = lots.filtered(lambda l: l.expiry_alert_30)
            if expiring_lots:
                product.expiry_status = "expiring_soon"
                continue

            product.expiry_status = "good"

    @api.constrains("min_expiry_days")
    def _check_min_expiry_days(self):
        for product in self:
            if product.min_expiry_days < 0:
                raise ValidationError(_("Minimum expiry days cannot be negative"))

    @api.constrains("pack_size")
    def _check_pack_size(self):
        for product in self:
            if product.pack_size and product.pack_size <= 0:
                raise ValidationError(_("Pack size must be greater than 0"))

    def get_available_lots(self, location_id, quantity_needed=0):
        """
        Get available lots for this product at a specific location
        Returns lots ordered by FEFO (First-Expire-First-Out)
        """
        lots = self.env["stock.lot"].search(
            [
                ("product_id.product_tmpl_id", "=", self.id),
                ("is_expired", "=", False),
                ("is_quarantined", "=", False),
            ],
            order="expiry_date ASC",
        )

        available_lots = []
        for lot in lots:
            # Calculate available quantity at location
            quants = self.env["stock.quant"].search(
                [
                    ("product_id.product_tmpl_id", "=", self.id),
                    ("lot_id", "=", lot.id),
                    ("location_id", "=", location_id),
                    ("quantity", ">", 0),
                ]
            )

            available_quantity = sum(quants.mapped("quantity"))
            if available_quantity > 0:
                available_lots.append(
                    {
                        "lot": lot,
                        "available_quantity": available_quantity,
                        "expiry_date": lot.expiry_date,
                        "days_to_expiry": lot.days_to_expiry,
                    }
                )

        return available_lots

    def get_fefo_lot(self, location_id, quantity_needed):
        """
        Get the best lot according to FEFO (First-Expire-First-Out) logic
        """
        available_lots = self.get_available_lots(location_id, quantity_needed)

        for lot_info in available_lots:
            if lot_info["available_quantity"] >= quantity_needed:
                return lot_info["lot"]

        # If no single lot has enough quantity, return the lot with the most available quantity
        if available_lots:
            return max(available_lots, key=lambda x: x["available_quantity"])["lot"]

        return False

    def check_sale_allowed(self, lot_id=None, quantity=1):
        """
        Check if sale is allowed for this product
        Returns dict with allowed status and reason
        """
        result = {"allowed": True, "reason": "", "warnings": []}

        # Check if product is a pharma product and requires special handling
        if self.is_pharma_product:
            # Check expiry if lot is specified
            if lot_id:
                lot = self.env["stock.lot"].browse(lot_id)
                if lot.is_expired:
                    result["allowed"] = False
                    result["reason"] = "Product batch has expired"
                    return result

                if lot.days_to_expiry < self.min_expiry_days:
                    result["warnings"].append(
                        f"Batch expires in {lot.days_to_expiry} days (minimum: {self.min_expiry_days})"
                    )

                if lot.is_quarantined:
                    result["allowed"] = False
                    result["reason"] = "Product batch is quarantined"
                    return result

        # Check if prescription is required
        if self.is_prescription_required:
            result["warnings"].append("Prescription required")

        # Check if controlled substance
        if self.is_controlled_substance:
            result["warnings"].append(
                "Controlled substance - pharmacist verification required"
            )

        # Check if pharmacist approval required
        if self.requires_pharmacist_approval:
            result["warnings"].append("Pharmacist approval required")

        # Check if ID capture required
        if self.requires_id_capture:
            result["warnings"].append("Customer ID capture required")

        return result

    def get_pricing_info(self, pricelist_id=None, quantity=1):
        """
        Get pricing information for this product
        """
        if not pricelist_id:
            pricelist_id = self.env["product.pricelist"].search(
                [("company_id", "=", self.env.company.id)], limit=1
            )

        # Get price from pricelist
        price = pricelist_id.get_product_price(self, quantity, self.env.user.partner_id)

        # Check minimum margin
        cost_price = self.standard_price
        min_price = cost_price * (1 + self.min_margin_percentage / 100)

        if price < min_price:
            result = {
                "price": price,
                "min_price": min_price,
                "margin_violation": True,
                "margin_percentage": ((price - cost_price) / cost_price * 100)
                if cost_price > 0
                else 0,
            }
        else:
            result = {
                "price": price,
                "min_price": min_price,
                "margin_violation": False,
                "margin_percentage": ((price - cost_price) / cost_price * 100)
                if cost_price > 0
                else 0,
            }

        return result

    def get_display_info(self):
        """
        Get formatted display information for POS
        """
        display_name = self.name
        if self.generic_name:
            display_name += f" ({self.generic_name})"
        if self.strength:
            display_name += f" {self.strength}"
        if self.dosage_form_id:
            display_name += f" - {self.dosage_form_id.display_name}"
        elif self.dosage_form:
            display_name += f" - {self.get_dosage_form_label()}"

        return {
            "name": display_name,
            "generic_name": self.generic_name,
            "strength": self.strength,
            "dosage_form": self.dosage_form_id.display_name
            if self.dosage_form_id
            else self.get_dosage_form_label(),
            "pack_size": self.pack_size,
            "is_prescription_required": self.is_prescription_required,
            "is_controlled_substance": self.is_controlled_substance,
            "requires_pharmacist_approval": self.requires_pharmacist_approval,
            "requires_id_capture": self.requires_id_capture,
        }

    @api.depends("dosage_form_id")
    def _compute_dosage_form(self):
        for template in self:
            if template.dosage_form_id:
                template.dosage_form = template.dosage_form_id.name
            else:
                template.dosage_form = False

    def _inverse_dosage_form(self):
        for template in self:
            if template.dosage_form:
                dosage_form = self.env["pharmacy.dosage.form"].search(
                    [("name", "=", template.dosage_form)], limit=1
                )
                if dosage_form:
                    template.dosage_form_id = dosage_form.id
                else:
                    template.dosage_form_id = False
            else:
                template.dosage_form_id = False

    def get_dosage_form_label(self):
        """Get human-readable dosage form label"""
        return dict(self._fields["dosage_form"].selection).get(
            self.dosage_form, self.dosage_form
        )

    def action_view_dispensing_history(self):
        """View dispensing history for this product"""
        return {
            "name": _("Dispensing History"),
            "type": "ir.actions.act_window",
            "res_model": "pharmacy.dispensing",
            "view_mode": "list,form",
            "domain": [("product_id", "=", self.id)],
            "context": {"default_product_id": self.id},
        }

    def action_view_stock_expiry(self):
        """View stock expiry information"""
        return {
            "name": _("Stock Expiry"),
            "type": "ir.actions.act_window",
            "res_model": "stock.lot",
            "view_mode": "list,form",
            "domain": [("product_id.product_tmpl_id", "=", self.id)],
            "context": {"default_product_id": self.id},
        }

    @api.model
    def get_expiring_products(self, days=30):
        """Get products expiring within specified days"""
        target_date = fields.Date.today() + timedelta(days=days)

        lots = self.env["stock.lot"].search(
            [
                ("expiry_date", "<=", target_date),
                ("expiry_date", ">=", fields.Date.today()),
                ("is_expired", "=", False),
            ]
        )

        return lots.mapped("product_id.product_tmpl_id")

    @api.model
    def get_expired_products(self):
        """Get products with expired stock"""
        lots = self.env["stock.lot"].search([("is_expired", "=", True)])
        return lots.mapped("product_id.product_tmpl_id")

    def generate_barcode_label(self):
        """Generate barcode label for product"""
        return self.env.ref("Pharmacy.action_report_product_label").report_action(self)


class ProductProduct(models.Model):
    _inherit = "product.product"

    # Override methods to use template methods
    def get_available_lots(self, location_id, quantity_needed=0):
        return self.product_tmpl_id.get_available_lots(location_id, quantity_needed)

    def get_fefo_lot(self, location_id, quantity_needed):
        return self.product_tmpl_id.get_fefo_lot(location_id, quantity_needed)

    def check_sale_allowed(self, lot_id=None, quantity=1):
        return self.product_tmpl_id.check_sale_allowed(lot_id, quantity)

    def get_pricing_info(self, pricelist_id=None, quantity=1):
        return self.product_tmpl_id.get_pricing_info(pricelist_id, quantity)

    def get_display_info(self):
        return self.product_tmpl_id.get_display_info()
