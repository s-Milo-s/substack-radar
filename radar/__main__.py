"""
substack-radar: drafts your Substack engagement. You post; it never does.

  python -m radar daily [--dry-run]
  python -m radar queue-notes essays/nominal.md https://you.substack.com/p/nominal [--lane hard-tech]
  python -m radar reply < comments.txt
  python -m radar discover [--dry-run]
  python -m radar add <url> [--tier peer] [--lane ai-infra] [--name "..."]
  python -m radar scorecard stats.csv [--dry-run]

--dry-run prints the output and writes nothing: no Slack post, no state.json, no feeds.yaml.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import feedparser

from . import config

config.load_env()  # before llm reads ANTHROPIC_API_KEY / RADAR_MODEL

from . import deliver, llm, net, sources, state as st  # noqa: E402
from .schemas import DailyPlan, NoteList, Replies  # noqa: E402

log = logging.getLogger("radar")
ROOT = config.ROOT


def my_essays_brief() -> str:
    out = [f"- {p.stem}: {p.read_text()[:700]}" for p in sorted((ROOT / "essays").glob("*.md"))]
    return "\n".join(out) or "(none yet)"


# --- daily ------------------------------------------------------------------------

def rotate_by_lane(posts: list[dict], lanes: list[str], today: date, per_lane: int = 5) -> list[dict]:
    """Interleave posts lane by lane, starting from a lane that rotates daily,
    capped per lane so one busy lane can't crowd out the rest."""
    present = [l for l in lanes if any(p["lane"] == l for p in posts)]
    present += sorted({p["lane"] for p in posts} - set(present))
    if not present:
        return []
    start = today.toordinal() % len(present)
    order = present[start:] + present[:start]
    buckets = {l: [p for p in posts if p["lane"] == l][:per_lane] for l in order}
    out = []
    for i in range(per_lane):
        out.extend(buckets[l][i] for l in order if i < len(buckets[l]))
    return out


def check_plan(plan: DailyPlan, posts: list[dict], news: list[dict]) -> list[str]:
    problems = []
    idx = [c.post for c in plan.comments] + ([plan.restack.post] if plan.restack else [])
    problems += [f"post index {i} out of range 0..{len(posts) - 1}" for i in idx if not 0 <= i < len(posts)]
    problems += [f"news index {h.news} out of range 0..{len(news) - 1}"
                 for h in plan.news_hooks if not 0 <= h.news < len(news)]
    lanes = [posts[c.post]["lane"] for c in plan.comments if 0 <= c.post < len(posts)]
    if len(set(p["lane"] for p in posts)) > 1 and len(lanes) != len(set(lanes)):
        problems.append("the comment picks must come from different lanes")
    return problems


def render_daily(plan: DailyPlan | None, posts: list[dict], news: list[dict]) -> list[str]:
    if plan is None:
        return []
    sections = []
    ok = [c for c in plan.comments if 0 <= c.post < len(posts)][:2]
    if ok:
        lines = ["*Comment on these*"]
        for c in ok:
            p = posts[c.post]
            lines.append(f"• <{p['url']}|{p['publication']}: {p['title']}> [{p['lane']}]\n"
                         f"  _{c.why}_\n  > {c.comment}")
        sections.append("\n".join(lines))
    r = plan.restack
    if r and 0 <= r.post < len(posts):
        p = posts[r.post]
        sections.append(f"*Restack with a take*\n• <{p['url']}|{p['publication']}: {p['title']}> "
                        f"[{p['lane']}]\n  > {r.take}")
    if plan.reactive_note:
        sections.append(f"*Bonus Note*\n>{plan.reactive_note}")
    for h in plan.news_hooks:
        if 0 <= h.news < len(news):
            n = news[h.news]
            sections.append(f"*News hook: {n['company']}*\n• <{n['url']}|{n['title']}>\n"
                            f"  > {h.note}\n  Essay: {n['essay_url']}")
    return sections


