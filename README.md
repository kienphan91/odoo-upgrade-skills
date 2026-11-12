# Odoo upgrade audit and test generator (free sample)

Two [Agent Skills](#how-to-use-the-skills) and the scripts they need, for people who upgrade **Odoo Community** from
17.0 or 18.0 to 19.0:

| Skill | What it does |
|---|---|
| `skills/upgrade-audit` | Audits a **copy** of a database and your custom addons before an upgrade: installed modules and owners, modules missing on the target, deprecated or removed APIs and view patterns, database-only customizations, scheduled actions, security, platform requirements. Produces a gate report where every gate is PASS, FAIL, NOT RUN or UNVERIFIED. |
| `skills/test-case-generator` | Turns a custom addon into Odoo tests (`TransactionCase`/`HttpCase`) that run on both the source and the target series, so the same tests show what the upgrade changed. Includes a mutation check so a test that cannot fail is caught. |

Everything is plain text and the Python standard library. The scripts open no network connections, and every SQL file is a
`SELECT`.

## Safety rule

**Never run any of this against a production database.** Work on a restored copy. The SQL files are read-only
`SELECT`s and are meant to be run in a read-only session
(`export PGOPTIONS='-c default_transaction_read_only=on'`). That setting stops accidents, it is not a permission
system: a session can switch it off. Use a database role with only `SELECT` rights if you need a hard guarantee (not
tested here). Tests run on a throw-away scratch database, never on production.

## Folder map

```
skills/upgrade-audit/SKILL.md          the audit procedure (steps, checks, report format)
skills/test-case-generator/SKILL.md    the test-writing procedure
reference/upgrade-gates.md             version differences 17.0 to 20.0, the audit gates PA-01..PA-16, the test gates
tools/scan_custom_code.py              static scanner for custom addons (Python, XML, JS, manifests)
tools/modules_missing_in_target.py     installed modules that have no usable source on the target series
tools/module_summary.py                what an addon contains, to choose test cases
tools/sql/01..04_*.sql                 read-only inventory queries (modules, customizations, crons and mail, security)
examples/upgrade_test_pattern/         an Odoo addon with four portable test patterns
examples/legacy_demo/                  four small legacy addons to try the scanner on
```

## Quick start

```bash
# 1. scan custom code for a 19.0 target (no database needed)
python3 tools/scan_custom_code.py examples/legacy_demo --target 19.0
python3 tools/scan_custom_code.py /path/to/your/addons --target 19.0 --min-severity warn --format tsv > scan.tsv

# 2. inventory a COPY of your database (read-only session)
export PGOPTIONS='-c default_transaction_read_only=on'
psql -d my_copy -f tools/sql/01_env_and_modules.sql > audit-01-modules.txt

# 3. which installed modules have no source for the target series?
psql -d my_copy -Atc "select name from ir_module_module where state = 'installed' order by name" > installed.txt
python3 tools/modules_missing_in_target.py --installed installed.txt --addons /path/to/odoo-19.0/addons /path/to/your-addons-19.0 --series 19.0

# 4. what does an addon contain? (to pick test cases)
python3 tools/module_summary.py /path/to/your/addon
```

The scanner prints one line per finding (`file:line RULE [severity/gate] message`) and a summary. Severity: `error` the
source breaks the install or the feature on the target; `warn` still works but logs a deprecation or behaves differently
without failing; `review` can be a false positive, a person must look. Exit code 0 means nothing at or above
`--fail-on` (default `error`). A clean scan does **not** mean a module upgrades.

To run the example tests, put `examples/upgrade_test_pattern` on the addons path of a scratch database and run
`odoo -d scratch -i upgrade_test_pattern --test-enable --test-tags /upgrade_test_pattern --stop-after-init --log-level=test`;
the log should end with `0 failed, 0 error(s) of 4 tests`.

## How to use the skills

A skill here is a `SKILL.md` file: a YAML header (`name`, `description`) and numbered steps, each with the command and the
check that shows it worked. Give the file to your AI coding agent the way that tool loads skills or custom
instructions, or paste it into the prompt and point the agent at this folder (`KIT` in the steps means this folder).
The skills were **not** tested inside any specific agent product: UNVERIFIED. They are procedures; the scripts they
call were run (see below).

## What was verified

Checked on **Odoo Community** only, in throw-away containers from the official images `odoo:17.0`, `odoo:18.0`,
`odoo:19.0`, `odoo:20.0` with PostgreSQL 16, on demo data, on 2026-11-11 and 2026-11-12:

- `scan_custom_code.py` on 14 legacy fixture addons for each target 17.0 to 20.0, on Odoo's own 19.0 addons (2
  findings at `error`: 1 true, 1 false positive, a local function named `name_get` inside a core test) and on Odoo's own
  17.0 addons. It also runs on Python 3.10 and 3.12.
- Every version difference in `reference/upgrade-gates.md` is labelled **run**, **source** or **UNVERIFIED**.
- `modules_missing_in_target.py` on the module lists of 17.0, 18.0 and 19.0 demo databases against the 19.0 addons.
- The four SQL files on 17.0, 18.0, 19.0 and 20.0 demo databases in a read-only session: no error on 17.0 to 19.0;
  `04_security.sql` fails on 20.0 as documented (the tables it reads do not exist there).
- `examples/upgrade_test_pattern`: `0 failed, 0 error(s) of 4 tests` on 17.0, 18.0, 19.0 and 20.0; with the unique
  constraint dropped in a copy, the constraint test fails on all four, so it is not vacuous.

**Not verified:** anything in a web browser, Odoo Enterprise, Studio, third-party and OCA modules, a real upgrade,
production-size data, and the skills as end-to-end agent workflows. Images are rebuilt over time: re-run the scripts on
your own build. Odoo is a trademark of Odoo S.A.; this project is independent and not affiliated with or endorsed by it.

## Licence

MIT, see `LICENSE`.

## Want the whole upgrade?

This free sample is the audit and the tests. The paid kit adds the data reconciliation, the code-porting and the
go/no-go skills, snapshot and compare tools for before/after numbers, 46 gates with pass/fail rules and a smoke-test
addon, run against real 17.0, 18.0 and 19.0 containers (20.0 in part), with a verification record that lists what was not checked:
https://buy.polar.sh/polar_cl_EVsRo3MlFd7yJZXyzo89BYz9Q2QtRWS5GiND429rVdR
