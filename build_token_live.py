#!/usr/bin/env python3
"""Build Kevin's live Token app page.

Reads the latest datapoint from usage-log.json and generates a Token-styled
live page (same look as the Token v1.1 demo he likes) with REAL numbers:
current usage %, trajectory (your pace vs safe pace, projected empty, buffer),
daily budget, per-day burn history, the Friday token queue, Low Token Mode
status, and a live-ticking reset countdown. Near-zero token cost; runs
unattended from refresh_usage.py and the twice-daily report crons.
"""
import html as htmlmod
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "usage-log.json")
QUEUE = os.path.join(BASE, "token-queue.md")
OUT = os.path.expanduser("~/workspace/your_files/token-live.html")
LA = ZoneInfo("America/Los_Angeles")

REPO = "blacklab-la/TOKEN"
RELEASES_URL = "https://github.com/blacklab-la/TOKEN/releases/latest"
RELEASES_API = "https://api.github.com/repos/blacklab-la/TOKEN/releases/latest"


def check_update():
    """Return the latest release tag if newer than the local VERSION file.

    Runs at build time (every 15 min), so the page shows an 'update
    available' banner without the browser needing network access.
    Returns None when offline, unreleased, or up to date.
    """
    try:
        with open(os.path.join(BASE, "VERSION")) as f:
            local = f.read().strip().lstrip("v")
    except FileNotFoundError:
        return None
    if not local:
        return None
    try:
        req = urllib.request.Request(
            RELEASES_API, headers={"User-Agent": "token-live"})
        data = json.load(urllib.request.urlopen(req, timeout=10))
        tag = str(data.get("tag_name") or "")
        if tag and tag.lstrip("v") != local:
            return tag
    except Exception:
        pass
    return None


