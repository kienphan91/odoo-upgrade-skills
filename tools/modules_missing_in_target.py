#!/usr/bin/env python3
"""Which installed modules have no usable source on the target addons path? (gate PA-02). Read only, standard library.

    modules_missing_in_target.py --installed installed.txt --addons DIR [DIR ...] [--series 19.0]

installed.txt: one module name per line (first CSV column is used). Make it from a COPY with:
    psql -d copy -Atc "select name from ir_module_module where state = 'installed' order by name" > installed.txt
--addons: the directories on the TARGET version's addons path (the core addons directory of the target Odoo, plus your
custom / OCA / third-party directories checked out at the target branch).
Status per module:
  FOUND          manifest present, installable
  MISSING        no folder with a __manifest__.py in any addons directory: renamed, merged, removed or not ported yet
  NOT-INSTALLABLE manifest says installable False
  WRONG-SERIES   manifest version has 4+ parts and starts with another series (18.0/19.0 skip such a module)
Exit code 0 = everything FOUND, 1 = anything else.
"""
import argparse
import ast
import os
import sys


def read_manifest(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return ast.literal_eval(handle.read())
    except (OSError, ValueError, SyntaxError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--installed", required=True)
    ap.add_argument("--addons", nargs="+", required=True)
    ap.add_argument("--series", help="target series, e.g. 19.0 (enables the WRONG-SERIES check)")
    args = ap.parse_args()
    names = [line.split(",")[0].strip() for line in open(args.installed, encoding="utf-8") if line.strip()]
    found = {}
    for root in args.addons:
        if not os.path.isdir(root):
            print("warning: not a directory: %s" % root, file=sys.stderr)
            continue
        for entry in os.listdir(root):
            manifest = os.path.join(root, entry, "__manifest__.py")
            if os.path.isfile(manifest) and entry not in found:
                found[entry] = manifest
    counts = {"FOUND": 0, "MISSING": 0, "NOT-INSTALLABLE": 0, "WRONG-SERIES": 0}
    for name in names:
        status, note = "FOUND", ""
        if name not in found:
            status = "MISSING"
        else:
            data = read_manifest(found[name])
            if data is None:
                status, note = "NOT-INSTALLABLE", "manifest unreadable"
            elif not data.get("installable", True):
                status = "NOT-INSTALLABLE"
            else:
                version = str(data.get("version", ""))
                parts = version.split(".")
                if args.series and len(parts) >= 4 and ".".join(parts[:2]) != args.series:
                    status, note = "WRONG-SERIES", "version " + version
        counts[status] += 1
        if status != "FOUND":
            print("%-16s %-45s %s" % (status, name, note))
    print("\n-- %d modules: %s" % (len(names), ", ".join("%d %s" % (v, k) for k, v in counts.items())), file=sys.stderr)
    return 0 if counts["FOUND"] == len(names) else 1


if __name__ == "__main__":
    sys.exit(main())
