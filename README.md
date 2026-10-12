# TOKEN — live token-usage tracker for Muse

Your real allowance %, burn pace vs safe pace, daily budget, per-day burn
history, a live-ticking reset countdown, and Low Token Mode status —
rebuilt automatically every 15 minutes with zero token cost.

![version](https://img.shields.io/badge/version-1.2.0-orange)

## What it is

- `build_token_live.py` — builds `token-live.html` from `usage-log.json`.
  Run it anytime to regenerate the page.
- `refresh_token_live.py` — reads your allowance via `subscription-status`,
  appends a datapoint to `usage-log.json`, rebuilds the page.
- `usage-log.json` — your data. Ships empty; the refresh script fills it in.
- `systemd/` — timer files for unattended 15-minute refreshes.
- `VERSION` — the release version. The page checks GitHub for newer
  releases at build time and shows an "update available" banner.

## Setup

Requires [Muse](https://muse.ai) (the page reads Muse's own usage numbers).

1. Clone or download this repo.
2. In `systemd/token-live-refresh.service`, set `ExecStart` to the real path
   of `refresh_token_live.py` and `HOME` to your home directory.
3. Seed one datapoint so the page renders immediately:
   `python3 refresh_token_live.py`
4. Install the timer (paths live in /etc and may not survive VM replacement —
   re-install if the page goes stale):
   ```
   sudo cp systemd/token-live-refresh.service systemd/token-live-refresh.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now token-live-refresh.timer
   ```
5. Open `token-live.html` — that's your live page. It auto-reloads every
   10 minutes to pick up fresh builds.

## Your data stays yours

Everything runs on your machine. Nothing is uploaded or shared.

## Updates

Watch this repo's releases — the page tells you when a new version is out.

---
Black Lab LA — Black Laboratory. A Skunkworks. R&D for your life.
