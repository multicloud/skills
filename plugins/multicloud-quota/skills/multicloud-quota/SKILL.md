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
   the denial's request id. Show the date and say that AWS decided recently. Pass
   `confirm_denied` only if the customer still wants it after seeing that. Never invent an id.
4. **Consent is the owner's.** If the answer says `consent: false`, nothing was filed. Tell the
   customer an organization owner runs `mctl cloud-account allow-quota-requests <id>`. Do not
   try to work around it.
5. **Never handle the API key.** Same rule as the other Multicloud skills: the customer stores it
   with `mctl auth login`.

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

Find the AWS account: `mctl cloud-account list` (the number and region list). Then call
`get_quota_plan_data` (or `mctl cloud-account quota-plan <id> --region <r> ...`) for the
candidate regions. It files nothing. For each quota it gives:

- `current_limit`, or an `error` (a quota you could not read is not a quota that is big enough);
- `open_request`: a request already waiting. Do not file another for the same quota;
- `latest_denial` with `cooldown_active` and `cooldown_until`;
- the request `budget` (open requests per account, per opt-in region, per quota) and `consent`.

Report the budget as the tool gives it. Never quote a cap from memory.

## Step 3: Propose an ordered plan

Write a short table: region, quota, current limit, new limit, why. Order it with the quota that
unblocks the first workload first. Leave out a quota that is already big enough or already has an
open request. Put a quota in a cooldown last, with its denial date, and say it needs a decision.
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
| `planned` and `consent: false` | Nothing was filed. An organization owner must allow quota requests. |
| `unmatched_confirmations` | The id did not match the latest denial. Read `get_quota_plan_data` again. |
| error 5xx or a timeout | The request may be open. Read `get_quota_plan_data` before you try again. |

## Step 5: Close

Say what was filed, what waits, and how to check: run `get_quota_plan_data` again later, or
`mctl cloud-account verify <id>`. Tell the customer that AWS decides each request and that you
cannot speed it up.
