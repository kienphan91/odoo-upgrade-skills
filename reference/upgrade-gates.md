# Upgrade gates: reference for the two sample skills

A **gate** is one thing that must be true before the next stage of an Odoo upgrade, with a way to check it and a rule
that says pass or fail. This file is the short reference the skills in `skills/` point to. It covers Odoo
**Community** from 17.0 or 18.0 to 19.0, with a few notes for 20.0.

## 1. How to read the evidence labels

| Label | Meaning |
|---|---|
| **run** | executed in a throw-away container from the official image (`odoo:17.0`, `odoo:18.0`, `odoo:19.0`, `odoo:20.0`; `odoo --version` 17.0-20260908 and 18.0, 19.0, 20.0-20261102), Community, demo data, on 2026-11-11 and 2026-11-12 |
| **source** | read in the source code inside that image; not executed |
| **UNVERIFIED** | not checked. Treat as a question, not a fact |

Everything below was checked on small demo databases, never on a customer database, never on Odoo Enterprise and never
in a web browser. The official tags move: a later image can behave differently, so re-run the scripts on yours.

## 2. Version differences the scanner knows

`tools/scan_custom_code.py` reports a rule only when it matters for the target series you pass with `--target`.

| Topic | 17.0 | 18.0 | 19.0 | 20.0 | Status |
|---|---|---|---|---|---|
| `attrs=` / `states=` in views | rejected | rejected | rejected | rejected | run |
| list view root `<tree>` | ok | rejected (`Invalid view type: 'tree'`) | rejected | rejected | run |
| kanban `t-name="kanban-box"` | ok | installs, server logs a deprecation warning | installs silently; the web client source throws `Missing 'card' template.` | same, in `card_arch_parser.js` | install: run; client error: source only, not run in a browser |
| `<group expand=...>` in a search view | ok | ok | rejected | rejected | run |
| `name_get()` | exists, deprecated (an override does not feed `display_name`) | gone | gone | gone | run |
| `_name_search()` override | used by `name_search` | not called (use `_search_display_name`) | not called | not called | run on 17, 18, 19 |
| `_search(..., access_rights_uid=)` | exists | removed | removed | removed | source |
| `check_access_rights` / `check_access_rule` | ok | deprecated, works | deprecated, works | removed | run; deprecation text source |
| `_sql_constraints` | creates the constraint | creates it | **ignored, log warning only** | ignored | run on 17, 18, 19; 20 source |
| `Model._cr/_uid/_context` | ok | ok | deprecated | deprecated | run (works), source (deprecation) |
| `odoo.osv.expression` | ok | ok | works with `DeprecationWarning` | package gone | run |
| `read_group()` | ok | ok | works, deprecated | `read_group([], ['id:count'], ...)` raises `ValueError` | run |
| `groups_id` on res.users, views, menus, actions | `groups_id` | `groups_id` | `group_ids` | `group_ids` | run |
| `ir.cron` fields `numbercall`, `doall` | exist | removed (record fails to load) | removed | removed | run |
| product type | `detailed_type`; `type` has `product` | `type` = consu/service/combo + `is_storable` | same | same | run |
| `res.partner.mobile` | exists | exists | removed | removed | run |
| manifest `version` of another series (`17.0.1.0.0`) | accepted | `-i` skips it, exit 0; a new database aborts (exit 255) | `installable=False`, exit 0 | same as 19.0 | run |
| access rights file | `ir.model.access.csv` | same | same | `ir.access.csv` (columns `id,name,model_id,group_id/id,operation,domain`); the old file fails with `KeyError: 'ir.model.access'`; Odoo's `upgrade_code` converts it | run |
| QWeb `t-raw`, `t-esc` | render | render | render | **render nothing** (`t-out` works) | run |
| `@route(type='json')` | ok | ok | deprecated alias of `'jsonrpc'` | same warning in source | source |

Not in the table, on purpose: anything about JavaScript at run time, the website editor, Enterprise modules.

## 3. Audit gates (PA)

For each gate: what is checked, how (script or manual), the pass rule.

