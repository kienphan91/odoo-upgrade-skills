from odoo import api, fields, models
from odoo.osv import expression


class LegPy(models.Model):
    _name = 'leg.py'
    _description = 'Legacy API fixture'

    name = fields.Char(required=True)
    code = fields.Char()

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Code must be unique'),
    ]

    def name_get(self):
        return [(rec.id, '[%s] %s' % (rec.code or '-', rec.name)) for rec in self]

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        # 17.0 signature. From 18.0 name_search() calls _search_display_name() instead and never reaches this method.
        domain = expression.AND([domain or [], [('code', operator, name)]])
        return self._search(domain, limit=limit, order=order, access_rights_uid=None)

    def probe(self):
        self.check_access_rights('read')
        self.check_access_rule('read')
        self._cr.execute('SELECT 1')
        uid = self._uid
        ctx = self._context
        groups = self.env.user.groups_id
        partner = self.env['res.partner'].search([], limit=1)
        phone = partner.mobile
        grouped = self.env['res.partner'].read_group([], ['id:count'], ['is_company'])
        return uid, ctx, groups, phone, grouped