def cmd_daily(args) -> None:
    cfg = config.load_feeds()
    s = st.load()
    posts = rotate_by_lane(st.unseen(sources.recent_posts(cfg["publications"]), s),
                           cfg["lanes"], date.today())
    news = st.unseen(sources.company_news(cfg["watch"]), s)
    log.info("%d new posts, %d news items", len(posts), len(news))

    sections = []
    drip = st.pop_note(s)
    if drip:
        sections.append(f"*Today's essay Note* ({len(s['note_queue'])} left in queue)\n"
                        f">{drip['text']}\nLink: {drip['url']}")

    plan = None
    if posts or news:
        yesterday = ", ".join(s.get("last_lanes") or []) or "(none)"
        plan = llm.ask(f"""You are drafting today's Substack engagement for the writer described above.

What they have published (excerpts):
{my_essays_brief()}

New posts from writers in their niche (index: publication [tier, lane] title — summary):
{chr(10).join(f"{i}: {p['publication']} [{p['tier']}, {p['lane']}] {p['title']} — {p['summary'][:500]}" for i, p in enumerate(posts)) or "(none)"}

News about companies they have covered:
{chr(10).join(f"{i}: [{n['company']}] {n['title']}" for i, n in enumerate(news)) or "(none)"}

Fill in:
- comments: the best 2 posts to comment on. Prefer anchors for reach and peers for relationships.
  The two must come from DIFFERENT lanes. Lanes used yesterday: {yesterday}; prefer others today.
- restack: one post to restack with a one-line take (ideally a third lane), or null.
- reactive_note: a standalone Note reacting to today's niche news or posts, under 280 chars, or null.
- news_hooks: for each news item worth it, a Note re-sharing their essay off that news, under 280 chars.
Skip anything off-topic for startups, tech strategy, AI, hard tech, or company analysis. Fewer, better picks beat filler.""",
            DailyPlan, check=lambda p: check_plan(p, posts, news))

    sections += render_daily(plan, posts, news)
    if plan:
        s["last_lanes"] = sorted({posts[c.post]["lane"] for c in plan.comments if 0 <= c.post < len(posts)})
    deliver.send("\n\n".join(sections) if sections else "Radar: nothing worth your time today.",
                 dry_run=args.dry_run)
    if args.dry_run:
        log.info("dry run: state.json not written")
        return
    st.mark_seen(s, [p["id"] for p in posts] + [n["id"] for n in news])
    st.save(s)


# --- queue-notes / reply ----------------------------------------------------------

def cmd_queue_notes(args) -> None:
    essay = Path(args.essay).read_text()
    out = llm.ask(f"""Turn this essay into {args.count} standalone Substack Notes that drive readers to it.
Mix formats: hot take, question, mini-thread (3 short lines), striking number, contrarian one-liner.
Each must make sense with zero context and stay under 300 characters. Order them strongest first.

ESSAY:
{essay}""", NoteList, max_tokens=6000,
        check=lambda o: [] if o.notes else ["notes list is empty"])
    if out is None:
        sys.exit("No Notes generated (see log). Nothing queued.")
    for i, t in enumerate(out.notes, 1):
        print(f"{i}. {t}\n")
    if args.dry_run:
        print(f"Dry run: {len(out.notes)} Notes not queued.")
        return
    s = st.load()
    s["note_queue"].extend({"text": t, "url": args.url, "lane": args.lane} for t in out.notes)
    s["essays"][args.url.rstrip("/")] = args.lane or "unknown"
    s["essays"][Path(args.essay).stem] = args.lane or "unknown"
    st.save(s)
    print(f"Queued {len(out.notes)} Notes. Edit state.json to tweak or reorder.")


def cmd_reply(args) -> None:
    comments = sys.stdin.read().strip()
    if not comments:
        sys.exit("Paste comments on stdin, e.g. pbpaste | python -m radar reply")
    out = llm.ask(f"""These are comments readers left on the writer's posts or Notes. Draft a reply to each:
short, warm but not sycophantic, keeps the conversation going (agree-and-extend, push back, or ask back).

COMMENTS:
{comments}""", Replies)
    if out is None:
        sys.exit("No replies generated (see log).")
    for r in out.replies:
        print(f"> {r.comment}\n{r.reply}\n")


# --- discover / add ---------------------------------------------------------------

