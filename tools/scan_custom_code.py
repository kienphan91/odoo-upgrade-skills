#!/usr/bin/env python3
"""Static scanner for custom Odoo addons (Odoo Upgrade Test Kit, free sample; gates PA-03, PA-04, PA-05, PA-09, PA-10, PA-12, PA-16 of reference/upgrade-gates.md).

Reads source files only. It never imports your addons, never opens a database and never writes anything.
Pure Python 3 standard library (run with Python 3.10 and 3.12; older versions were not tried).

    scan_custom_code.py PATH [PATH ...] --target 19.0 [--min-severity warn] [--format text|tsv|json]

PATH is an addons directory (containing addon folders) or a single addon folder.
--target is the series you are upgrading to. A rule is reported only if it starts to matter at or before the
target series (a rule with since=18.0 is not reported for --target 17.0).

Severity:
  error   the source breaks the install/update or the feature on the target series (checked on the official images, see reference/upgrade-gates.md for the status of each claim)
  warn    still works on the target but logs a deprecation, or silently behaves differently
  review  can be a false positive: a person must look at the line

Exit code: 0 = no finding at or above --fail-on (default: error), 1 = findings, 2 = bad usage.
A clean scan does NOT mean the module upgrades. It only means none of these known patterns were found.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

SEV_ORDER = {"info": 0, "review": 1, "warn": 2, "error": 3}

# Each rule: id, gate, since (series where it starts to matter), file kind, regex, severity, message.
# kind: py | xml | js | manifest.  "block" rules match across lines (re.S).
RULES = [
    # ---- XML views and data
    dict(id="XML-ATTRS", gate="PA-05", since=17.0, kind="xml", sev="error",
         rx=r"""\sattrs\s*=\s*["']""",
         msg="`attrs` attribute: rejected by view validation since 17.0. Use invisible=/readonly=/required= with Python expressions."),
    dict(id="XML-STATES", gate="PA-05", since=17.0, kind="xml", sev="error",
         rx=r"""<(?:button|field|header)\b[^>]*\sstates\s*=\s*["']""",
         msg="`states` attribute: rejected by view validation since 17.0. Use invisible=\"state not in (...)\"."),
    dict(id="XML-TREE-TAG", gate="PA-05", since=18.0, kind="xml", sev="error",
         rx=r"""<tree[\s>/]""",
         msg="<tree> root: the list view type is called `list` since 18.0."),
    dict(id="XML-VIEWMODE-TREE", gate="PA-05", since=18.0, kind="xml", sev="warn",
         rx=r"""name=["']view_mode["'][^>]*>[^<]*\btree\b""",
         msg="view_mode contains `tree`: the list view type is `list` since 18.0 (not rejected at install, client behaviour UNVERIFIED). Also check `tree_view_ref` context keys and xpath //tree."),
    dict(id="XML-KANBAN-BOX", gate="PA-05", since=18.0, kind="xml", sev="warn", sev_at={19.0: "error"},
         rx=r"""t-name=["']kanban-box["']""",
         msg="kanban `kanban-box` template: 18.0 logs a deprecation warning; the 19.0 and 20.0 web sources throw `Missing 'card' template.` when no `card` template exists (read in the source, not run in a browser). Use a `card` template."),
    dict(id="XML-T-RAW", gate="PA-12", since=17.0, kind="xml", sev="warn", sev_at={20.0: "error"},
         rx=r"""\st-raw\s*=""",
         msg="`t-raw` is documented as deprecated and renders EMPTY on 20.0 (checked). Use `t-out`; t-raw never escaped, t-out escapes plain str, so pass Markup where you mean HTML."),
    dict(id="XML-T-ESC", gate="PA-12", since=20.0, kind="xml", sev="error",
         rx=r"""\st-esc\s*=""",
         msg="`t-esc` renders EMPTY on 20.0 (checked on odoo:20.0): use `t-out`."),
    dict(id="XML-CRON-FIELDS", gate="PA-10", since=18.0, kind="xml", sev="error",
         rx=r"""<field\s+name=["'](?:numbercall|doall)["']""",
         msg="ir.cron `numbercall`/`doall`: fields removed in 18.0, the record fails to load."),
    dict(id="XML-GROUPS-ID", gate="PA-09", since=19.0, kind="xml", sev="error",
         rx=r"""<field\s+name=["']groups_id["']""",
         msg="`groups_id` renamed `group_ids` in 19.0 on res.users, ir.ui.view, ir.ui.menu, ir.actions.act_window/server/report."),
    dict(id="XML-GROUP-USERS", gate="PA-09", since=19.0, kind="xml", sev="error",
         rx=r"""<record[^>]*model=["']res\.groups["'][^>]*>(?:(?!</record>).)*?<field\s+name=["'](?:users|category_id)["']""",
         msg="res.groups `users` is `user_ids` and `category_id` is `privilege_id` in 19.0.", block=True),
    dict(id="XML-SEARCH-GROUP-EXPAND", gate="PA-05", since=19.0, kind="xml", sev="review",
         rx=r"""<group[^>]*\sexpand\s*=""",
         msg="`expand` on <group> in a search view: not accepted by 19.0 validation."),
    dict(id="XML-MOBILE", gate="PA-04", since=19.0, kind="xml", sev="review",
         rx=r"""<field\s+name=["']mobile["']""",
         msg="`mobile` field: removed from res.partner in 19.0 (other models may keep their own)."),
    dict(id="XML-DETAILED-TYPE", gate="PA-04", since=18.0, kind="xml", sev="error",
         rx=r"""name=["']detailed_type["']""",
         msg="product `detailed_type` removed in 18.0: use type (consu/service/combo) + is_storable."),
    # ---- Python
    dict(id="PY-NAME-GET", gate="PA-04", since=18.0, kind="py", sev="error",
         rx=r"""\bdef\s+name_get\s*\(|\.name_get\s*\(""",
         msg="name_get() is deprecated in 17.0 and gone in 18.0 (a call raises AttributeError; an override never fed display_name). Override _compute_display_name."),
    dict(id="PY-NAME-SEARCH", gate="PA-04", since=18.0, kind="py", sev="error",
         rx=r"""\bdef\s+_name_search\s*\(""",
         msg="_name_search override is not called by name_search() from 18.0. Override _search_display_name(operator, value)."),
    dict(id="PY-ACCESS-RIGHTS-UID", gate="PA-04", since=18.0, kind="py", sev="error",
         rx=r"""\baccess_rights_uid\b""",
         msg="`access_rights_uid` parameter of _search() removed in 18.0."),
    dict(id="PY-CHECK-ACCESS", gate="PA-04", since=18.0, kind="py", sev="warn", sev_at={20.0: "error"},
         rx=r"""\.(?:check_access_rights|check_access_rule|_filter_access_rules)\s*\(""",
         msg="Deprecated since 18.0, no longer defined in 20.0: use check_access()/has_access()/_filtered_access()."),
    dict(id="PY-READ-GROUP", gate="PA-04", since=19.0, kind="py", sev="warn",
         rx=r"""\.read_group\s*\(""",
         msg="read_group() is documented as deprecated in 19.0; use _read_group() (tuples) or formatted_read_group() (dicts)."),
    dict(id="PY-SQL-CONSTRAINTS", gate="PA-04", since=19.0, kind="py", sev="error",
         rx=r"""^\s*_sql_constraints\s*=""",
         msg="_sql_constraints is ignored in 19.0 (warning only): the constraint is NOT created. Use models.Constraint / models.Index.",
         flags=re.M),
    dict(id="PY-CR-UID-CONTEXT", gate="PA-04", since=19.0, kind="py", sev="warn",
         rx=r"""\._(?:cr|uid|context)\b""",
         msg="Model._cr/_uid/_context deprecated in 19.0: use self.env.cr / .uid / .context."),
    dict(id="PY-EXPRESSION", gate="PA-04", since=19.0, kind="py", sev="warn", sev_at={20.0: "error"},
         rx=r"""from\s+odoo\.osv\s+import\s+expression|from\s+odoo\.osv\.expression\s+import|\bexpression\.(?:AND|OR|normalize_domain|is_false|distribute_not)\b""",
         msg="odoo.osv.expression helpers emit DeprecationWarning in 19.0 and the odoo.osv package is gone in 20.0 (ModuleNotFoundError): use odoo.fields.Domain."),
    dict(id="PY-ROUTE-JSON", gate="PA-04", since=19.0, kind="py", sev="warn",
         rx=r"""type\s*=\s*['"]json['"]""",
         msg="@route(type='json') is a deprecated alias of type='jsonrpc' in 19.0."),
    dict(id="PY-GROUPS-ID", gate="PA-09", since=19.0, kind="py", sev="error",
         rx=r"""\.groups_id\b|['"]groups_id['"]""",
         msg="`groups_id` is `group_ids` in 19.0 on res.users / views / menus / actions. Check which model this line touches."),
    dict(id="PY-GROUP-USERS", gate="PA-09", since=19.0, kind="py", sev="review",
         rx=r"""\.category_id\b.*group|group.*\.users\b""",
         msg="res.groups: `users` is `user_ids`, `category_id` is `privilege_id` in 19.0 (false positives likely)."),
    dict(id="PY-PARTNER-MOBILE", gate="PA-04", since=19.0, kind="py", sev="review",
         rx=r"""\.mobile\b|['"]mobile['"]""",
         msg="res.partner `mobile` removed in 19.0 (other models, e.g. hr.employee, keep their own phone fields)."),
    dict(id="PY-DETAILED-TYPE", gate="PA-04", since=18.0, kind="py", sev="error",
         rx=r"""detailed_type""",
         msg="product `detailed_type` removed in 18.0: type is consu/service/combo, stock tracking is is_storable."),
    dict(id="PY-PRODUCT-TYPE-VALUE", gate="PA-04", since=18.0, kind="py", sev="review",
         rx=r"""\btype['"]?\s*(?:==|=|:|,)\s*['"]product['"]|\(['"]type['"]\s*,\s*['"](?:=|in)['"]\s*,\s*\[?['"]product['"]""",
         msg="type 'product' no longer exists on product.template from 18.0 (type is consu/service/combo; false positive if this is another model's `type`)."),
    dict(id="PY-STOCK-SVL", gate="DM-07", since=19.0, kind="py", sev="review",
         rx=r"""stock\.valuation\.layer""",
         msg="stock.valuation.layer: no model of that name in 19.0 stock_account (valuation reworked)."),
    # ---- JavaScript
    dict(id="JS-ODOO-DEFINE", gate="PA-16", since=18.0, kind="js", sev="review",
         rx=r"""\bodoo\.define\s*\(""",
         msg="Legacy odoo.define module: rewrite as an ES module (UNVERIFIED which legacy require() paths still resolve per series)."),
    dict(id="JS-LEGACY-REQUIRE", gate="PA-16", since=18.0, kind="js", sev="review",
         rx=r"""require\(\s*['"]web\.""",
         msg="require('web.*'): legacy module path, check it still exists in the target series."),
]

