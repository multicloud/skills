#!/usr/bin/env python3
"""Check flows/*.json against the console contract (flow-contract v1).

  python3 scripts/check-flow-refs.py

Fails when a flow file or doors.json does not parse, a `refs` / `os_stage` entry
("<flow-basename>#<stage-id>") names no real stage, a `detect` id is not in the
contract list, or an `in[]` item has a bad shape.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DETECT = {"organization", "cloud_account", "pool_created", "pool_ready",
          "peering_created", "peering_ready", "cleanup", "quota_gpu"}
errs = []
stages = {}
for f in sorted(ROOT.glob("plugins/*/skills/*/flows/*.json")):
  try:
    d = json.loads(f.read_text())
  except ValueError as e:
    errs.append(f"{f.name}: {e}")
    continue
  if f.name == "doors.json":
    doors = d
    continue
  for st in d["stages"]:
    stages[f"{f.stem}#{st['id']}"] = st
    for s in st["steps"]:
      where = f"{f.stem}#{st['id']}:{s['id']}"
      if "detect" in s and s["detect"] not in DETECT:
        errs.append(f"{where}: unknown detect {s['detect']!r}")
      if "owner_only" in s and not isinstance(s["owner_only"], bool):
        errs.append(f"{where}: owner_only must be a boolean")
      for i in s.get("in", []):
        ok = isinstance(i, str) or (isinstance(i, dict) and isinstance(i.get("label"), str)
                                    and set(i) <= {"label", "secret", "placeholder"})
        if not ok:
          errs.append(f"{where}: bad in[] item {i!r}")
        elif isinstance(i, dict) and "placeholder" in i and i["placeholder"] not in s.get("c", ""):
          errs.append(f"{where}: placeholder {i['placeholder']!r} not in c")

try:
  doors
except NameError:
  sys.exit("doors.json not found")
for door in doors["doors"]:
  refs = list(door.get("os_stage", {}).values())
  for cs in door["stages"]:
    refs += cs["refs"]
    if not cs["refs"] and "skill" not in cs:
      errs.append(f"{door['id']}/{cs['id']}: empty refs need a skill")
  for r in refs:
    if r not in stages:
      errs.append(f"{door['id']}: ref {r!r} is not a stage")
  ids = [cs["id"] for cs in door["stages"]]
  if len(ids) != len(set(ids)):
    errs.append(f"{door['id']}: duplicate console stage ids")
for e in errs:
  print("FAIL ", e)
if not errs:
  print(f"OK    flows and doors.json: {len(stages)} stages, {len(doors['doors'])} doors")
sys.exit(1 if errs else 0)