def cmd_discover(args) -> None:
    from . import discover as d
    cfg = config.load_feeds()
    s = st.load()
    topics = ", ".join(p.stem for p in (ROOT / "essays").glob("*.md")) or "startup teardowns"
    cands = d.discover(cfg["publications"], hops=args.hops, exclude=s.get("rejected_writers", []))
    picks = d.score(cands, topics, cfg["lanes"], my_subs=(cfg["me"] or {}).get("subscribers"))
    if not picks:
        deliver.send("Discovery: no strong new writers this week.", dry_run=args.dry_run)
        return
    lines = ["*New writers to check out*"]
    for p in picks:
        if p["tier_source"] == "size":
            size = f"{p['subscribers']:,}+ subs" if p["subscribers"] else "size unknown"
            if p["bestseller"]:
                size += f", bestseller {p['bestseller']}"
            tier = f"{p['tier']} ({size})"
        else:
            tier = f"{p['tier']} (LLM guess: Substack exposed no size data)"
        lines.append(f"• <{p['url']}|{p['name']}> fit {p['fit']}/10, lane *{p['lane']}*, {tier}, "
                     f"recommended by {p['recommended_by']} of yours\n  _{p['why']}_")
    lines.append("Accept one with:\n```\n" + "\n".join(
        f"python -m radar add {p['url']} --tier {p['tier']} --lane {p['lane']}" for p in picks) + "\n```")
    deliver.send("\n".join(lines), dry_run=args.dry_run)
    if args.dry_run:
        log.info("dry run: suggested writers not recorded in state.json")
        return
    # don't resurface the same names next week; delete from this list to see one again
    s.setdefault("rejected_writers", []).extend(p["url"] for p in picks)
    st.save(s)


def _feed_title(url: str) -> str | None:
    body = net.get(sources.feed_url(url), ttl=3600)
    return feedparser.parse(body).feed.get("title") if body else None


def cmd_add(args) -> None:
    from . import feeds
    cfg = config.load_feeds()
    if args.lane and cfg["lanes"] and args.lane not in cfg["lanes"]:
        sys.exit(f"Unknown lane '{args.lane}'. Add it to lanes: in feeds.yaml or pick one of: "
                 + ", ".join(cfg["lanes"]))
    name = args.name or _feed_title(args.url) or args.url
    text = feeds.add_publication(args.url, name, tier=args.tier, lane=args.lane)
    if text is None:
        print(f"{args.url} is already in feeds.yaml")
        return
    if args.dry_run:
        print(f"Dry run: would add {name} ({args.url}) as {args.tier}"
              + (f", lane {args.lane}" if args.lane else ""))
        return
    config.FEEDS.write_text(text)
    print(f"Added {name} to feeds.yaml")


# --- scorecard --------------------------------------------------------------------

def cmd_scorecard(args) -> None:
    from . import scorecard
    s = st.load()
    lane_for = dict(s.get("essays", {}))
    lane_for.update({n["url"].rstrip("/"): n["lane"] for n in s["posted_notes"] + s["note_queue"]
                     if n.get("lane")})
    rows, subs_cols = scorecard.parse(Path(args.csv), lane_for)
    deliver.send(scorecard.report(rows, subs_cols), dry_run=args.dry_run)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s",
                        stream=sys.stderr)
    for noisy in ("httpx", "httpx2", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    ap = argparse.ArgumentParser(prog="radar")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cmd(name: str, fn, help: str):
        p = sub.add_parser(name, help=help)
        p.add_argument("--dry-run", action="store_true", help="print only; write nothing")
        p.set_defaults(fn=fn)
        return p

    cmd("daily", cmd_daily, "morning digest")
    q = cmd("queue-notes", cmd_queue_notes, "turn an essay into queued Notes")
    q.add_argument("essay")
    q.add_argument("url")
    q.add_argument("--count", type=int, default=10)
    q.add_argument("--lane", default=None)
    cmd("reply", cmd_reply, "draft replies to comments on stdin")
    dsc = cmd("discover", cmd_discover, "find new writers")
    dsc.add_argument("--hops", type=int, default=2)
    a = cmd("add", cmd_add, "add a writer to feeds.yaml")
    a.add_argument("url")
    a.add_argument("--tier", default="peer", choices=["anchor", "peer", "news"])
    a.add_argument("--lane", default=None)
    a.add_argument("--name", default=None)
    sc = cmd("scorecard", cmd_scorecard, "weekly scorecard from a stats CSV")
    sc.add_argument("csv")

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
