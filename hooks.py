# -*- coding: utf-8 -*-

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def post_init_hook(env):

    # Ensure branch default structures exist (journals/locations). The model's
    # create() already does this for new branches, but for existing branches or
    # upgrades we re-run idempotent initializers.
    for branch in env["pharmacy.branch"].search([]):
        branch._create_default_locations()
        branch._create_default_journals()

    # Ensure demo POS configs exist for branches.
    # We keep this conservative and idempotent to avoid breaking existing POS.
    PosConfig = env["pos.config"]
    for branch in env["pharmacy.branch"].search([]):
        existing = PosConfig.search([("branch_id", "=", branch.id)], limit=1)
        if existing:
            continue
        PosConfig.create(
            {
                "name": f"{branch.name} POS",
                "branch_id": branch.id,
                "is_pharmacy_pos": True,
                "allow_insurance_sales": True,
                "require_prescription_for_rx": True,
                "enforce_fefo": True,
            }
        )

    # Configure POS payment methods and attach them to each POS config.
    # Cash payment methods cannot be shared across POS configs in Odoo 18,
    # so we create a unique cash method per POS and share non-cash methods.
    def _get_xmlid(xmlid):
        try:
            return env.ref(xmlid)
        except Exception:
            return env[None]

    non_cash_methods = []
    for xmlid in [
        "Pharmacy.payment_method_mpesa_pharmacy",
        "Pharmacy.payment_method_card_pharmacy",
        "Pharmacy.payment_method_insurance_pharmacy",
    ]:
        rec = _get_xmlid(xmlid)
        if rec:
            non_cash_methods.append(rec)

    cash_journal = _get_xmlid("Pharmacy.pharmacy_cash_journal")
    PaymentMethod = env["pos.payment.method"]

    for config in env["pos.config"].search([("is_pharmacy_pos", "=", True)]):
        # Check if this config already has a cash payment method
        existing_cash = config.payment_method_ids.filtered(lambda m: m.is_cash_count)
        if not existing_cash:
            cash_pm = PaymentMethod.create({
                "name": f"{config.name} Cash",
                "is_cash_count": True,
                "journal_id": cash_journal.id if cash_journal else False,
                "company_id": config.company_id.id,
            })
        else:
            cash_pm = existing_cash[0]
        all_methods = [cash_pm] + non_cash_methods
        config.write(
            {"payment_method_ids": [(6, 0, [pm.id for pm in all_methods])]}
        )

    # Put demo stock on hand in each branch shop-floor location so that FEFO / expiry
    # dashboards work immediately.
    # We use stock.quant inventory adjustment fields which are stable in Odoo.
    def _set_quant(location, product, lot, qty):
        Quant = env["stock.quant"]
        quant = Quant.search(
            [
                ("location_id", "=", location.id),
                ("product_id", "=", product.id),
                ("lot_id", "=", lot.id),
            ],
            limit=1,
        )
        if not quant:
            quant = Quant.create(
                {
                    "location_id": location.id,
                    "product_id": product.id,
                    "lot_id": lot.id,
                }
            )
        # Idempotent: always enforce the desired on-hand quantity.
        quant.inventory_quantity = qty
        quant.action_apply_inventory()

    demo_products = {
        "paracetamol": _get_xmlid("Pharmacy.demo_product_paracetamol"),
        "amoxicillin": _get_xmlid("Pharmacy.demo_product_amoxicillin"),
        "diazepam": _get_xmlid("Pharmacy.demo_product_diazepam"),
    }
    demo_lots = {
        "para": _get_xmlid("Pharmacy.demo_lot_para_2027"),
        "amox": _get_xmlid("Pharmacy.demo_lot_amox_2026"),
        "diaz": _get_xmlid("Pharmacy.demo_lot_diaz_2026"),
    }

    for branch in env["pharmacy.branch"].search([]):
        shop_floor = branch.get_shop_floor_location()
        if not shop_floor:
            continue

        if demo_products["paracetamol"] and demo_lots["para"]:
            _set_quant(shop_floor, demo_products["paracetamol"], demo_lots["para"], 200)
        if demo_products["amoxicillin"] and demo_lots["amox"]:
            _set_quant(shop_floor, demo_products["amoxicillin"], demo_lots["amox"], 50)
        if demo_products["diazepam"] and demo_lots["diaz"]:
            _set_quant(shop_floor, demo_products["diazepam"], demo_lots["diaz"], 20)

    # Create demo POS sessions + orders (cash + insurance). We use the same approach
    # as the included test script to stay compatible with Odoo 18.
    def _ensure_demo_pos_order(ref, config, is_insurance=False):
        existing = env["pos.order"].search([("pos_reference", "=", ref)], limit=1)
        if existing:
            return existing

        session = env["pos.session"].create(
            {
                "config_id": config.id,
                "user_id": env.user.id,
            }
        )
        session.action_pos_session_open()

        order_vals = {
            "session_id": session.id,
            "branch_id": config.branch_id.id,
            "pos_reference": ref,
            "lines": [
                (
                    0,
                    0,
                    {
                        "product_id": demo_products["paracetamol"].id,
                        "qty": 2,
                        "price_unit": demo_products["paracetamol"].lst_price,
                        "lot_id": demo_lots["para"].id,
                    },
                )
            ],
        }

        if is_insurance:
            insurer = env["pharmacy.insurer"].search([], limit=1)
            plan = (
                env["pharmacy.insurer.plan"].search(
                    [("insurer_id", "=", insurer.id)], limit=1
                )
                if insurer
                else False
            )
            if insurer and plan:
                order_vals.update(
                    {
                        "is_insurance_sale": True,
                        "insurer_id": insurer.id,
                        "plan_id": plan.id,
                        "member_number": "DEMO-MEM-001",
                        "patient_name": "Demo Insurance Patient",
                    }
                )

        order = env["pos.order"].create(order_vals)

        # Try creating dispensing records if configured.
        try:
            order.action_create_dispensing_records()
        except Exception:
            pass

        # Close session (optional). We avoid payment posting to keep this light.
        try:
            session.action_pos_session_closing_control()
        except Exception:
            pass

        return order

    # Create orders only for Westlands branch (code: WST002)
    westlands_branch = env["pharmacy.branch"].search([("code", "=", "WST002")], limit=1)
    if westlands_branch:
        pos_config = env["pos.config"].search(
            [("is_pharmacy_pos", "=", True), ("branch_id", "=", westlands_branch.id)],
            limit=1,
        )

        if pos_config and demo_products["paracetamol"] and demo_lots["para"]:
            _ensure_demo_pos_order(
                "PHARM-DEMO-CASH-001", pos_config, is_insurance=False
            )
            _ensure_demo_pos_order("PHARM-DEMO-INS-001", pos_config, is_insurance=True)
    else:
        _logger.warning(
            "Westlands branch (WST002) not found. Skipping demo POS order creation."
        )
