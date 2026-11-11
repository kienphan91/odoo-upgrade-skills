---
name: test-case-generator
description: Generate and run Odoo upgrade test cases for a custom addon (TransactionCase/HttpCase) and link them to upgrade gates. Use for "write tests for odoo module upgrade", "regression tests before migrating", "smoke test odoo 19".
---

# test-case-generator

Turn a custom addon into a set of automated tests that run on **both** the source and the target series, so the same
tests show what the upgrade changed. Gates: FS-01..FS-10, PA-04, PA-09, PR-02 (short definitions in `reference/upgrade-gates.md`, section 4).
The pattern file is `examples/upgrade_test_pattern/tests/test_pattern.py` (version-neutral helpers, visible skips).

## Safety rule (read first)

Never run destructive commands against a production database. Tests run on a **throw-away scratch database** only
(restored copy or fresh `-i`), never on production. Tests must roll back (use `TransactionCase`/`HttpCase`, never
`cr.commit()`), and must not send real mail or call external services.

## Inputs

`ADDON` path, `SERIES` to run on, `KIT` (the folder that contains `tools/` and `examples/`), scratch database name, a way to run Odoo for that series.

## Steps

1. **Inventory the addon.** `python3 "$KIT/tools/module_summary.py" "$ADDON"`
   Check: it lists models, ACL rows, crons, routes, reports and existing tests. Write the list of features to cover.
2. **Choose cases from the inventory** (one row per feature; keep the gate id in the docstring):

   | Feature found | Test to write | Gate |
   |---|---|---|
   | Model with `@api.constrains` or a unique constraint | create a valid record; create an invalid one inside `with self.assertRaises(...)` (for SQL constraints use `psycopg2.IntegrityError` inside `self.cr.savepoint()` with `mute_logger('odoo.sql_db')`, see `test_unique_constraint_is_enforced` in the pattern file); this is the only reliable detector of 19.0 silently dropping `_sql_constraints` | PA-04 |
   | Computed / stored field | create, change a dependency, assert the value | FS |
   | `create`/`write` overrides | assert the side effect | FS |
   | ACL rows / groups / record rules | for each role (internal, portal, your custom group) assert `has_access`/`check_access_rights` per operation and a record-rule read of another company's record | FS-08, FS-09 |
   | Workflow buttons / state changes | drive the whole state chain with real data | FS-01..FS-03 |
   | Cron records | assert the cron's model, server action and user resolve (do not run it: crons commit) | FS-10 |
   | Reports (`ir.actions.report`) | `env['ir.actions.report']._render_qweb_html(report_name, record.ids)` returns non-empty HTML | PA-12 |
   | Controllers (`@http.route`) | `HttpCase.url_open(path)`, assert status and a text marker | FS-04, FS-05 |
   | Mail templates / alias | post a message and assert a `mail.notification` of type email; route a raw message with `mail.thread.message_process` | FS-06, FS-07 |
   | Heavy screens or loops | `with self.assertQueryCount(__system__=<measured>)` around the call | PR-02 |

3. **Write the tests in `<ADDON>/tests/`** (add `from . import test_upgrade_cases` to `tests/__init__.py`), tagged
   `@tagged('post_install', '-at_install', '<addon>_upgrade')`. Rules that keep them portable across series:
   - Do not hard-code field names that changed: use the helpers `_group_field(env)` (`group_ids` vs `groups_id`),
     `'is_storable' in env['product.template']._fields`, `'uom_id' in env['stock.move']._fields` as in the pattern file.
   - Compare against computed totals of the same run (invoice vs order), not against literal numbers that depend on demo data.
   - Skip visibly with `self.skipTest('<module> not installed')`; never let a missing module pass silently.
   - Create all data inside the test; reference no demo-data ids.
4. **Run on the source series first, then on the target series**, each on its own scratch database that has the addon's
   dependencies installed:
   `odoo -d <scratch> -i <addon> --test-enable --test-tags /<addon> --stop-after-init --log-level=test > tests-<series>.log 2>&1`
   Check: `grep tests.result tests-<series>.log` -> `0 failed, 0 error(s) of N tests` with N equal to the number of tests you
   wrote (a lower N means a test did not load). Failures on the **source** series are bugs in the test: fix them first.
   Failures only on the target are the findings; each maps to a row of the version table in `reference/upgrade-gates.md`.
5. **Prove the tests can fail (mutation check).** For three tests (always the constraint test), break the covered code line
   in the scratch copy of the addon, re-run, confirm the test fails, restore the line. Record the three results.
6. **Report.** `tests-report.md`: table of test name, gate id, result on source, result on target, mutation result. A gate
   that has no test or whose test was only run on one series is NOT PASS.

## Do not

- Do not assert only that "no exception was raised". Do not use `sudo()` to get around an access check you are testing.
- Do not generate tests that call real SMTP, payment providers or external APIs. Mark those cases manual in the report.