SKIP_DIRS = {".git", "node_modules", "__pycache__", "i18n", "i18n_extra"}
EXT_KIND = {".py": "py", ".xml": "xml", ".js": "js"}


def parse_series(text):
    m = re.match(r"^\s*(\d+)(?:\.(\d+))?", text)
    if not m:
        raise argparse.ArgumentTypeError("series like 19.0 expected")
    return float("%s.%s" % (m.group(1), m.group(2) or 0))


def iter_files(paths):
    for root_path in paths:
        if os.path.isfile(root_path):
            yield root_path
            continue
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not (d == "lib" and "static" in root.split(os.sep))]
            for name in files:
                yield os.path.join(root, name)


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def scan_manifest(path, text, target):
    out = []
    tgt = "%d.0" % int(target)
    m = re.search(r"""['"]version['"]\s*:\s*['"]([^'"]+)['"]""", text)
    if m:
        ver = m.group(1)
        head = re.match(r"^(\d+)\.(\d+)\.\d+", ver)
        # x.y.z.. with 5 parts is a full series version; 3 parts "1.0.0" is a short version.
        if head and len(ver.split(".")) >= 4 and "%s.%s" % (head.group(1), head.group(2)) != tgt:
            out.append(("MANIFEST-VERSION-SERIES", "PA-03", "error", line_of(text, m.start()),
                        "manifest version %r does not start with the target series %s: 18.0/19.0 skip the module (\"invalid module names, ignored\" / \"incompatible version, setting installable=False\") while the command still exits 0; 18.0 also aborts new-database creation (see reference/upgrade-gates.md)." % (ver, tgt)))
    if not re.search(r"""['"]license['"]\s*:""", text):
        out.append(("MANIFEST-LICENSE", "PA-03", "warn", 1, "no `license` key: Odoo logs a warning and assumes LGPL-3."))
    if not re.search(r"""['"]author['"]\s*:""", text):
        out.append(("MANIFEST-AUTHOR", "PA-03", "warn", 1, "no `author` key (19.0 logs a warning and derives it)."))
    if re.search(r"""['"]qweb['"]\s*:""", text):
        out.append(("MANIFEST-QWEB-KEY", "PA-03", "warn", 1, "`qweb` manifest key: templates belong in `assets` (UNVERIFIED: how each series treats the key)."))
    return out


