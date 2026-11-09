#!/usr/bin/env python3
"""Lab foundation readiness checker.

Reads foundation/foundation.json, runs automated checks, writes
foundation/status.json, and prints a weighted readiness percentage.
"""
import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/faris/dev/labs")
FOUNDATION_DIR = ROOT / "foundation"
FOUNDATION_JSON = FOUNDATION_DIR / "foundation.json"
STATUS_JSON = FOUNDATION_DIR / "status.json"
MARKER_DIR = Path.home() / ".config" / "foundation"
SHIP_REPOS = ["workflow-kit", "cockpit", "agent"]
COCKPIT = ROOT / "cockpit"
AGENT = ROOT / "agent"


def load_items():
    with FOUNDATION_JSON.open() as f:
        data = json.load(f)
    return data


def save_items(data):
    with FOUNDATION_JSON.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def run(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=20)
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def score_status(status):
    return {"done": 1.0, "partial": 0.5, "todo": 0.0}.get(status, 0.0)


# ---------- automated checks ----------

def check_ci_ship_repos(item):
    present = []
    missing = []
    for repo in SHIP_REPOS:
        wf = ROOT / repo / ".github" / "workflows"
        if wf.is_dir() and any(wf.iterdir()):
            present.append(repo)
        else:
            missing.append(repo)
    total = len(SHIP_REPOS)
    if len(present) == total:
        status = "done"
    elif len(present) > 0:
        status = "partial"
    else:
        status = "todo"
    item["status"] = status
    item["evidence"] = f"CI present in {len(present)}/{total} ship repos: {', '.join(present) or 'none'}; missing: {', '.join(missing) or 'none'}."


def check_cockpit_m0(item):
    checks = {
        "LICENSE": (COCKPIT / "LICENSE").exists(),
        "CI workflow dir": (COCKPIT / ".github" / "workflows").is_dir(),
        "goreleaser config": any((COCKPIT / n).exists() for n in
                                 [".goreleaser.yaml", ".goreleaser.yml", "goreleaser.yml", "goreleaser.yaml"]),
    }
    done_count = sum(1 for v in checks.values() if v)
    total = len(checks)
    if done_count == total:
        status = "done"
    elif done_count > 0:
        status = "partial"
    else:
        status = "todo"
    item["status"] = status
    item["evidence"] = f"{done_count}/{total} M0 gaps closed: " + ", ".join(
        f"{k}={'yes' if v else 'no'}" for k, v in checks.items()
    ) + "."


def check_secrets_hygiene(item):
    present = []
    missing = []
    for repo in SHIP_REPOS:
        repo_path = ROOT / repo
        if not (repo_path / ".git").exists():
            missing.append(f"{repo}(no git)")
            continue
        ok, _, _ = run(["git", "-C", str(repo_path), "check-ignore", ".env"])
        if ok:
            present.append(repo)
        else:
            missing.append(repo)
    total = len(SHIP_REPOS)
    if len(present) == total:
        status = "done"
    elif len(present) > 0:
        status = "partial"
    else:
        status = "todo"
    item["status"] = status
    item["evidence"] = f".env ignored in {len(present)}/{total} ship repos: {', '.join(present) or 'none'}; not ignored: {', '.join(missing) or 'none'}."


def check_backup_tested(item):
    marker = MARKER_DIR / "backup-verified"
    if marker.exists():
        item["status"] = "done"
        item["evidence"] = f"Marker present: {marker} (last: {marker.stat().st_mtime and datetime.fromtimestamp(marker.stat().st_mtime, tz=timezone.utc).isoformat()})."
    else:
        item["status"] = "todo"
        item["evidence"] = f"No marker at {marker}. Run a restore drill, then: foundation/check.py --mark-backup."


def check_monitoring_deployed(item):
    marker = MARKER_DIR / "monitoring-verified"
    if marker.exists():
        item["status"] = "done"
        item["evidence"] = f"Marker present: {marker}."
        return
    # try systemctl user units
    for unit in ("beszel.service", "uptime-kuma.service", "uptimekuma.service"):
        ok, out, _ = run(["systemctl", "--user", "is-active", unit])
        if ok and out.strip() == "active":
            item["status"] = "done"
            item["evidence"] = f"systemd user unit active: {unit}."
            return
    item["status"] = "todo"
    item["evidence"] = "No monitoring marker and no active beszel/uptime-kuma user unit. Run: foundation/check.py --mark-monitoring after deploying."


