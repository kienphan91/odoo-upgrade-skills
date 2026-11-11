#!/usr/bin/env python3
"""Summarise what an Odoo addon contains, to decide which test cases it needs (used by the test-case-generator skill).
Read only, standard library, regex based: it does not import the addon.

    module_summary.py ADDON_DIR [ADDON_DIR ...] [--json]

For each addon prints: manifest facts, models (_name / _inherit with the file), number of fields, methods that matter for
tests (constraints, onchange, compute, cron targets), views and actions in XML, ACL rows, groups, record rules, cron
records, report records, controller routes, JS files, existing test files. Counts are approximate (regex), use them as a
checklist, not as a proof.
"""
import argparse
import ast
import json
import os
import re
import sys


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def summarise(addon):
    name = os.path.basename(os.path.normpath(addon))
    manifest = {}
    try:
        manifest = ast.literal_eval(read(os.path.join(addon, "__manifest__.py")) or "{}")
    except (ValueError, SyntaxError):
        pass
    out = {"addon": name, "version": manifest.get("version"), "depends": manifest.get("depends", []),
           "models": [], "views": [], "actions": [], "menus": 0, "acl_rows": [], "groups": [], "record_rules": [],
           "crons": [], "reports": [], "routes": [], "js_files": [], "tests": [], "methods": {"constrains": 0, "onchange": 0, "compute": 0, "depends": 0, "create_override": 0, "write_override": 0, "unlink_override": 0}}
    for root, dirs, files in os.walk(addon):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules", "i18n")]
        rel_root = os.path.relpath(root, addon)
        for fname in files:
            path = os.path.join(root, fname)
            rel = os.path.normpath(os.path.join(rel_root, fname))
            text = None
            if fname.endswith(".py") and fname != "__manifest__.py":
                text = read(path)
                if rel.startswith("tests"):
                    out["tests"].append(rel)
                    continue
                for m in re.finditer(r"^\s*_name\s*=\s*['\"]([\w.]+)['\"]", text, re.M):
                    fields = len(re.findall(r"^\s{4}\w+\s*=\s*fields\.\w+", text, re.M))
                    out["models"].append({"model": m.group(1), "file": rel, "fields_in_file": fields})
                for m in re.finditer(r"^\s*_inherit\s*=\s*\[?\s*['\"]([\w.]+)['\"]", text, re.M):
                    if not re.search(r"^\s*_name\s*=", text, re.M):
                        out["models"].append({"model": m.group(1) + " (extended)", "file": rel, "fields_in_file": len(re.findall(r"^\s{4}\w+\s*=\s*fields\.\w+", text, re.M))})
                out["methods"]["constrains"] += len(re.findall(r"@api\.constrains", text))
                out["methods"]["onchange"] += len(re.findall(r"@api\.onchange", text))
                out["methods"]["depends"] += len(re.findall(r"@api\.depends", text))
                out["methods"]["compute"] += len(re.findall(r"compute\s*=", text))
                out["methods"]["create_override"] += len(re.findall(r"def create\(", text))
                out["methods"]["write_override"] += len(re.findall(r"def write\(", text))
                out["methods"]["unlink_override"] += len(re.findall(r"def unlink\(", text))
                for m in re.finditer(r"@http\.route\(\s*([^)]*)\)", text, re.S):
                    out["routes"].append({"file": rel, "route": re.sub(r"\s+", " ", m.group(1))[:100]})
            elif fname.endswith(".xml") and "static" not in rel.split(os.sep):
                text = read(path)
                for m in re.finditer(r"<record\s+id=[\"']([\w.]+)[\"']\s+model=[\"']([\w.]+)[\"']", text):
                    rec_id, model = m.groups()
                    if model == "ir.ui.view":
                        out["views"].append({"id": rec_id, "file": rel})
                    elif model in ("ir.actions.act_window", "ir.actions.server", "ir.actions.client"):
                        out["actions"].append({"id": rec_id, "model": model})
                    elif model == "ir.cron":
                        out["crons"].append(rec_id)
                    elif model == "ir.actions.report":
                        out["reports"].append(rec_id)
                    elif model == "res.groups":
                        out["groups"].append(rec_id)
                    elif model == "ir.rule":
                        out["record_rules"].append(rec_id)
                out["menus"] += len(re.findall(r"<menuitem\b", text))
                for m in re.finditer(r"<template\s+id=[\"']([\w.]+)[\"']", text):
                    out["views"].append({"id": m.group(1), "file": rel, "kind": "qweb template"})
            elif fname in ("ir.model.access.csv", "ir.access.csv"):
                rows = [r for r in read(path).splitlines()[1:] if r.strip()]
                out["acl_rows"] = [r.split(",")[0] + " -> " + (r.split(",")[1] if "," in r else "") for r in rows]
            elif fname.endswith(".js") and "static" in rel.split(os.sep):
                out["js_files"].append(rel)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("addons", nargs="+")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    results = []
    for addon in args.addons:
        if not os.path.isfile(os.path.join(addon, "__manifest__.py")):
            print("not an addon (no __manifest__.py): %s" % addon, file=sys.stderr)
            return 2
        results.append(summarise(addon))
    if args.json:
        print(json.dumps(results, indent=1))
        return 0
    for r in results:
        print("== %s  version=%s  depends=%s" % (r["addon"], r["version"], ", ".join(r["depends"])))
        for m in r["models"]:
            print("   model      %-40s %s (%d field lines)" % (m["model"], m["file"], m["fields_in_file"]))
        print("   methods    " + ", ".join("%s=%d" % kv for kv in r["methods"].items()))
        print("   views      %d, actions %d, menus %d, templates/reports %s" % (len(r["views"]), len(r["actions"]), r["menus"], len(r["reports"])))
        print("   security   %d ACL rows, %d groups, %d record rules" % (len(r["acl_rows"]), len(r["groups"]), len(r["record_rules"])))
        print("   crons      %s" % (", ".join(r["crons"]) or "none"))
        print("   routes     %s" % (", ".join(x["route"] for x in r["routes"]) or "none"))
        print("   js files   %d" % len(r["js_files"]))
        print("   tests      %s" % (", ".join(r["tests"]) or "NONE"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
