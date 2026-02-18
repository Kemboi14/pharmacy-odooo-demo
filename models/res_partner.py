# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class ResPartner(models.Model):
    _inherit = 'res.partner'

    pharmacy_patient_id = fields.Many2one('pharmacy.patient', 'Pharmacy Patient Profile', readonly=True)
    is_pharmacy_patient = fields.Boolean('Is Pharmacy Patient', compute='_compute_is_pharmacy_patient', store=True)

    @api.depends('pharmacy_patient_id')
    def _compute_is_pharmacy_patient(self):
        for partner in self:
            partner.is_pharmacy_patient = bool(partner.pharmacy_patient_id)

    def action_view_pharmacy_profile(self):
        """View the linked pharmacy patient profile"""
        self.ensure_one()
        if not self.pharmacy_patient_id:
            return False
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pharmacy Patient Profile'),
            'res_model': 'pharmacy.patient',
            'res_id': self.pharmacy_patient_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
