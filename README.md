# substack-radar

Drafts your daily Substack engagement and finds new writers in your niche. It reads public data, ranks it and drafts text. **You post everything by hand.** It never logs into Substack, never posts, likes or comments, and does no browser automation against Substack. The only outbound destination is an optional Slack webhook.

## What it does
- **Daily digest** (GitHub Actions cron, to Slack or stdout): today's queued essay Note, 2 posts to comment on (from different lanes) with draft comments, 1 restack with a take, a bonus reactive Note, and news hooks when a company you covered makes news.
- **Note queue**: turns each essay into about 10 Notes, dripped one per day.
- **Reply drafts**: paste comments in, get replies out.
- **Weekly discovery** (Sundays): crawls Substack's recommendation graph 2 hops out from your `feeds.yaml` seeds and ranks new writers by how many of your seeds recommend them. Claude checks topical fit and lane. The tier comes from real subscriber counts or bestseller badges when Substack exposes them. You get up to 8 picks with one-line `add` commands.
- **Scorecard**: reads a Substack stats CSV and reports which posts and Notes drove subscribers and which lane is growing.

## Safety rails
- **Pseudonymity**: `voice.md` goes into every prompt. Put any identifying terms (real name, employer, city, …) in `blocklist.txt`, one per line; it's gitignored. A draft containing one is rejected and regenerated once, then dropped. The terms are never sent to the model.
- **Polite fetching**: about 1 request per second, a real User-Agent, a disk cache (`.cache/`), retries with backoff. See `docs/endpoints.md`.
- **Fail soft**: a broken feed, endpoint or LLM reply skips that item or section and logs it. Every LLM reply is validated with pydantic (`radar/schemas.py`) and retried once.
- **Secrets**: only in env vars, `.env` (gitignored) or GitHub secrets.

## Setup
1. Python 3.12:
   ```
   python3.12 -m venv .venv && source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```
2. Put `ANTHROPIC_API_KEY=...` in `.env` (and optionally `SLACK_WEBHOOK_URL=...`). Real env vars override the file.
3. Optional: create `blocklist.txt` with your identifying terms.
4. Optional: set `me.subscribers` in `feeds.yaml` so discovery can tell anchors from peers.
5. For the scheduled runs: push to a **private** GitHub repo and add the repo secrets `ANTHROPIC_API_KEY` and `SLACK_WEBHOOK_URL` (Slack → Apps → Incoming Webhooks). Then go to Actions → *daily-radar* / *weekly-discover* → **Run workflow** to test.

Both workflows commit `state.json`. They share a `concurrency: radar-state` group, so they queue instead of overlapping, and they `git pull --rebase` before pushing.

## Commands
Every command takes `--dry-run`, which prints only: no Slack post and no writes to `state.json` or `feeds.yaml`.

| Command | What it does |
|---|---|
| `python -m radar daily` | Morning digest. Pops one queued Note and marks posts seen. |
| `python -m radar queue-notes essays/x.md <published_url> [--lane hard-tech] [--count 10]` | Essay → Notes, queued one per day. `--lane` tags them for the scorecard. |
| `pbpaste \| python -m radar reply` | Draft replies to the comments on stdin. |
| `python -m radar discover [--hops 2]` | New-writer picks. Picks aren't suggested again (delete from `rejected_writers` in `state.json` to undo). |
| `python -m radar add <url> [--tier peer] [--lane ai-infra] [--name "..."]` | Append a writer to `feeds.yaml`. Comments and formatting stay intact; the name defaults to the feed title. |
| `python -m radar scorecard stats.csv` | Subscriber drivers and lane growth from a Substack stats export. |
| `pytest` | Offline tests against recorded fixtures (`tests/fixtures/`). |

`RADAR_MODEL` overrides the model (default `claude-sonnet-5-5`).

## Lanes
`lanes:` in `feeds.yaml` lists your sector lanes, and each publication has an optional `lane:`. Daily picks rotate the starting lane each day, cap posts per lane, require the two comment picks to come from different lanes, and avoid yesterday's lanes. Discovery labels each pick with a lane. The scorecard takes a `lane` column if the CSV has one; otherwise it infers the lane from essays you queued with `--lane`.

## The daily 10-minute routine
1. **(1 min)** Open the Slack digest, or run `python -m radar daily` locally.
2. **(2 min)** Post today's essay Note. Tweak a word if it doesn't sound like you.
3. **(4 min)** Leave the 2 comments. Read each post first and edit the draft: the drafts are a starting point, not a script.
4. **(1 min)** Restack the third post with the take.
5. **(2 min)** Reply to anyone who engaged with your stuff: `pbpaste | python -m radar reply`.

Sundays: skim the discovery picks, then paste the `python -m radar add ...` lines for the ones you want and commit `feeds.yaml`. Once a week, export stats from Substack and run `python -m radar scorecard <file>.csv`.

## Tuning
- `feeds.yaml`: publications, lanes, and companies to watch. Keep `watch` queries tight (quoted names), because loose queries match unrelated news.
- `voice.md`: your voice rules. Tighten it whenever drafts sound off.
- `docs/endpoints.md`: what each Substack endpoint returns, if one breaks.
