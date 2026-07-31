---
status: active
progress: 60
---

# Hydrow Web

<!--
IdeaBRD parses this file. It is the source of truth for this idea's tile:
the app re-reads it on every open and commits its own edits back here, so
the shape below matters more than it looks. Anything the parser
(backend/app/ideafile.py) can't read is dropped silently.

  frontmatter  status: one of idea, active, paused, done. progress: 0-100.
               Any other key is ignored.
  # heading    The idea title (first H1).
  prose        Everything outside the Todos section becomes the tile's
               notes, shown on the board — so keep it short. Documentation
               written here is published, not filed away.
  ## Todos     That heading exactly (or "## To-Dos"); "## ToDo", "## TODO"
               and "## Tasks" do not match and the whole list is lost.
               Inside it, only "- [ ] open" / "- [x] done" lines survive:
               sub-headings and blank-line grouping are discarded, and a
               wrapped item is cut at the line break, so keep each to-do on
               one line. The next "## " heading ends the list.

To-dos are matched to the board by exact text, so rewording one replaces it
rather than editing it in place — expect a checked item to come back
unchecked if you reword it.

HTML comments are stripped on read, so this block never reaches the board.
-->

A self-hosted web dashboard for Hydrow rowing data, built on the undocumented
Hydrow mobile API (`v2.api.prod.hydrow-external.net`). Started as a Python CLI
(`hydrow.py`) that reverse-engineered the endpoints; now a Flask app that logs in
with Hydrow credentials, keeps tokens in a Redis-backed server-side session, and
proxies the API so the browser never sees a bearer token.

Live at hydrow.nickknows.net. Shipping today: stats dashboard with period tabs
and Chart.js meters/watts graphs, workout history with poster art, per-workout
leaderboards, and per-rower profile pages. Deploys via GitHub Actions → Docker Hub
→ Helm image bump → ArgoCD auto-sync.

Next up is hardening the parts that were rushed to get it live — the session
secret is hardcoded in the Helm manifest, there are no tests or health probes —
plus surfacing the API data already proxied but unused (personal records,
calendar) and the rower search the CLI can do but the web app can't.

## Todos

- [x] Reverse-engineer the Hydrow mobile API and build a CLI client (hydrow.py)
- [x] Wrap the API in a Flask app with Redis-backed server-side sessions
- [x] Build the stats dashboard with period tabs and Chart.js meters/watts graphs
- [x] Render workout history as cards with poster images and descriptive stats
- [x] Add per-workout leaderboard pages with a real table and avatar fallbacks
- [x] Add per-rower profile pages backed by the community profile + feed endpoints
- [x] Containerize with a multi-stage non-root Dockerfile and gunicorn
- [x] Ship a Helm chart (app + redis + ingress) and CI that bumps the image tag for ArgoCD
- [x] Trust X-Forwarded-For via ProxyFix so logs show real client IPs
- [ ] Move SECRET_KEY out of helm/templates/hydrow-web-deployment.yaml into a real Secret
- [ ] Rotate the leaked session signing key once it is out of the manifest
- [ ] Add a /healthz endpoint plus liveness/readiness probes to the deployment
- [ ] Set CPU/memory requests and limits on the app and redis pods
- [ ] Give redis a PVC or accept session loss on restart explicitly
- [ ] Add tests for the auth flow, token refresh, and the API proxy error paths
- [ ] Build a personal records page — /api/records is already proxied but unused
- [ ] Build a calendar/streak view — /api/calendar is already proxied but unused
- [ ] Expose rower search (members/search) in the web UI, not just the CLI
- [ ] Self-host Chart.js instead of loading it from cdnjs
- [ ] Add pagination or infinite scroll to workout history beyond the first 15
- [ ] Share the API client between hydrow.py and app/routes.py instead of duplicating it
- [ ] Write a README covering local dev, required env vars, and the deploy path
- [ ] Add a CLAUDE.md so future sessions start with the architecture and deploy flow