def scan_file(path, target):
    ext = os.path.splitext(path)[1]
    name = os.path.basename(path)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return []
    findings = []
    if name == "__manifest__.py":
        findings += [(r, g, s, ln, m) for (r, g, s, ln, m) in scan_manifest(path, text, target)]
    if name == "ir.model.access.csv" and target >= 20.0:
        findings.append(("FILE-ACL-CSV", "PA-09", "error", 1,
                         "20.0 loads access rights from security/ir.access.csv (columns id,name,model_id,group_id/id,operation,domain); "
                         "ir.model.access.csv fails with KeyError: 'ir.model.access' (checked). Odoo's own upgrade_code converts the file: run it on a copy of your code, with a scratch copy of Odoo's core `base` addon on --addons-path."))
    kind = EXT_KIND.get(ext)
    if not kind:
        return [(path,) + f for f in findings]
    if kind == "xml" and "/static/" in path.replace(os.sep, "/"):
        return [(path,) + f for f in findings]  # OWL/QWeb client templates are not backend views (attrs= is a component prop there)
    for rule in RULES:
        if rule["kind"] != kind or rule["since"] > target:
            continue
        flags = rule.get("flags", 0) | (re.S if rule.get("block") else 0)
        for m in re.finditer(rule["rx"], text, flags):
            sev = rule["sev"]
            for series, forced in sorted(rule.get("sev_at", {}).items()):
                if target >= series:
                    sev = forced
            findings.append((rule["id"], rule["gate"], sev, line_of(text, m.start()), rule["msg"]))
    if kind == "js" and target >= 18.0 and "/static/src/" in path.replace(os.sep, "/"):
        if "@odoo-module" not in text and not re.search(r"^\s*(?:import|export)\s", text, re.M):
            findings.append(("JS-PLAIN-SCRIPT", "PA-16", "review", 1,
                             "plain script under static/src without import/export or @odoo-module header: 18.0+ transpiles every file under static/src as an ES module unless it says `@odoo-module ignore`."))
    return [(path,) + f for f in findings]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--target", type=parse_series, required=True, help="series you upgrade to, e.g. 19.0")
    ap.add_argument("--min-severity", choices=list(SEV_ORDER), default="review")
    ap.add_argument("--fail-on", choices=list(SEV_ORDER), default="error")
    ap.add_argument("--format", choices=["text", "tsv", "json"], default="text")
    args = ap.parse_args(argv)
    for p in args.paths:
        if not os.path.exists(p):
            print("no such path: %s" % p, file=sys.stderr)
            return 2
    results = []
    for path in iter_files(args.paths):
        for f in scan_file(path, args.target):
            if SEV_ORDER[f[3]] >= SEV_ORDER[args.min_severity]:
                results.append(f)
    results.sort(key=lambda f: (f[0], f[4], f[1]))
    if args.format == "json":
        print(json.dumps([dict(file=f[0], rule=f[1], gate=f[2], severity=f[3], line=f[4], message=f[5]) for f in results], indent=1))
    elif args.format == "tsv":
        print("file\tline\trule\tgate\tseverity\tmessage")
        for f in results:
            print("%s\t%d\t%s\t%s\t%s\t%s" % (f[0], f[4], f[1], f[2], f[3], f[5]))
    else:
        for f in results:
            print("%s:%d: %s [%s/%s] %s" % (f[0], f[4], f[1], f[3], f[2], f[5]))
        by_rule = Counter((f[1], f[3]) for f in results)
        print("\n-- summary (target %.1f): %d finding(s)" % (args.target, len(results)), file=sys.stderr)
        for (rule, sev), n in sorted(by_rule.items(), key=lambda kv: (-SEV_ORDER[kv[0][1]], kv[0][0])):
            print("   %-24s %-7s %d" % (rule, sev, n), file=sys.stderr)
    worst = max([SEV_ORDER[f[3]] for f in results] or [-1])
    return 1 if worst >= SEV_ORDER[args.fail_on] else 0


if __name__ == "__main__":
    sys.exit(main())
