# Lab Foundation Readiness

A single, objective system for answering: **"Are we foundation-ready yet?"**

This replaces circling with a weighted checklist + automated checks. Run it any
time; it writes `status.json` and prints the current percentage plus gaps.

## Usage

```sh
# Run all automated checks and print readiness
python3 ~/dev/labs/foundation/check.py

# Mark manual items
python3 ~/dev/labs/foundation/check.py --set mfa_audit done
python3 ~/dev/labs/foundation/check.py --set branch_protection done --note branch_protection "protected main via GitHub UI"

# Record completed ops (after a real drill/deploy)
python3 ~/dev/labs/foundation/check.py --mark-backup
python3 ~/dev/labs/foundation/check.py --mark-monitoring
```

## Scoring

- Each item has a weight (1 or 2).
- Status: `done` = 1.0, `partial` = 0.5, `todo` = 0.0.
- Readiness % = weighted earned / weighted total.

## Items

See `foundation.json` for the full list, weights, and notes. High-weight gaps
(backup, CI, CEO identity) dominate the score on purpose — they are the
blockers for a sustainable first dollar.

## Files

- `foundation.json` — checklist (source of truth; manual statuses live here).
- `check.py` — runs automated checks, updates statuses, writes `status.json`.
- `status.json` — last run result (generated; do not hand-edit).

## Rule

Do not start new research spending until readiness >= 80% (or an explicit
L0 override). Re-run after each gap is closed.

Note: "published" is not "done". `first_sale` requires an actual purchase;
`product_qa_market_gap` requires evidence of value/market fit, not just
shipping code.