def main():
    with open(LOG) as f:
        log = json.load(f)
    pts = log.get("points", [])
    if not pts:
        raise SystemExit("no datapoints in usage log")
    latest = pts[-1]
    pct_used = float(latest["pct_used"])
    pct_left = max(0.0, 100.0 - pct_used)
    reset_iso = log.get("reset")
    now = datetime.now().astimezone()
    built_iso = now.isoformat()
    now_la = now.astimezone(LA)

    # Update notice: compare local VERSION against the latest GitHub release.
    new_release = check_update()
    if new_release:
        update_html = (
            f'<div class="update"><b>Update available: '
            f'{htmlmod.escape(new_release)}</b> — '
            f'<a href="{RELEASES_URL}">get the latest release</a></div>')
    else:
        update_html = ""

    # Pace since the start of this cycle (first datapoint, right after reset).
    first = pts[0]
    first_dt = datetime.fromisoformat(first["ts"])
    days = max((now - first_dt).total_seconds() / 86400.0, 1e-6)
    pace = (pct_used - float(first.get("pct_used", 0))) / days  # % per day

    reset_dt = datetime.fromisoformat(reset_iso) if reset_iso else None
    if reset_dt:
        reset_label = reset_dt.strftime("%a %b %-d · %-I:%M %p")
        days_left = max((reset_dt - now).total_seconds() / 86400.0, 1e-6)
        daily_budget = pct_left / days_left
    else:
        reset_label, days_left, daily_budget = "—", 1.0, pct_left

    if pace > 0.01:
        empty_in_days = (100.0 - pct_used) / pace
        empty_dt = now + timedelta(days=empty_in_days)
        empty_label = empty_dt.strftime("%a %b %-d")
    else:
        empty_in_days, empty_dt, empty_label = None, None, "—"

    if reset_dt:
        on_track = (empty_dt is None) or (empty_dt >= reset_dt)
        if empty_dt and reset_dt:
            buffer_days = (empty_dt - reset_dt).total_seconds() / 86400.0
        else:
            buffer_days = None
    else:
        on_track, buffer_days = True, None

    if on_track:
        status_html = '<span style="color:#34d17b">On track</span> for reset'
        traj_note = ("After reset — comfortable."
                     if buffer_days and buffer_days >= 1
                     else "Lands right around reset — keep it lean.")
    else:
        status_html = (f'<span style="color:#ffb020">At risk</span> — '
                       f'pace runs out ~{empty_label}, before reset')
        traj_note = f"Runs dry ~{empty_label}, before Friday's reset."

    # Per-day burn history for this cycle.
    by_day = {}
    for p in pts:
        dt = datetime.fromisoformat(p["ts"]).astimezone(LA)
        by_day.setdefault(dt.date(), []).append((dt, float(p["pct_used"])))
    burns, prev_last = [], 0.0
    for d in sorted(by_day):
        last = sorted(by_day[d])[-1][1]
        burns.append((d, last - prev_last))
        prev_last = last
    max_burn = max((b for _, b in burns), default=1.0) or 1.0
    today_burn = burns[-1][1] if burns else 0.0
    hist_rows = []
    for d, b in burns[-8:]:
        w = max(b / max_burn * 100.0, 2.0)
        day_label = d.strftime("%a %b %-d")
        today_tag = ' <span style="color:#FF8000;font-size:11px">· today</span>' \
            if d == now_la.date() else ""
        hist_rows.append(
            f'<div class="hrow"><span class="hday">{day_label}{today_tag}</span>'
            f'<span class="hbar"><span style="width:{w:.0f}%"></span></span>'
            f'<span class="hval">{b:.0f}%</span></div>')
    hist_html = "\n".join(hist_rows)

    # Friday queue — active items only.
    queue_items = []
    try:
        in_queued = False
        with open(QUEUE) as f:
            for line in f:
                if line.startswith("## Queued"):
                    in_queued = True
                    continue
                if in_queued and line.startswith("## "):
                    break
                if in_queued and line.startswith("### "):
                    title = line[4:].strip()
                    if "DONE" in title.upper():
                        continue
                    title = re.split(r"\s+\((?:deferred|carried)", title)[0]
                    queue_items.append(htmlmod.escape(title))
    except FileNotFoundError:
        pass
    if queue_items:
        q_rows = "".join(
            f'<div class="row"><div class="dot">◷</div><div><b>{t}</b>'
            f'<span>Queued for Friday reset</span></div></div>'
            for t in queue_items)
        queue_html = (f'<div class="kicker">QUEUED FOR FRIDAY RESET</div>{q_rows}'
                      f'<div class="sub">Runs Fri Oct 16 after the 12:24 PM reset — '
                      f'you allow each one.</div>')
    else:
        queue_html = ('<div class="kicker">QUEUED FOR FRIDAY RESET</div>'
                      '<div class="sub">Queue is empty — nothing parked.</div>')

    # Trajectory bars.
    pace_w = max(min(pace / max(pace, daily_budget, 0.01) * 100.0, 100.0), 2.0)
    safe_w = max(min(daily_budget / max(pace, daily_budget, 0.01) * 100.0, 100.0), 2.0)
    pace_color = "#FF8000" if pace <= daily_budget else "#ffb020"

    ring_frac = pct_left / 100.0
    circ = 2 * 3.14159 * 54
    dash = circ * ring_frac

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Token — Live</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0a0a0c; color: #e8e8ea;
    font-family: -apple-system, 'SF Pro Text', Inter, Helvetica, Arial, sans-serif;
    padding: 20px 16px 40px; max-width: 560px; margin: 0 auto; }}
  .brand {{ display: flex; align-items: center; gap: 10px; margin: 8px 4px 18px; }}
  .brand h1 {{ font-size: 30px; letter-spacing: -0.5px; }}
  .pill {{ display: inline-block; background: #FF8000; color: #111; font-size: 11px;
    font-weight: 800; padding: 4px 12px; border-radius: 20px; letter-spacing: 1.5px; }}
  .card {{ background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 20px; padding: 20px; margin-bottom: 16px; }}
  .kicker {{ font-size: 11px; letter-spacing: 2.5px; color: #8a8a93; font-weight: 700;
    margin-bottom: 10px; }}
  .big {{ font-size: 22px; font-weight: 800; letter-spacing: -0.3px; }}
  .sub {{ color: #a9a9b2; font-size: 14px; line-height: 1.55; margin-top: 8px; }}
  .row {{ display: flex; align-items: center; gap: 12px; padding: 12px 0;
    border-top: 1px solid rgba(255,255,255,0.06); }}
  .row:first-of-type {{ border-top: none; }}
  .dot {{ width: 34px; height: 34px; border-radius: 50%; background: rgba(255,128,0,0.12);
    display: flex; align-items: center; justify-content: center; font-size: 16px; flex: none; }}
  .row b {{ display: block; font-size: 15px; }}
  .row span {{ color: #8a8a93; font-size: 13px; }}
  .toggle {{ margin-left: auto; width: 56px; height: 32px; border-radius: 20px;
    background: #FF8000; position: relative; flex: none; }}
  .toggle::after {{ content: ''; position: absolute; top: 3px; right: 3px; width: 26px;
    height: 26px; border-radius: 50%; background: #fff; }}
  .allow {{ display: flex; align-items: center; gap: 20px; }}
  .ring {{ position: relative; width: 128px; height: 128px; flex: none; }}
  .ring svg {{ transform: rotate(-90deg); }}
  .ring .num {{ position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center; }}
  .ring .num b {{ font-size: 34px; letter-spacing: -1px; }}
  .ring .num span {{ font-size: 10px; letter-spacing: 2px; color: #8a8a93; }}
  .count {{ font-size: 34px; font-weight: 800; letter-spacing: -0.5px;
    font-variant-numeric: tabular-nums; }}
  .fresh {{ text-align: center; color: #6d6d76; font-size: 12px; margin-top: 18px; }}
  .fresh b {{ color: #FF8000; }}
  .update {{ background: rgba(255,176,32,0.10); border: 1px solid rgba(255,176,32,0.45);
    color: #ffd88a; border-radius: 14px; padding: 12px 16px; margin-bottom: 16px;
    font-size: 14px; }}
  .tbar {{ margin: 10px 0 4px; }}
  .tbar .tlabel {{ display: flex; justify-content: space-between; font-size: 13px;
    margin-bottom: 6px; }}
  .tbar .tlabel b {{ font-size: 14px; }}
  .tbar .ttrack {{ height: 10px; border-radius: 6px; background: rgba(255,255,255,0.07);
    overflow: hidden; }}
  .tbar .tfill {{ display: block; height: 100%; border-radius: 6px; }}
  .hrow {{ display: flex; align-items: center; gap: 10px; padding: 7px 0; }}
  .hday {{ width: 92px; flex: none; font-size: 13px; color: #a9a9b2; }}
  .hbar {{ flex: 1; height: 8px; border-radius: 5px; background: rgba(255,255,255,0.07);
    overflow: hidden; }}
  .hbar span {{ display: block; height: 100%; background: #FF8000; border-radius: 5px; }}
  .hval {{ width: 44px; flex: none; text-align: right; font-size: 13px;
    font-variant-numeric: tabular-nums; }}
  a {{ color: #FF8000; }}
</style></head>
<body>
  <div class="brand"><h1>TOKEN</h1><span class="pill">LIVE</span></div>
  {update_html}

  <div class="card">
    <div class="kicker">LATEST UPDATE&nbsp;&nbsp;·&nbsp;&nbsp;YOUR NUMBERS, YOUR PACE</div>
    <div class="big">{pct_used:.0f}% used · {pct_left:.0f}% left</div>
    <div class="sub">Weekly allowance resets {reset_label}.<br>{status_html}.</div>
  </div>

  <div class="card">
    <div class="kicker">TRAJECTORY — THE RACE TO RESET</div>
    <div class="tbar">
      <div class="tlabel"><span>Your pace</span><b>{pace:.1f}%/day</b></div>
      <div class="ttrack"><span class="tfill" style="width:{pace_w:.0f}%;background:{pace_color}"></span></div>
    </div>
    <div class="tbar">
      <div class="tlabel"><span>Safe pace</span><b>{daily_budget:.1f}%/day</b></div>
      <div class="ttrack"><span class="tfill" style="width:{safe_w:.0f}%;background:#34d17b"></span></div>
    </div>
    <div class="sub">Projected empty: <b style="color:#e8e8ea">{empty_label}</b> — {traj_note}</div>
  </div>

  <div class="card">
    <div class="kicker">DAILY BUDGET</div>
    <div class="big">~{daily_budget:.1f}%/day</div>
    <div class="sub">Stay under this to reach reset.<br>Today's burn so far: <b style="color:#e8e8ea">{today_burn:.0f}%</b>.</div>
  </div>

  <div class="card">
    <div class="kicker">BURN HISTORY — THIS ALLOWANCE WEEK</div>
    {hist_html}
  </div>

  <div class="card">
    <div class="kicker">POWER</div>
    <div style="display:flex; align-items:center; margin-bottom:6px;">
      <div><div class="big">Low Token Mode</div>
      <div class="sub" style="margin-top:2px;"><b style="color:#FF8000">On</b> — running lean</div></div>
      <div class="toggle"></div>
    </div>
    <div class="row"><div class="dot">⚡</div><div><b>Batched tool calls</b><span>Cheapest path first, zero redundant work</span></div></div>
    <div class="row"><div class="dot">☰</div><div><b>Shorter answers</b><span>Signal over noise, unless you ask for depth</span></div></div>
    <div class="row"><div class="dot">⚠</div><div><b>Warn before big tasks</b><span>You approve the spend — or it waits</span></div></div>
    <div class="row"><div class="dot">◷</div><div><b>Friday queue</b><span>Declined work parks here until tokens renew</span></div></div>
  </div>

  <div class="card">
    <div class="kicker">ALLOWANCE</div>
    <div class="allow">
      <div class="ring">
        <svg width="128" height="128" viewBox="0 0 128 128">
          <circle cx="64" cy="64" r="54" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="12"/>
          <circle cx="64" cy="64" r="54" fill="none" stroke="#FF8000" stroke-width="12"
            stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}"/>
        </svg>
        <div class="num"><b>{pct_left:.0f}</b><span>LEFT</span></div>
      </div>
      <div>
        <div class="big">{pct_used:.0f}% used this week</div>
        <div class="sub">{status_html}.<br>Pace: ~{pace:.1f}%/day · empty ~{empty_label}.</div>
      </div>
    </div>
  </div>

  <div class="card">
    {queue_html}
  </div>

  <div class="card">
    <div class="kicker">RESET COUNTDOWN</div>
    <div class="count" id="count">—</div>
    <div class="sub" id="countsub">until reset</div>
  </div>

  <div class="card">
    <div class="kicker">WHAT CHANGED</div>
    <div class="sub" style="margin-top:0"><b style="color:#e8e8ea">v1.2 · Oct 12</b> — Trajectory, daily budget, burn history, and the Friday queue are back from the v1.1 demo, now running on live data.</div>
  </div>

  <div class="fresh">Live data · updated <b id="ago">just now</b> · refreshes automatically</div>

<script>
  var resetTs = {int(reset_dt.timestamp() * 1000) if reset_dt else "null"};
  var builtTs = {int(now.timestamp() * 1000)};
  var resetLabel = {json.dumps(reset_label)};
  function tick() {{
    var el = document.getElementById('count');
    if (resetTs === null) {{ el.textContent = '—'; return; }}
    var ms = resetTs - Date.now();
    if (ms < 0) ms = 0;
    var s = Math.floor(ms / 1000);
    var d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600),
        m = Math.floor(s % 3600 / 60), ss = s % 60;
    function p(n) {{ return (n < 10 ? '0' : '') + n; }}
    el.textContent = d + 'd ' + p(h) + ':' + p(m) + ':' + p(ss);
    document.getElementById('countsub').textContent = 'until ' + resetLabel;
    var mins = Math.floor((Date.now() - builtTs) / 60000);
    document.getElementById('ago').textContent =
      mins < 1 ? 'just now' : mins + ' min ago';
  }}
  tick(); setInterval(tick, 1000);
  setTimeout(function() {{ location.reload(); }}, 600000);
</script>
</body></html>
"""
    with open(OUT, "w") as f:
        f.write(html)
    print("wrote", OUT, f"{pct_used:.0f}% used")

if __name__ == "__main__":
    main()
