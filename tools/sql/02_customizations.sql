-- Gate PA-07, PA-12, PA-13. READ ONLY. Odoo 17.0 / 18.0 / 19.0.
-- Finds customizations that live in the database and therefore are NOT in any addon you can grep.
\pset pager off
\echo '== Manual (UI-created, x_) fields per model'
SELECT model, count(*) AS manual_fields, string_agg(name, ', ' ORDER BY name) AS fields
FROM ir_model_fields WHERE state = 'manual' GROUP BY model ORDER BY model;

\echo '== Models created from the UI (x_ models)'
SELECT model, name->>'en_US' AS name FROM ir_model WHERE state = 'manual' ORDER BY model;

\echo '== Views with no external id (created in the database, e.g. Studio or the HTML/XML editor)'
SELECT v.id, v.name, v.model, v.type, v.inherit_id, v.active, v.priority
FROM ir_ui_view v
LEFT JOIN ir_model_data d ON d.model = 'ir.ui.view' AND d.res_id = v.id
WHERE d.id IS NULL
ORDER BY v.model, v.id;

\echo '== Module views edited in the database (noupdate record or arch edited since load)'
SELECT v.id, d.module || '.' || d.name AS xmlid, v.model, v.type, d.noupdate, v.arch_updated
FROM ir_ui_view v JOIN ir_model_data d ON d.model = 'ir.ui.view' AND d.res_id = v.id
WHERE d.noupdate OR v.arch_updated
ORDER BY d.module, d.name;

\echo '== Server actions with Python code and no external id'
SELECT a.id, a.name->>'en_US' AS name, a.state, m.model
FROM ir_act_server a
JOIN ir_model m ON m.id = a.model_id
LEFT JOIN ir_model_data d ON d.model = 'ir.actions.server' AND d.res_id = a.id
WHERE d.id IS NULL AND a.state = 'code'
ORDER BY a.id;

\echo '== Report actions with no external id'
SELECT r.id, r.name, r.model, r.report_type, r.report_name
FROM ir_act_report_xml r
LEFT JOIN ir_model_data d ON d.model = 'ir.actions.report' AND d.res_id = r.id
WHERE d.id IS NULL ORDER BY r.id;

\echo '== Mail templates with no external id'
SELECT t.id, t.name->>'en_US' AS name, t.model FROM mail_template t
LEFT JOIN ir_model_data d ON d.model = 'mail.template' AND d.res_id = t.id
WHERE d.id IS NULL ORDER BY t.id;

\echo '== QWeb views and mail templates using t-raw (deprecated) in the database'
SELECT 'ir.ui.view' AS kind, id, name FROM ir_ui_view WHERE arch_db::text LIKE '%t-raw=%'
UNION ALL
SELECT 'mail.template', id, name->>'en_US' FROM mail_template WHERE body_html::text LIKE '%t-raw=%'
ORDER BY 1, 2;

\echo '== Saved filters (domains refer to fields by name: re-check after the upgrade)'
SELECT model_id, count(*) FROM ir_filters GROUP BY model_id ORDER BY 2 DESC LIMIT 20;

\echo '== Studio / Enterprise customization modules installed (UNVERIFIED for Enterprise: not tested by this kit)'
SELECT name, state FROM ir_module_module WHERE name IN ('web_studio', 'studio_customization') AND state = 'installed';

\echo '== Custom assets (ir.asset rows with no external id, i.e. created in the database)'
SELECT a.id, a.name, a.bundle, a.directive, a.path, a.active
FROM ir_asset a LEFT JOIN ir_model_data d ON d.model = 'ir.asset' AND d.res_id = a.id
WHERE d.id IS NULL ORDER BY a.bundle, a.id;

\echo '== Website: theme modules, website-specific view copies, pages (only if the website module is installed)'
SELECT EXISTS (SELECT 1 FROM ir_module_module WHERE name = 'website' AND state = 'installed') AS has_website \gset
\if :has_website
SELECT name, state, latest_version FROM ir_module_module WHERE state = 'installed' AND name LIKE 'theme\_%' ORDER BY name;
SELECT v.id, v.key, v.name, v.website_id, v.active FROM ir_ui_view v WHERE v.website_id IS NOT NULL ORDER BY v.key, v.website_id;
SELECT p.id, p.url, p.is_published, p.website_id FROM website_page p ORDER BY p.website_id, p.url;
SELECT id, name, domain FROM website ORDER BY id;
\else
\echo '(website not installed)'
\endif
