#!/usr/bin/env python3
"""Render a customer PoC page from the flow files of the skills.

The steps of a PoC live in one place: `plugins/<skill>/skills/<skill>/flows/*.json`. The skills
read them at run time; this script builds the human page from the same files, so the page and
the skills cannot drift.

  python3 scripts/render-poc-page.py                 # write every poc/*.page.json output
  python3 scripts/render-poc-page.py --check         # exit 1 if a committed page is out of date

A page manifest (`poc/<name>.page.json`) lists stages in page order. An entry is either
"<skill>:<stage-id>" (the whole stage), or an object {t, note, dg, steps: ["<skill>:<stage>:<step>"]}
that composes one page stage from steps of several skills.

Step fields the page shows: h, who, d, in, c, os, g. `c_file` is inlined into `c` (path relative to
the skill folder). Fields only the agent reads (id, who_kind, c_agent, agent_note, ...) are dropped.
A step with "page": false is left out of the page.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE_KEYS = ("h", "who", "d", "in", "c", "os", "g")
MARK = "/*@@FLOW_DATA@@*/"


def load_flows():
  stages = {}
  for f in sorted(ROOT.glob("plugins/*/skills/*/flows/*.json")):
    data = json.loads(f.read_text())
    for st in data["stages"]:
      key = f"{data['skill']}:{st['id']}"
      if key in stages:
        sys.exit(f"duplicate stage {key} in {f}")
      stages[key] = (st, f.parent.parent)
  return stages


def page_step(step, skill_dir):
  out = {}
  for k in PAGE_KEYS:
    if k == "c" and "c_file" in step:
      out["c"] = (skill_dir / step["c_file"]).read_text().rstrip("\n")
    elif k in step:
      out[k] = step[k]
  return out


def stage_steps(st, skill_dir):
  return [page_step(s, skill_dir) for s in st["steps"] if s.get("page", True)]


def resolve(entry, stages):
  if isinstance(entry, str):
    st, d = stages[entry]
    out = {"t": st["t"], "note": st["note"]}
    if st.get("dg"):
      out["dg"] = st["dg"]
    out["steps"] = stage_steps(st, d)
    return out
  out = {"t": entry["t"], "note": entry["note"]}
  if entry.get("dg"):
    out["dg"] = entry["dg"]
  out["steps"] = []
  for ref in entry["steps"]:
    skill, sid, step_id = ref.split(":")
    st, d = stages[f"{skill}:{sid}"]
    step = next((s for s in st["steps"] if s["id"] == step_id), None)
    if step is None:
      sys.exit(f"unknown step {ref}")
    out["steps"].append(page_step(step, d))
  return out


def render(manifest_path, stages):
  m = json.loads(manifest_path.read_text())
  template = (ROOT / "poc" / "template.html").read_text()
  if template.count(MARK) != 1:
    sys.exit("template.html must hold the flow marker exactly once")
  a = [resolve(e, stages) for e in m["STAGES"]]
  b = [resolve(e, stages) for e in m["STAGES_B"]]
  js = ("const STAGES = " + json.dumps(a, ensure_ascii=False, indent=1) + ";\n"
        "const STAGES_B = " + json.dumps(b, ensure_ascii=False, indent=1) + ";\n")
  # A literal "</script" inside a command would end the script element early.
  js = js.replace("</", "<\\/")
  return ROOT / m["output"], template.replace(MARK, js)


def main():
  check = "--check" in sys.argv[1:]
  stages = load_flows()
  bad = 0
  for mf in sorted((ROOT / "poc").glob("*.page.json")):
    out, html = render(mf, stages)
    if check:
      if not out.exists() or out.read_text() != html:
        print(f"FAIL  {out.relative_to(ROOT)} is out of date: run python3 scripts/render-poc-page.py")
        bad = 1
      else:
        print(f"OK    {out.relative_to(ROOT)}")
    else:
      out.write_text(html)
      print(f"wrote {out.relative_to(ROOT)}")
  sys.exit(bad)


if __name__ == "__main__":
  main()
