-- Gate PA-01, PA-14, PA-15. READ ONLY (plain SELECTs). Odoo 17.0 / 18.0 / 19.0.
-- Run with: PGOPTIONS='-c default_transaction_read_only=on' psql -d <db> -f 01_env_and_modules.sql
\pset pager off
\echo '== Server and database'
SELECT current_database() AS db,
       current_setting('server_version') AS postgres,
       pg_size_pretty(pg_database_size(current_database())) AS db_size,
       current_setting('server_encoding') AS encoding;

\echo '== Odoo version recorded in the database (module "base")'
SELECT name, state, latest_version FROM ir_module_module WHERE name = 'base';

\echo '== Module states that must be empty before a rehearsal ("to upgrade", "to install", "to remove")'
SELECT name, state FROM ir_module_module WHERE state IN ('to upgrade', 'to install', 'to remove') ORDER BY name;

\echo '== Installed modules by origin (heuristic, from author and licence in the module table)'
SELECT CASE
         WHEN license LIKE 'OEEL%'                                  THEN '1 enterprise (OEEL-1)'
         WHEN license = 'OPL-1'                                     THEN '2 paid third-party (OPL-1)'
         WHEN author ILIKE '%Odoo Community Association%'
              OR author ILIKE '%(OCA)%'                             THEN '3 OCA'
         WHEN author ~* '^odoo(\s+s\.a\.)?\s*(,.*)?$'                             THEN '4 odoo community'
         ELSE                                                            '5 other: custom or third-party'
       END AS origin,
       count(*) AS modules
FROM ir_module_module WHERE state = 'installed' GROUP BY 1 ORDER BY 1;

\echo '== Installed modules that are NOT Odoo S.A. community modules (this is your upgrade scope)'
SELECT name, latest_version, author, license, application
FROM ir_module_module
WHERE state = 'installed'
  AND NOT (author ~* '^odoo(\s+s\.a\.)?\s*(,.*)?$' AND COALESCE(license, '') NOT LIKE 'OEEL%' AND COALESCE(license, '') <> 'OPL-1')
ORDER BY license, name;

\echo '== Installed modules whose recorded version does not start with the Odoo series of "base" (never updated across a version?)'
SELECT m.name, m.latest_version, b.latest_version AS base_version
FROM ir_module_module m, (SELECT latest_version FROM ir_module_module WHERE name = 'base') b
WHERE m.state = 'installed'
  AND m.latest_version IS NOT NULL
  AND split_part(m.latest_version, '.', 1) || '.' || split_part(m.latest_version, '.', 2)
      <> split_part(b.latest_version, '.', 1) || '.' || split_part(b.latest_version, '.', 2)
ORDER BY m.name;

\echo '== Companies, languages, currencies'
SELECT (SELECT count(*) FROM res_company) AS companies,
       (SELECT count(*) FROM res_lang WHERE active) AS active_languages,
       (SELECT count(*) FROM res_currency WHERE active) AS active_currencies,
       (SELECT count(*) FROM res_users WHERE active AND NOT share) AS internal_users,
       (SELECT count(*) FROM res_users WHERE active AND share) AS portal_or_public_users;
