"""Append a redacted audit entry to the Advisor run log.

PORTED, not shared. The original is `scripts/init/lib/audit.py` in Multicloud's
private platform repo, where the /bootstrap skill uses it to keep a per-env
record of every command it runs. That repo is private, so this is a copy with
attribution rather than a submodule — the two can drift and only this one is
customer-facing.

WHAT IS VERBATIM: `mask()` and its four patterns, the entry format, the
greppable header tokens (`FAIL` / `ISSUE` / `SUGGESTION` / `DONE`), the 8000-char
output cap, and the 0600 file mode. Also the 2-space indentation, which is the
origin repo's rule and is kept so a diff against the original stays readable.

WHAT DIVERGED, and only this: WHERE THE LOG GOES. The bootstrap original writes
to `data/bootstrap/env/<env>/audit.log` inside its own git checkout. This log
lives on the CUSTOMER'S machine, is not in any repo, and never comes back to
Multicloud — we have no mechanism to read it and do not want one. So `--env`
became `--context` (recorded in the header, never used to build a path) and the
destination is chosen explicitly:

  1. `--log <path>`
  2. `$MULTICLOUD_ADVISOR_AUDIT_LOG`
  3. `./multicloud-advisor-audit.log` in the working directory

The agent picks a path in phase 1 and tells the human where it is. Whatever it
picks, say it out loud — the human owns this file.

Each command is appended by its own process as soon as it finishes, so the file
updates continuously — a SECOND session can `tail -f` it to follow a live run
and `grep -n FAIL` to jump to failures (the header carries an `ok`/`FAIL` token
next to the exit code).

Beyond commands, log the friction with `--note` (`--kind issue` for a
bug/blocker, `--kind suggestion` for an improvement). Those carry an `ISSUE` /
`SUGGESTION` header token, so the next session can
`grep -nE 'ISSUE|SUGGESTION'` to collect everything worth fixing.

At the end of each phase, log a completion marker with `--kind done` whose note
names the resources created or changed, with ids. These carry a `DONE` token, so
a resumed session can `grep -n 'DONE ===='` to reconstruct what is finished and
what it produced. "Done" on its own is not a marker.

REDACTION: two layers, and the first one is yours.
  1. YOU mask secret values before calling this, and pass `--redacted` for any
     command that mints or handles a secret (its output is then not recorded).
  2. As a BACKSTOP ONLY, this auto-masks common secret shapes (PEM blocks, AWS
     key ids, and values of secret-ish keys) in both the command string and the
     output, in case you missed one.
Do not treat layer 2 as the mechanism. It catches shapes it knows; a credential
in a shape it does not know reaches the file. The log is created 0600 as
defense-in-depth — treat it as sensitive regardless.

VERIFY INDEPENDENTLY. This is the create-then-verify shape the origin repo's
`*_verify.sh` scripts use: the thing that writes is never the thing that
confirms. After a phase, read the log back and check it says what you think it
says — `grep -n 'DONE ====' <log>` for what completed, `grep -n FAIL <log>` for
what did not. A completion marker you wrote is not evidence that the step
worked.

No third-party imports, so it runs before anything is installed.

Input:  optional captured output on stdin (ignored when --redacted).
Usage (command entry):
  some_cmd; rc=$?
  printf '%s' "$output" | python3 scripts/audit.py \\
    --context prod-eks --phase 2 --exit "$rc" --cmd 'kubectl create secret …' --redacted

Usage (issue / suggestion entry — no command):
  python3 scripts/audit.py --context prod-eks --phase 5 --kind issue \\
    --note 'preflight said PodSecurity was unset; admission rejected the DaemonSet anyway'

Usage (phase-completion marker — no command):
  python3 scripts/audit.py --context prod-eks --phase 2 --kind done \\
    --note 'secret advisor-catalog/advisor; helm release advisor rev 1 chart 0.5.0; port-forward 8080'
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
from pathlib import Path

DEFAULT_LOG = "multicloud-advisor-audit.log"
MAX_OUTPUT = 8000  # cap per-entry output to keep the log readable

_PEM = re.compile(r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", re.DOTALL)
_AKIA = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
# Secret-ish key names; reused for both the kv and flag patterns below.
_SECRET_KEY = (
    r"(?:secret|passwd|password|token|api[_-]?key|access[_-]?key|"
    r"client[_-]?secret|tunnel[_-]?secret|private[_-]?key|nextauth|hmac)"
)
# value following a secret-ish key in JSON ("k":"v") or kv (k=v)
_KV = re.compile(r"(?i)(\"?[\w.-]*" + _SECRET_KEY + r"[\w.-]*\"?\s*[:=]\s*\"?)([^\"\s,}&]+)")
# value following a secret-ish long CLI flag (--secret VALUE,
# --client-secret VALUE). Requires a real `--` flag at a word boundary so
# it can't latch onto an internal hyphen of a positional arg like
# `create-access-key`. Single-dash flags are left to the primary redactor.
_FLAG = re.compile(r"(?i)((?:^|\s)--[\w-]*" + _SECRET_KEY + r"[\w-]*\s+)(\S+)")


def mask(text: str) -> str:
  if not text:
    return text
  text = _PEM.sub("[REDACTED PEM BLOCK]", text)
  text = _AKIA.sub("[REDACTED-AWS-KEY-ID]", text)
  text = _KV.sub(r"\1[REDACTED]", text)
  text = _FLAG.sub(r"\1[REDACTED]", text)
  return text


def log_path(explicit: str | None) -> Path:
  # Explicit flag, then environment, then the working directory. Never derived
  # from a repo root: this file belongs to the customer, not to a checkout.
  if explicit:
    return Path(explicit).expanduser()
  from_env = os.environ.get("MULTICLOUD_ADVISOR_AUDIT_LOG")
  if from_env:
    return Path(from_env).expanduser()
  return Path.cwd() / DEFAULT_LOG


def main(argv: list[str] | None = None) -> int:
  p = argparse.ArgumentParser(description="Append a redacted Advisor audit entry.")
  p.add_argument("--context", default="",
                 help="The pinned kubeconfig context this entry belongs to.")
  p.add_argument("--log", help="Destination log file. Overrides "
                 "$MULTICLOUD_ADVISOR_AUDIT_LOG and the working-directory default.")
  p.add_argument("--cmd", help="The command that was run (command entries).")
  p.add_argument("--phase", default="", help="Phase label, e.g. 2, 4.aws.")
  p.add_argument("--exit", dest="code", default="", help="Exit code of the command.")
  p.add_argument("--redacted", action="store_true",
                 help="Command mints/handles a secret: do not log its output.")
  p.add_argument("--note", help="Log a free-text observation instead of a command: "
                 "an issue you hit or an improvement suggestion for the skill. "
                 "Pass '-' to read the note from stdin.")
  p.add_argument("--kind", choices=("issue", "suggestion", "note", "done"),
                 default="note",
                 help="Category for --note; written as a greppable header token "
                 "(issue=ISSUE, suggestion=SUGGESTION, done=DONE phase-complete "
                 "marker, note=NOTE).")
  args = p.parse_args(argv)
  if not args.cmd and args.note is None:
    p.error("pass --cmd (a command entry) or --note (an issue/suggestion entry)")

  ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
  phase = f" | phase {args.phase}" if args.phase else ""
  ctx = f" | context {args.context}" if args.context else ""

  if args.note is not None:
    # An observation, not a command: an issue the agent hit or a fix it
    # suggests. ISSUE / SUGGESTION are greppable so the following session can
    # collect everything worth changing in the skill.
    text = sys.stdin.read() if args.note == "-" else args.note
    if len(text) > MAX_OUTPUT:
      text = text[:MAX_OUTPUT] + "\n…[truncated]"
    kind_msg = args.kind.upper()
    note_body = ("\n".join("  " + ln for ln in mask(text).splitlines())
                 or "  (empty note)")
    entry = f"==== {ts}{ctx}{phase} | {kind_msg} ====\n{note_body}\n\n"
  else:
    raw_out = "" if args.redacted else sys.stdin.read()
    if len(raw_out) > MAX_OUTPUT:
      raw_out = raw_out[:MAX_OUTPUT] + "\n…[truncated]"
    # A greppable status token: a second session following the live run can
    # `grep -n FAIL <log>` to jump straight to every failed command.
    if args.code == "":
      code = ""
    else:
      code = f" | exit {args.code} {'ok' if args.code == '0' else 'FAIL'}"
    body = ("  [output redacted — single-shot secret]" if args.redacted
            else "\n".join("  " + ln for ln in mask(raw_out).splitlines())
            or "  (no output)")
    entry = f"==== {ts}{ctx}{phase}{code} ====\n  $ {mask(args.cmd)}\n{body}\n\n"
    kind_msg = "redacted" if args.redacted else ""

  target = log_path(args.log)
  target.parent.mkdir(parents=True, exist_ok=True)
  # Create 0600 if new; append otherwise.
  fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
  with os.fdopen(fd, "a", encoding="utf-8") as f:
    f.write(entry)
  print(f"audit: logged to {target}" + (f" [{kind_msg}]" if kind_msg else ""))
  return 0


if __name__ == "__main__":
  sys.exit(main())
