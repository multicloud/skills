#!/usr/bin/env python3
"""Routing eval: with all Multicloud skills visible at once, which one does the agent pick?

Puts every skill of this repo (name + description) into a scratch project's .claude/commands/,
runs each query of trigger-queries.json through `claude -p`, and records the first skill the model
invokes. Detection follows skill-creator's run_eval.py (first Skill tool_use in the stream).

  python3 evals/onboarding/route_eval.py --project /tmp/x --runs 2 --model claude-opus-5-5

Claude Code only (it drives `claude -p`). It checks trigger routing, not the skills' behaviour.
"""
import argparse, json, os, pathlib, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[2]


def install(project: pathlib.Path):
  cmds = project / ".claude" / "commands"
  cmds.mkdir(parents=True, exist_ok=True)
  names = []
  for sk in sorted(ROOT.glob("plugins/*/skills/*/SKILL.md")):
    text = sk.read_text()
    m = re.search(r"^name: (.+)$", text, re.M)
    d = re.search(r"^description: (.+)$", text, re.M)
    name, desc = m.group(1).strip(), d.group(1).strip()
    (cmds / f"{name}.md").write_text(f"---\ndescription: |\n  {desc}\n---\n\n# {name}\n\nRead {sk} and follow it.\n")
    names.append(name)
  return names


def first_skill(query, project, model, timeout):
  cmd = ["claude", "-p", query, "--output-format", "stream-json", "--verbose"]
  if model:
    cmd += ["--model", model]
  env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
  p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=project, env=env, text=True)
  try:
    for line in p.stdout:
      try:
        ev = json.loads(line)
      except ValueError:
        continue
      if ev.get("type") == "assistant":
        for c in ev.get("message", {}).get("content", []):
          if c.get("type") == "tool_use":
            if c.get("name") == "Skill":
              return c.get("input", {}).get("skill", "?")
            if c.get("name") == "Read" and "SKILL.md" in c.get("input", {}).get("file_path", ""):
              return "read:" + c["input"]["file_path"].split("/")[-2]
            return "tool:" + c.get("name", "?")
      if ev.get("type") == "result":
        return "none"
  finally:
    if p.poll() is None:
      p.kill(); p.wait()
  return "none"


def norm(picked):
  s = picked.split(":")[-1]
  return s if s.startswith("multicloud-") else "none"


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--project", required=True)
  ap.add_argument("--runs", type=int, default=2)
  ap.add_argument("--model", default=None)
  ap.add_argument("--timeout", type=int, default=90)
  ap.add_argument("--workers", type=int, default=6)
  ap.add_argument("--out", default=str(ROOT / "evals/onboarding/route-results.json"))
  a = ap.parse_args()
  project = pathlib.Path(a.project)
  names = install(project)
  qs = json.loads((ROOT / "evals/onboarding/trigger-queries.json").read_text())
  jobs = [(i, r) for i in range(len(qs)) for r in range(a.runs)]
  with ThreadPoolExecutor(a.workers) as ex:
    picks = list(ex.map(lambda j: first_skill(qs[j[0]]["query"], project, a.model, a.timeout), jobs))
  rows = []
  for i, q in enumerate(qs):
    got = [picks[k] for k, (qi, _) in enumerate(jobs) if qi == i]
    ok = sum(norm(g) == q["skill"] for g in got)
    rows.append({"expected": q["skill"], "query": q["query"], "picked": got, "correct": ok, "runs": len(got)})
  total = sum(r["correct"] for r in rows); n = sum(r["runs"] for r in rows)
  json.dump({"skills": names, "model": a.model, "score": f"{total}/{n}", "rows": rows}, open(a.out, "w"), indent=1)
  print(f"score {total}/{n}")
  for r in rows:
    if r["correct"] < r["runs"]:
      print(f"MISS expected={r['expected']} picked={r['picked']} :: {r['query'][:80]}")


if __name__ == "__main__":
  main()
