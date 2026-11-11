-- Gate PA-10, PA-11. READ ONLY. Odoo 17.0 / 18.0 / 19.0.
\pset pager off
\echo '== Scheduled actions (ir.cron): active ones are what runs on cutover day'
SELECT c.id, c.cron_name, c.active, c.interval_number, c.interval_type, c.nextcall, c.lastcall, c.user_id
FROM ir_cron c ORDER BY c.active DESC, c.nextcall;

\echo '== Scheduled actions that belong to no module (created by hand)'
SELECT c.id, c.cron_name, c.active
FROM ir_cron c LEFT JOIN ir_model_data d ON d.model = 'ir.cron' AND d.res_id = c.id
WHERE d.id IS NULL ORDER BY c.id;

\echo '== Outgoing mail servers (a rehearsal copy must not be able to send through these)'
SELECT id, name, smtp_host, smtp_port, smtp_encryption, active, from_filter FROM ir_mail_server ORDER BY sequence, id;

\echo '== Mail queue by state (anything "outgoing" on a copy will be sent if a server is active)'
SELECT state, count(*) FROM mail_mail GROUP BY state ORDER BY state;

\echo '== Mail alias domains and catch-all related parameters'
SELECT id, name, bounce_alias, catchall_alias, default_from FROM mail_alias_domain ORDER BY id;
SELECT key, value FROM ir_config_parameter
WHERE key LIKE 'mail.%' OR key IN ('web.base.url', 'web.base.url.freeze') ORDER BY key;

\echo '== Incoming mail servers (only if the fetchmail module is installed)'
SELECT EXISTS (SELECT 1 FROM ir_module_module WHERE name = 'fetchmail' AND state = 'installed') AS has_fetchmail \gset
\if :has_fetchmail
SELECT id, name, server_type, server, state, active FROM fetchmail_server ORDER BY id;
\else
\echo '(fetchmail not installed)'
\endif
