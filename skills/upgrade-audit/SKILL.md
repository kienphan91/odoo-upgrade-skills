---
name: upgrade-audit
description: Audit an Odoo database copy and custom addons before an upgrade (17.0 or 18.0 to 19.0). Use for "odoo upgrade audit", "is this module ready for 19", "readiness check", "what breaks when upgrading odoo". Produces a gate report.
---

# upgrade-audit

Audit the **source** side of an Odoo upgrade: which modules exist, which custom code and views will break on the
target series, what lives only in the database, and what the target platform requires. Gates: PA-01 to PA-16 of
`reference/upgrade-gates.md` (the reference for every pass/fail rule).

## Safety rule (read first)

Never run a write, `DROP`, `-u`, `-i`, `neutralize` or any destructive command against a production database.
Only connect to a **restored copy**. If the user gives a database name and you cannot tell that it is a copy, stop and
ask. All SQL in this skill is `SELECT` and is run in a read-only session (a guard against accidents, not a permission
system). Never print passwords; read connection data from the environment (`PGHOST`, `PGUSER`, `PGPASSWORD` or `~/.pgpass`).

## Inputs to collect

- `SRC` / `TARGET` series (for example 17.0 -> 19.0), `ADDONS` = folders with custom/OCA/third-party addons, `COPY` = copy
  database name, the connection variables, and `KIT` = the folder that contains `reference/` and `tools/` (this repository).
- Check the tools are there: `ls "$KIT/tools/scan_custom_code.py" "$KIT/tools/sql/01_env_and_modules.sql"` lists both files.

## Steps

1. **Make the session read-only and prove it.**
   `export PGOPTIONS='-c default_transaction_read_only=on'; psql -d "$COPY" -Atc "show transaction_read_only"`
   Check: prints `on`. If it prints `off`, stop.
2. **Inventory (PA-01).** `mkdir -p audit && psql -d "$COPY" -f "$KIT/tools/sql/01_env_and_modules.sql" > audit/01_modules.txt`
   Check: the file has the sections "Module states that must be empty" (expect 0 rows) and "NOT Odoo S.A. community
   modules". Every module in the second list needs an owner and a decision; list them in the report.
3. **Availability on the target (PA-02).**
   `psql -d "$COPY" -Atc "select name from ir_module_module where state='installed' order by name" > audit/installed.txt`
   then `python3 "$KIT/tools/modules_missing_in_target.py" --installed audit/installed.txt --addons <target core addons dir> <each target-series addons dir> --series <TARGET>`
   Check: exit code 0 means every module is FOUND. Every MISSING / NOT-INSTALLABLE / WRONG-SERIES line goes in the report.
   If the user has no target addons checked out, mark PA-02 UNVERIFIED instead of guessing.
4. **Static scan of code and views (PA-03, PA-04, PA-05, PA-09, PA-10, PA-12, PA-16).**
   `python3 "$KIT/tools/scan_custom_code.py" $ADDONS --target <TARGET> --min-severity review --format tsv > audit/scan.tsv`
   Check: the file has a header line and one row per finding; count rows per rule and severity with
   `cut -f3,5 audit/scan.tsv | sort | uniq -c | sort -rn`. `error` rows are blockers, `warn` are deprecations or silent
   changes (notably `PY-SQL-CONSTRAINTS` on 19.0: constraints are silently not created), `review` rows need a human.
5. **Database-resident customizations (PA-07, PA-13).** `psql -d "$COPY" -f "$KIT/tools/sql/02_customizations.sql" > audit/02_db_customizations.txt`
   Check: no `ERROR` in the output (`grep -c ERROR audit/02_db_customizations.txt` prints 0). Views without external id,
   manual fields, server actions with code and custom assets are items for the porting plan.
6. **Scheduled actions and mail (PA-10, PA-11).** `psql -d "$COPY" -f "$KIT/tools/sql/03_cron_and_mail.sql" > audit/03_cron_mail.txt`
7. **Security (PA-09), Odoo 17.0-19.0 only.** `psql -d "$COPY" -f "$KIT/tools/sql/04_security.sql" > audit/04_security.txt`
   Check: on a 20.0 database this file errors (tables differ): then mark PA-09 UNVERIFIED for the SQL part.
8. **Platform (PA-15).** Record `psql --version`, `python3 --version`, `wkhtmltopdf --version` and compare with the
   table in PA-15 for the target. Search `odoo.conf` for removed options (`grep -n longpolling_port odoo.conf`).
9. **Steps that need a target server or a browser (PA-06, PA-08, PA-12, PA-16).** The scripts in this folder do not run them. If
   the user has a target server, the manual route is in `reference/upgrade-gates.md`: update a **copy** with `-u all` and read the
   log, run Odoo's `upgrade_code` on a copy of the source, render each custom report, load the backend with the browser console
   open. Otherwise mark these gates NOT RUN, never PASS.
10. **Write the report** `audit/upgrade-audit-report.md`: one table row per gate PA-01..PA-16 with result
    (PASS / FAIL / NOT RUN / UNVERIFIED), the evidence file, and for FAIL the first three findings. Check: every gate id
    appears exactly once, and every PASS names an evidence file.

## Rules for the result

- A gate is PASS only with an evidence file you produced in this run. "No findings" from the scanner is not a pass for
  PA-06 (view validation on the target) or PA-16 (JavaScript at run time): those need the target server or a browser.
- Report what was not run. Do not turn an UNVERIFIED line of the reference into a statement of fact.
- Offer, do not perform, fixes: the porting itself is a separate task, not part of this sample.
