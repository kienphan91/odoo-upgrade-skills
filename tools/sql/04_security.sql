-- Gate PA-09. READ ONLY. Odoo 17.0 / 18.0 / 19.0. NOT for 20.0: the ir_model_access and ir_rule tables do not exist there (UNVERIFIED what replaced them).
\pset pager off
\echo '== Models of NON-Odoo-S.A. modules that have a table but no access rule row (nobody but the superuser can use them)'
SELECT d.module AS defined_by, m.model
FROM ir_model m
JOIN ir_model_data d ON d.model = 'ir.model' AND d.res_id = m.id
JOIN ir_module_module mm ON mm.name = d.module AND mm.state = 'installed' AND NOT (mm.author ~* '^odoo(\s+s\.a\.)?\s*(,.*)?$')
WHERE NOT m.transient
  AND EXISTS (SELECT 1 FROM information_schema.tables t WHERE t.table_schema = 'public' AND t.table_name = replace(m.model, '.', '_'))
  AND NOT EXISTS (SELECT 1 FROM ir_model_access a WHERE a.model_id = m.id)
ORDER BY 1, 2;

\echo '== Access rows without a group (apply to everybody, including portal and public)'
SELECT a.id, a.name, m.model, a.perm_read, a.perm_write, a.perm_create, a.perm_unlink
FROM ir_model_access a JOIN ir_model m ON m.id = a.model_id
WHERE a.group_id IS NULL AND a.active ORDER BY m.model;

\echo '== Record rules with no external id (created by hand)'
SELECT r.id, r.name, m.model, r.domain_force, r.active
FROM ir_rule r JOIN ir_model m ON m.id = r.model_id
LEFT JOIN ir_model_data d ON d.model = 'ir.rule' AND d.res_id = r.id
WHERE d.id IS NULL ORDER BY r.id;

\echo '== Record rules from NON-Odoo-S.A. modules or with no xmlid (your rules; mentions_groups_id=t means it breaks on 19.0: groups_id became group_ids)'
SELECT r.id, COALESCE(d.module || '.' || d.name, '(no xmlid)') AS xmlid, m.model,
       r.domain_force ~ '(groups_id|user\.groups)' AS mentions_groups_id,
       left(regexp_replace(COALESCE(r.domain_force, ''), '\s+', ' ', 'g'), 120) AS domain
FROM ir_rule r JOIN ir_model m ON m.id = r.model_id
LEFT JOIN ir_model_data d ON d.model = 'ir.rule' AND d.res_id = r.id
LEFT JOIN ir_module_module mm ON mm.name = d.module
WHERE d.id IS NULL OR NOT (mm.author ~* '^odoo(\s+s\.a\.)?\s*(,.*)?$')
ORDER BY d.module, d.name;

\echo '== Groups defined by non-core modules'
SELECT d.module, d.name, g.id AS group_id
FROM res_groups g JOIN ir_model_data d ON d.model = 'res.groups' AND d.res_id = g.id
WHERE d.module NOT IN ('base') AND d.module IN (SELECT name FROM ir_module_module WHERE state = 'installed' AND NOT (author ~* '^odoo(\s+s\.a\.)?\s*(,.*)?$'))
ORDER BY d.module, d.name;

\echo '== Users per group (membership table res_groups_users_rel, same table name in 17, 18 and 19)'
SELECT d.module || '.' || d.name AS group_xmlid, count(rel.uid) AS users
FROM res_groups g
JOIN ir_model_data d ON d.model = 'res.groups' AND d.res_id = g.id
LEFT JOIN res_groups_users_rel rel ON rel.gid = g.id
GROUP BY 1 HAVING count(rel.uid) > 0 ORDER BY 2 DESC LIMIT 40;

\echo '== Administrators (members of base.group_system)'
SELECT u.id, u.login, u.active
FROM res_users u
JOIN res_groups_users_rel rel ON rel.uid = u.id
JOIN ir_model_data d ON d.model = 'res.groups' AND d.res_id = rel.gid AND d.module = 'base' AND d.name = 'group_system'
ORDER BY u.id;
