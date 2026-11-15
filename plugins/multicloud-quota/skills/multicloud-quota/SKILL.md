---
name: multicloud-quota
description: Use when someone needs more AWS quota for Multicloud work: a verify showed "quota LOW", a pool or GPU workload will not start for lack of vCPU quota, they ask what quota to request, in which regions, or in which order, or they want to file AWS quota increase requests for a connected AWS account.
---

# Plan and request AWS quota

Multicloud runs machines in the customer's own AWS account, and AWS caps how many vCPUs that
account may use. `verify` only reads quotas and files nothing. **You** plan the requests with the
customer, then file the ones they approve. The goal is the smallest list of requests that lets
their first workload run.

This file packages **no** quota code, region list, limit or request cap. The tools serve them live.
If anything here or in your memory disagrees with a tool answer, the tool wins.

## Rules that do not bend

1. **Ask before every filing.** Show the quota, the current limit, the new limit, the region and
   the open-request count. File only after a clear yes. A yes covers the items shown.
2. **Smallest request that works.** AWS often denies large requests on new accounts. Ask for what
   the first workload needs, not for what the customer might want later.
3. **Never bypass a denial.** A quota AWS denied in the last 30 days comes back as `deferred` with
   the denial's request id. Show the date from the answer and say that AWS decided recently. Pass
   `confirm_denied` only if the customer still wants it after seeing that. Never invent an id.
4. **Consent is the owner's.** If the answer says `consent: false`, nothing was filed. Tell the
   customer an organization owner runs `mctl cloud-account allow-quota-requests <id>`. Do not
   try to work around it.
5. **Never handle the API key.** Do not ask for it, accept it in chat, put it in a command or file,
   read `~/.config/multicloud/credentials`, or print environment variables. The customer stores it
   with `mctl auth login`. If they paste one, tell them to revoke it on multicloud.io (Account →
   API keys) and make a new one.
6. **AWS only.** Check the account's cloud with `mctl cloud-account list`. For a non-AWS account,
   stop and say this skill covers AWS.
7. **Never guess a quota code.** Use the codes the data returns. If the customer needs a quota the
   data does not list (for example another instance family), say so and ask them to request it in
   the AWS Service Quotas console; do not type a code from memory.

If the tools are missing (`get_quota_plan_data` or `mctl cloud-account quota-plan` is unknown),
the customer's Multicloud release is older than this skill. Say so and stop.

## Step 1: Ask what they want to run

Ask one question at a time. Every list has an "other" answer.

1. Goal: a proof of concept, CI runners, production inference, batch or training, or other.
2. If proof of concept: extend an existing cluster, or a CI workload?
3. If extend: one LLM on one GPU, a CPU service, a multi-node test, or other.

From the answers derive the need: instance family (GPU or standard), spot or on-demand, vCPU
count, and candidate regions. State the derived need in one line and let the customer correct it.
Use the Multicloud catalog tools (`advanced_server_search`, `get_locations`) to compare price and
spot availability by region for the instance the customer needs. Prefer regions that are cheap
and have capacity, and say why. Do not pick a region only because it is the default.

## Step 2: Read the data

Find the AWS account: `mctl cloud-account list` (the number and region list). The organization slug is the team ID of `mctl auth status` (ask the customer if unsure). Without the MCP tools, the web catalog at multicloud.io/catalog does the price comparison of step 1. Then call
`get_quota_plan_data` (or `mctl cloud-account quota-plan <id> --region <r> [--region <r2> ...]`, at
most 10 regions; `--code <c>` reads one more quota code) for the candidate regions. It files nothing. For each quota it gives:

- `current_limit`, or an `error` (a quota you could not read is not a quota that is big enough);
- `open_request`: a request already waiting. Do not file another for the same quota;
- `latest_denial` with `cooldown_active` and `cooldown_until`;
- the request `budget` (open requests per account, per opt-in region, per quota) and `consent`.

Report the budget as the tool gives it. Never quote a cap from memory.

If `consent` is false, tell the customer now that nothing can be filed until an organization owner
runs `mctl cloud-account allow-quota-requests <id>`. Plan with them anyway, but say it first. If the
owner does not want to allow it, use **Without consent: the customer files** below.

## Step 3: Propose an ordered plan

Write a short table: region, quota, current limit, new limit, why. Order it with the quota that
unblocks the first workload first. Leave out a quota that is already big enough (never ask for `desired` at or below
`current_limit`) or already has an open request. Size `desired` to the first workload's need plus a
little headroom: each quota gets one request slot. Put a quota in a cooldown last, with its denial date, and say it needs a decision.
Keep the list within the budget; say what waits and why. Ask which items the customer approves.

## Step 4: File what they approved

For each approved item call `request_quota` (or `mctl cloud-account quota-request <id> --region
<r> --code <c> --desired <n>`). One call files one quota.

| Answer | Tell the customer |
|---|---|
| `filed` with a request id | It is filed. AWS decides, often within hours but sometimes days. |
| `already_open` | A request is already waiting. Nothing new was filed. |
| `deferred` with `denial` | AWS denied this recently. Show the date. Ask again before using `confirm_denied`. |
| `deferred`, budget reason | The request cap is full. Say which requests are open. |
| `planned` and `consent: false` | Nothing was filed. An organization owner must allow quota requests. `mctl` exits non-zero here: do not retry. |
| `planned`, consent true | Nothing was filed. Read `get_quota_plan_data` and report why. |
| `unmatched_confirmations` | The id did not match the latest denial. Read `get_quota_plan_data` again. |
| error 5xx or a timeout | The request may be open. Read `get_quota_plan_data` before you try again. |

## Step 5: Close

Say what was filed, what waits, and how to check: run `get_quota_plan_data` again later, or
`mctl cloud-account verify <id>`. Tell the customer that AWS decides each request and that you
cannot speed it up.

## Without consent: the customer files

When the owner does not allow quota requests, the customer files the same plan with their own AWS
sign-in. The steps are in `flows/gpu-quota-own-cli.json` next to this file (the GPU PoC form:
on-demand G and VT vCPUs in one region).

1. Plan as in steps 1 to 3. Take the quota code, the region and the new limit from the plan data,
   not from memory. The flow's code is the one for on-demand G and VT instances; for another quota,
   use the code the data returned.
2. Read the current limit (step `read-quota`, with the code and region of the plan). You may run it:
   it only reads.
3. Step `request-quota`: show the command with the code, region and value, ask, and run it only
   after a yes (or give it to the customer to run). It uses their AWS sign-in
   (`AWS_PROFILE=<p>`), not Multicloud.
4. Step `answer-aws`: if AWS opens a support case, the customer answers it.
5. Step `wait-approval`: read the request history later. Do not file again while a request is
   open.

On Windows, run the commands inside WSL (see skill `multicloud-workstation`).

## Hand back

End with one line, so an onboarding flow can continue (IDs and states only):

```text
MULTICLOUD-RESULT skill=multicloud-quota status=<done|waiting|blocked|failed> quota=<enough|waiting|denied> region=<r> requests=<id,id|none> filed_by=<multicloud|customer|none>
```

`done` with `quota=enough`: the first workload fits now. `waiting`: requests are open; check again
later with step 2 (it files nothing). `blocked who=owner`: consent is missing and the customer has
not chosen to file themselves. `quota=denied`: AWS denied it; show the date and stop.
