#!/usr/bin/env python3
"""Read-only assertion runner for `audit.py`'s redaction backstop.

The create-then-verify shape borrowed from the origin repo's `*_verify.sh`
scripts: the thing that writes is never the thing that confirms. One line per
check (`PASS`/`FAIL  <name>  <detail>`), non-zero exit if any check fails.

Run this before trusting the backstop, and run it again after touching
`audit.py`. A redaction claim we print to a customer is executed, not reasoned
about.

    python3 scripts/verify_audit_redaction.py

Passing does NOT mean secrets cannot reach the log. It means these shapes are
caught. `mask()` is a backstop; masking before you call it is the mechanism.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import mask  # noqa: E402

# Real shapes, not lookalikes. The key id below is syntactically valid and
# belongs to nobody; the PEM body is filler of the right form.
PEM = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEowIBAAKCAQEAvQ9m2H0jK3xNQ0bZ7T1sW4pR8yFhL2cV6dXeA1uY3nKpM5qS\n"
    "8tB4rC7wZ0oI9lJ6hG2fD3aE5xN1vU7yT4kR6mP8sQ2wX0zB9cH3jL5nF7dK1gV4\n"
    "-----END RSA PRIVATE KEY-----"
)
AWS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
STS_KEY_ID = "ASIAY34FZKBOKMUTVV7A"

CHECKS = [
    ("pem-block", f"here is the key:\n{PEM}\nand that was it", "BEGIN RSA PRIVATE KEY"),
    ("aws-key-id", f"aws_access_key_id = {AWS_KEY_ID}", AWS_KEY_ID),
    ("aws-sts-key-id", f"using {STS_KEY_ID} for the call", STS_KEY_ID),
    ("password-kv", "psql 'host=db user=advisor password=hunter2correct' -c 'select 1'", "hunter2correct"),
    ("json-secret", '{"client_secret": "s3cr3t-value-here", "id": "public"}', "s3cr3t-value-here"),
    ("api-key-kv", "CATALOG_API_KEY=mc_live_9f2b71ac4d", "mc_live_9f2b71ac4d"),
    ("long-flag", "helm upgrade advisor --client-secret zzTOPsecret42 --wait", "zzTOPsecret42"),
]

# Things that must survive: over-masking hides the failure you are debugging.
KEEPS = [
    ("keeps-command", "aws iam create-access-key --user-name advisor", "create-access-key"),
    ("keeps-exit", "Error: UnauthorizedOperation: not authorized", "UnauthorizedOperation"),
    ("keeps-key-name", 'kubectl get secret -o jsonpath="{.data.CATALOG_API_KEY}"', "CATALOG_API_KEY"),
]


def main() -> int:
  failed = 0
  for name, raw, secret in CHECKS:
    out = mask(raw)
    ok = secret not in out
    print(f"{'PASS' if ok else 'FAIL'}  {name}  "
          f"{'redacted' if ok else 'SECRET SURVIVED: ' + out!r}")
    failed += not ok
  for name, raw, keep in KEEPS:
    out = mask(raw)
    ok = keep in out
    print(f"{'PASS' if ok else 'FAIL'}  {name}  "
          f"{'preserved' if ok else 'OVER-MASKED: ' + out!r}")
    failed += not ok
  print(f"\n{len(CHECKS) + len(KEEPS) - failed}/{len(CHECKS) + len(KEEPS)} checks passed")
  return 1 if failed else 0


if __name__ == "__main__":
  sys.exit(main())
