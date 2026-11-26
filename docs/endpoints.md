# Endpoints (verified live 2026-11-26)

Everything is read-only and goes through `radar/net.py`: about 1 request per second, a browser-style User-Agent tagged `substack-radar`, a disk cache in `.cache/`, and up to 3 retries with backoff (it honors `Retry-After`). A 4xx other than 408/429 is logged and skipped without retrying. Substack's JSON endpoints are undocumented and all wrapped in `radar/substack.py`. Recorded samples are in `tests/fixtures/`.

## 1. Publication RSS: `GET <pub>/feed`

Works for both `*.substack.com` and custom domains (checked: `dtvc.substack.com`, `www.notboring.co`). It returns `application/xml` RSS 2.0 with about the last 20 posts. feedparser entries have `id` (the post URL), `link`, `title`, `published`/`published_parsed` (GMT), `summary` (the subtitle), `content` (full HTML) and `author`. Large publications send big feeds: Not Boring's is about 1.3 MB. Cached for 1 hour.

Failure modes seen on the seed list:

| Seed | What happened |
|---|---|
| `www.riskgaming.com` | 301 to `blog.riskgaming.com` (urllib follows it). The archive API 404s on the old host, so `feeds.yaml` now uses the new one. |
| `lukeringlein.substack.com` | Redirects to a `substack.com/@lukeringlein` profile page (HTML). The publication is gone. |
| `zachglabman.substack.com` | Feed returns 400, archive returns 403, the homepage redirects to `/welcome`. |
| `defensevc.substack.com` | 404: deleted. |

## 2. Archive: `GET <pub>/api/v1/archive?sort=new&limit=N`

**The shape changed.** It is now an object, `{"posts": [...], "nextCursor": "<base64>"}`, not a bare list. The parser accepts both shapes.

Useful fields per post: `id`, `publication_id`, `title`, `subtitle`, `slug`, `canonical_url`, `post_date` (ISO 8601, `Z`), `audience`, `type`, `wordcount`, `reaction_count`, `comment_count`, `restacks`, and `publishedBylines[]`. Each byline has `id`, `name`, `handle` and `bestseller_tier`.

Used for: getting `publication_id` (with `limit=1`), and for recent titles plus the last post date during discovery (`limit=8`). Cached for 1 day.

## 3. Recommendations: `GET https://substack.com/api/v1/recommendations/from/<publication_id>`

This returns a JSON list, one entry per publication that `<publication_id>` recommends (4 for DTVC, 26 for Not Boring). The field names the original code guessed were right:

```
{ id, recommending_publication_id, recommended_publication_id, description, blurb_active,
  created_at, updated_at, email_sent_at, list_ids, subscribe_auth_token,
  recommendedPublication: {
    id, name, subdomain, custom_domain, custom_domain_optional, hero_text,
    author_id, author_name, author_photo_url, logo_url, language, payments_state,
    primaryUser: {id, name, handle, photo_url, bio, ...}, author: {...same...},
    displayProfile: {userId, name, handle, photo_url}, ... } }
```

- URL is `https://<custom_domain>` if one is set, else `https://<subdomain>.substack.com`.
- `recommendedPublication.id` is the publication ID, so the second hop can call this endpoint directly without an archive lookup.
- `primaryUser.handle` is what the size lookup below needs.
- **There are no subscriber or size fields here.**

Cached for 7 days.

## 4. Size signal: `GET https://substack.com/api/v1/user/<handle>/public_profile`

This one feeds task 4. It returns about 600 KB of JSON; the parts used are:

| field | example (Not Boring) |
|---|---|
| `subscriberCountNumber` | `284000` |
| `subscriberCountString` | `"284K+ subscribers"` |
| `rough_num_free_subscribers_int` | `100000` (bucketed) |
| `bestseller_tier` / `status.bestsellerTier` | `100` (badge tiers seen: 100, 1000) |
| `followerCount` | `379782` |

Discovery calls this only for its final picks (8 at most), cached 7 days. Tier rule (`discover.size_tier`):

- a bestseller badge means `anchor`;
- otherwise at least 10× `me.subscribers` in `feeds.yaml` (500 if unset) means `anchor`;
- otherwise `peer`.

If Substack exposes neither number, the tier comes from the LLM and the digest says so.

## 5. Google News RSS: `GET https://news.google.com/rss/search?q=<query>+when:2d&hl=en-US&gl=US&ceid=US:en`

The format in the original code works. It returns RSS with `title` (ending in ` - <Source>`), `link` (a `news.google.com/rss/articles/...` redirect), `published`, `source` and `id`. `when:2d` often returns zero items on quiet days, which is expected. Queries are loose keyword matches: `"Sift" hardware telemetry startup` pulled in an unrelated VTOL story, so keep queries tight (quoted names). Cached for 1 hour.

## If an endpoint breaks

Only `radar/substack.py` (JSON endpoints) or `radar/sources.py` (RSS) should need changes. A fallback for recommendations would be scraping `<pub>/recommendations` (HTML), but it isn't needed today.