def check_ceo_identity(item):
    path = AGENT / "identities" / "ceo.yaml"
    if not path.exists():
        item["status"] = "todo"
        item["evidence"] = "identities/ceo.yaml missing."
        return
    text = path.read_text()
    # look for key-like fields with non-null/non-empty values
    found = 0
    details = []
    for key in ("ssh_key", "pat", "token", "ssh", "github_token", "api_key"):
        m = re.search(rf"(?im)^\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text)
        if m:
            val = m.group(1).strip().split("#", 1)[0].strip().strip('"').strip("'")
            if val and val.lower() not in ("null", "none", "~", ""):
                found += 1
                details.append(f"{key}=set")
            else:
                details.append(f"{key}=null")
    if found >= 2:
        status = "done"
    elif found == 1:
        status = "partial"
    else:
        status = "todo"
    item["status"] = status
    item["evidence"] = f"Provisioned credential fields: {found} ({', '.join(details) or 'none found'})."


def check_runbooks(item):
    candidates = []
    search_dirs = [AGENT / "docs", COCKPIT, ROOT]
    for d in search_dirs:
        if d.exists():
            for p in d.rglob("*"):
                if p.is_file() and "runbook" in p.name.lower():
                    candidates.append(str(p.relative_to(ROOT)))
    if candidates:
        item["status"] = "done"
        item["evidence"] = f"Runbook files found: {', '.join(candidates[:5])}."
    else:
        item["status"] = "todo"
        item["evidence"] = "No *runbook* files found in agent/docs, cockpit, or labs root."


CHECKS = {
    "ci_ship_repos": check_ci_ship_repos,
    "cockpit_m0": check_cockpit_m0,
    "secrets_hygiene": check_secrets_hygiene,
    "backup_tested": check_backup_tested,
    "monitoring_deployed": check_monitoring_deployed,
    "ceo_identity": check_ceo_identity,
    "runbooks": check_runbooks,
}


def compute(data):
    items = data["items"]
    for item in items:
        if item.get("auto") and item["id"] in CHECKS:
            CHECKS[item["id"]](item)
    total_weight = sum(i["weight"] for i in items)
    earned = sum(i["weight"] * score_status(i["status"]) for i in items)
    pct = (earned / total_weight * 100) if total_weight else 0.0
    data["updated"] = datetime.now(timezone.utc).isoformat()
    data["percentage"] = round(pct, 1)
    # write status.json
    status = {
        "updated": data["updated"],
        "percentage": data["percentage"],
        "earned_weight": round(earned, 2),
        "total_weight": total_weight,
        "items": [
            {
                "id": i["id"],
                "title": i["title"],
                "weight": i["weight"],
                "status": i["status"],
                "auto": i.get("auto", False),
                "evidence": i.get("evidence", ""),
            }
            for i in items
        ],
    }
    STATUS_JSON.write_text(json.dumps(status, indent=2) + "\n")
    save_items(data)
    return data, status


def print_report(data, status):
    pct = status["percentage"]
    print(f"\nLab foundation readiness: {pct}%  ({status['earned_weight']}/{status['total_weight']} weighted points)\n")
    print("DONE:")
    for i in status["items"]:
        if i["status"] == "done":
            print(f"  [x] {i['id']} (w={i['weight']}) — {i['evidence']}")
    print("\nPARTIAL:")
    for i in status["items"]:
        if i["status"] == "partial":
            print(f"  [~] {i['id']} (w={i['weight']}) — {i['evidence']}")
    print("\nTODO (gaps, highest weight first):")
    todos = sorted([i for i in status["items"] if i["status"] == "todo"], key=lambda x: -x["weight"])
    for i in todos:
        print(f"  [ ] {i['id']} (w={i['weight']}) — {i['evidence'] or i.get('notes', '')}")
    print(f"\nStatus written to {STATUS_JSON}")


def main():
    parser = argparse.ArgumentParser(description="Lab foundation readiness checker")
    parser.add_argument("--set", nargs=2, metavar=("ID", "STATUS"), help="Set item status (done/partial/todo)")
    parser.add_argument("--note", nargs=2, metavar=("ID", "TEXT"), help="Set evidence note for an item")
    parser.add_argument("--mark-backup", action="store_true", help="Create backup-verified marker")
    parser.add_argument("--mark-monitoring", action="store_true", help="Create monitoring-verified marker")
    args = parser.parse_args()

    MARKER_DIR.mkdir(parents=True, exist_ok=True)
    if args.mark_backup:
        (MARKER_DIR / "backup-verified").write_text(datetime.now(timezone.utc).isoformat() + "\n")
        print("Created backup-verified marker.")
    if args.mark_monitoring:
        (MARKER_DIR / "monitoring-verified").write_text(datetime.now(timezone.utc).isoformat() + "\n")
        print("Created monitoring-verified marker.")

    data = load_items()
    if args.set:
        id_, status = args.set
        if status not in ("done", "partial", "todo"):
            raise SystemExit("status must be done/partial/todo")
        found = False
        for item in data["items"]:
            if item["id"] == id_:
                item["status"] = status
                item["auto"] = False
                found = True
                break
        if not found:
            raise SystemExit(f"unknown item id: {id_}")
    if args.note:
        id_, text = args.note
        found = False
        for item in data["items"]:
            if item["id"] == id_:
                item["evidence"] = text
                found = True
                break
        if not found:
            raise SystemExit(f"unknown item id: {id_}")

    data, status = compute(data)
    print_report(data, status)


if __name__ == "__main__":
    main()