| Gate | What | How | Pass rule |
|---|---|---|---|
| PA-01 | Inventory of installed modules and their owners | `tools/sql/01_env_and_modules.sql` on a copy | no module in state `to upgrade`, `to install` or `to remove`; every non-core module has an owner and a decision (port, replace, drop). The "origin" column is a heuristic: correct it by hand. Enterprise licence detection (`OEEL-1`) was not exercised: UNVERIFIED |
| PA-02 | Every non-core module has source for the target series | `tools/modules_missing_in_target.py` against the target addons | exit 0. A module MISSING from core may be renamed or merged: look in the target series before calling it removed |
| PA-03 | Manifests valid for the target | scanner rule `MANIFEST-VERSION-SERIES` | no error. A 4-part version must start with the target series. A module with another series prefix is skipped silently (exit 0): check the module is `installed`, not only the exit code |
| PA-04 | Deprecated or removed Python APIs | scanner `PY-*` rules; then confirm by running | no `error` left; each `warn` fixed or explained. Add a test that tries to violate every old `_sql_constraints` rule |
| PA-05 | View XML the target refuses | scanner `XML-*` rules | no `error` left, and the module installs on the target |
| PA-06 | Every view validates on the target (xpath, inheritance) | not covered by the scripts here: update a copy with `-u all` on the target and read the log for `ParseError` and "cannot be located in parent view" | no view error. One broken inheriting view makes every view of its chain fail: fix the first one listed |
| PA-07 | Customizations that live only in the database | `tools/sql/02_customizations.sql` | each row has a decision. The demo databases had no customizations, so the result sections were not seen with real rows: UNVERIFIED |
| PA-08 | Odoo's own code rewriter on a copy of the source | not covered by the scripts here: `odoo/cli/upgrade_code.py` standalone, on a git branch or a copy | every hunk of the diff reviewed. It converts `<tree>`, `_sql_constraints`, `_cr/_uid/_context`; it does not touch `attrs`, `states`, `groups_id`, `name_get`, `_name_search`, cron fields, `kanban-box`, `mobile` or manifest versions |
| PA-09 | Security: groups, access rights, record rules | `tools/sql/04_security.sql` (17.0 to 19.0 only), scanner `GROUPS` and `ACL-CSV` rules, then a role walk-through | no custom model without access rows; no `groups_id` on a 19.0 target; each role sees the same menus. On 20.0 the SQL file errors because the tables differ: mark that part UNVERIFIED |
| PA-10 | Scheduled actions | `tools/sql/03_cron_and_mail.sql`, scanner `XML-CRON-FIELDS` | no cron XML uses `numbercall`/`doall`; `failure_count` is 0 after a rehearsal (column exists on 18.0 and later) |
| PA-11 | Mail and neutralization of the rehearsal copy | `tools/sql/03_cron_and_mail.sql`; `odoo neutralize` on the **copy** | `database.is_neutralized` set, only the autovacuum cron active, only the dummy mail server active. Never on production |
| PA-12 | Reports and QWeb | scanner `T-RAW`/`T-ESC` rules; render each report on the target by hand | no `t-raw`/`t-esc` left; every custom report renders |
| PA-13 | Website view copies, themes, assets | last sections of `tools/sql/02_customizations.sql` | each website-specific view copy re-applied or dropped on purpose. Rendering in a browser: UNVERIFIED |
| PA-14 | Third-party, OCA and Enterprise modules | list from PA-01; check each repository branch, licence and last commit | every module has a source, a licence decision and an owner. Enterprise was not tested: UNVERIFIED |
| PA-15 | Platform requirements of the target | compare `psql`, Python and `wkhtmltopdf` versions with the target; grep `odoo.conf` for removed options | Python minimum 3.10, 3.10, 3.10, 3.12 and PostgreSQL minimum 12, 12, 13, 16 for 17.0 to 20.0 (official documentation, fetched 2026-11-11); `--longpolling-port` is gone from 18.0; the default `--http-interface` is `127.0.0.1` on 20.0 |
| PA-16 | JavaScript of custom modules | scanner `JS-*` rules, then the browser console on the upgraded copy | no unexplained finding and no module-loader error in the console. Run-time behaviour: UNVERIFIED |

## 4. Test gates used by the `test-case-generator` skill

| Gate | What the test shows |
|---|---|
| PA-04 | a database constraint is still enforced (19.0 skips old `_sql_constraints` with only a log warning) |
| PA-09 | access rights per role still hold |
| PA-12 | each custom report renders to non-empty HTML |
| FS-01 | quotation, confirm, invoice, post, payment: totals equal and journal items balance |
| FS-02 | purchase, receipt, vendor bill: stock rises by the received quantity |
| FS-03 | a stock move changes on-hand quantity as expected (a move written for 19.0 has no `name`; on 20.0 the unit field is `uom_id`) |
| FS-04, FS-05 | public pages and the portal answer HTTP 200 |
| FS-06, FS-07 | outgoing mail creates an e-mail notification; an inbound message creates a record (no real SMTP or mailbox) |
| FS-08 | a user limited to company A cannot read company B's record |
| FS-09 | portal and internal users get only the access they should |
| FS-10 | every active cron still has a model, a server action and an active user |
| PR-02 | `assertQueryCount` on a hot path stays at the bound measured on the source series |

A gate is PASS only with an evidence file from the run. "No findings" from the scanner never makes PA-06 or PA-16 pass.
