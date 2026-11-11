# Version-neutral test patterns for a database or addon that is being upgraded. MIT licence (see LICENSE).
#
# Four patterns, one per kind of risk. Copy the one you need into your own addon's tests/ and replace the data:
#   test_unique_constraint_is_enforced  a database constraint still exists (Odoo 19.0 skips old-style `_sql_constraints`
#                                       with a log warning only, so only a test that tries to break the rule notices)
#   test_sale_invoice_payment           a business flow, compared against its own totals (no hard-coded numbers)
#   test_access_rights                  access rights per role, written for 17.0 (check_access_rights) and 18.0+ (has_access)
#   test_cron_definitions_resolve       scheduled actions still point at a model, a server action and a user
#
# The upgrade scanner reports two lines of this file (`groups_id` and `check_access_rights`): they are the deliberate
# 17.0 branches of the two helpers below, guarded by feature checks.
#
# Rules used throughout: create all data inside the test, skip visibly (never pass silently) when a module is missing,
# never call real mail servers or external services, never commit.
import secrets

from psycopg2 import IntegrityError

from odoo import Command
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


def _installed(env, *modules):
    return all(
        env['ir.module.module'].sudo().search_count([('name', '=', name), ('state', '=', 'installed')])
        for name in modules
    )


def _group_field(env):
    """res.users field holding the explicit groups: groups_id up to 18.0, group_ids from 19.0."""
    return 'group_ids' if 'group_ids' in env['res.users']._fields else 'groups_id'


def _can(env, user, model, operation):
    """Access check that works on 17.0 (check_access_rights) and on 18.0 and later (has_access)."""
    records = env[model].with_user(user).browse()
    if hasattr(records, 'has_access'):
        return records.has_access(operation)
    return records.check_access_rights(operation, raise_exception=False)


@tagged('post_install', '-at_install', 'upgrade_test_pattern')
class TestUpgradePatterns(TransactionCase):

    def _user(self, login, groups):
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': login, 'login': login, 'email': login + '@example.com',
            _group_field(self.env): [Command.set([self.env.ref(g).id for g in groups])],
        })

    def test_unique_constraint_is_enforced(self):
        """Pattern for a database unique constraint. Replace res.currency/name by your model and field.
        res.currency.name is unique in the database on every series (`_sql_constraints` up to 18.0, `models.Constraint`
        from 19.0). A savepoint keeps the test transaction usable after the database refuses the second row.
        If your own constraint is a Python @api.constrains rule, assert ValidationError instead of IntegrityError."""
        Currency = self.env['res.currency']
        Currency.create({'name': 'ZQX', 'symbol': 'Z', 'rounding': 0.01})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            Currency.create({'name': 'ZQX', 'symbol': 'Z', 'rounding': 0.01})

    def test_sale_invoice_payment(self):
        """Pattern for a business flow: quotation -> confirm -> invoice -> post -> payment.
        Compare the invoice with the order of the same run instead of a literal number."""
        if not _installed(self.env, 'sale', 'account'):
            self.skipTest('sale/account not installed')
        partner = self.env['res.partner'].create({'name': 'Pattern customer'})
        product = self.env['product.product'].create(
            {'name': 'Pattern service', 'type': 'service', 'list_price': 250.0})
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [Command.create({'product_id': product.id, 'product_uom_qty': 2})],
        })
        order.action_confirm()
        invoice = order._create_invoices()
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        self.assertAlmostEqual(invoice.amount_total, order.amount_total, places=2)
        self.assertGreater(invoice.amount_total, 0)
        context = {'active_model': 'account.move', 'active_ids': invoice.ids}
        self.env['account.payment.register'].with_context(**context).create({}).action_create_payments()
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertAlmostEqual(sum(invoice.line_ids.mapped('debit')), sum(invoice.line_ids.mapped('credit')), places=2)

    def test_access_rights(self):
        """Pattern for access rights per role. Add the roles and models of your own addon."""
        portal = self._user('upgrade_portal', ['base.group_portal'])
        internal = self._user('upgrade_internal', ['base.group_user'])
        self.assertFalse(_can(self.env, portal, 'res.partner', 'unlink'))
        self.assertFalse(_can(self.env, portal, 'product.template', 'create'))
        self.assertTrue(_can(self.env, internal, 'res.partner', 'read'))
        if _installed(self.env, 'account'):
            self.assertFalse(_can(self.env, internal, 'account.move', 'read'))

    def test_cron_definitions_resolve(self):
        """Pattern for scheduled actions: each active cron still has a server action, a model and an active user.
        Crons are not run here: running one inside a test transaction would commit."""
        crons = self.env['ir.cron'].search([('active', '=', True)])
        self.assertTrue(crons)
        for cron in crons:
            self.assertTrue(cron.ir_actions_server_id.exists(), 'cron %s has no server action' % cron.cron_name)
            self.assertIn(cron.ir_actions_server_id.model_name, self.env, 'cron %s model missing' % cron.cron_name)
            # OdooBot (base.user_root) is archived by design and is the normal cron user
            self.assertTrue(cron.user_id.active or cron.user_id == self.env.ref('base.user_root'),
                            'cron %s runs as an inactive user' % cron.cron_name)
