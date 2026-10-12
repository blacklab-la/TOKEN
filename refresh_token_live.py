#!/usr/bin/env python3
"""Silent token-usage refresh for the live Token page.

Runs `subscription-status status`, appends a datapoint to usage-log.json
(pruned to the last 200 points), and rebuilds token-live.html via
build_token_live.py. Designed to run unattended every 15 minutes via the
systemd timer — no agent, no chat output, near-zero token cost.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "usage-log.json")
MAX_POINTS = 200


def main():
    try:
        out = subprocess.run(
            ["/opt/hatch/bin/subscription-status", "status"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception as e:
        print(f"status check failed: {e}", file=sys.stderr)
        return 1

    m = re.search(r"Usage:\s*(\d+(?:\.\d+)?)%", out)
    if not m:
        print("could not parse usage pct", file=sys.stderr)
        return 1
    pct = float(m.group(1))

    # "Weekly limit resets Oct 16 at 12:24 PM PDT" -> ISO with -07:00 (PDT)
    reset_iso = None
    rm = re.search(
        r"resets\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)\s*(PDT|PST)",
        out,
    )
    if rm:
        mon, day, hh, mm, ap, tzname = rm.groups()
        month = datetime.strptime(mon, "%b").month
        h = int(hh) % 12 + (12 if ap == "PM" else 0)
        # assume current year; roll to next year if the date already passed
        now = datetime.now().astimezone()
        year = now.year
        off = "-07:00" if tzname == "PDT" else "-08:00"
        cand = datetime(year, month, int(day), h, int(mm),
                        tzinfo=timezone(timedelta(hours=int(off[:3]))))
        if cand < now - timedelta(days=1):
            cand = datetime(year + 1, month, int(day), h, int(mm),
                            tzinfo=cand.tzinfo)
        reset_iso = cand.isoformat()

    with open(LOG) as f:
        log = json.load(f)
    now_iso = datetime.now().astimezone().isoformat()
    log["points"].append({"ts": now_iso, "pct_used": pct, "note": "auto refresh"})
    log["points"] = log["points"][-MAX_POINTS:]
    if reset_iso:
        log["reset"] = reset_iso
    with open(LOG, "w") as f:
        json.dump(log, f, indent=2)

    subprocess.run([sys.executable, os.path.join(BASE, "build_token_live.py")],
                   check=True, timeout=60, cwd=BASE, capture_output=True)
    print(f"refreshed: {pct}% @ {now_iso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
