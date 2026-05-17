#!/usr/bin/env python3
"""
Generate a balanced multi-creator LinkedIn audit from bulk-export Markdown files.
Each peer gets the same section structure; six-post plan rotates across creators.
"""

from __future__ import annotations

import argparse
import html
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Default window end (aligned with bulk export dates in repo). Overridden by configure_window().
WINDOW_ANCHOR = datetime(2026, 5, 17, 23, 59, 59)
WINDOW_DAYS = 90

POST_BLOCK = re.compile(
    r"--- Post (?P<num>\d+) ---\s*\n"
    r"Author: (?P<author>[^\n]+)\n"
    r"Date: (?P<date>[^\n]+)\n"
    r"Engagement: (?P<eng>[^\n]+)\n"
    r"Media: (?P<media>[^\n]+)\n"
    r"URL: (?P<url>[^\n]+)\n\n"
    r"(?P<body>.*?)(?=\n--- Post \d+ ---|\Z)",
    re.DOTALL,
)

EXPORTED = re.compile(r"Exported:\s*(\d{2})/(\d{2})/(\d{4})")
PAGE = re.compile(r"Page:\s*(https://www\.linkedin\.com/in/[^/\s]+)")

BRAND_PATTERNS = [
    ("Anthropic", re.compile(r"\bAnthropic\b", re.I)),
    ("Claude", re.compile(r"\bClaude\b", re.I)),
    ("OpenAI", re.compile(r"\bOpenAI\b|\bChatGPT\b", re.I)),
    ("Perplexity", re.compile(r"\bPerplexity\b", re.I)),
    ("Replit", re.compile(r"\bReplit\b", re.I)),
    ("NVIDIA", re.compile(r"\bNvidia\b|\bNVIDIA\b", re.I)),
    ("Google", re.compile(r"\bGoogle\b", re.I)),
    ("Microsoft", re.compile(r"\bMicrosoft\b", re.I)),
    ("Meta", re.compile(r"\bMeta\b", re.I)),
    ("Amazon / AWS", re.compile(r"\bAWS\b|\bAmazon Web Services\b|\bAmazon\b", re.I)),
    ("Manifest Law", re.compile(r"Manifest\s+Law|\bManifest\b", re.I)),
    ("Statsig", re.compile(r"\bStatsig\b", re.I)),
    ("Fireworks AI", re.compile(r"Fireworks\s*AI", re.I)),
]

TOPIC_PATTERNS = [
    ("visa_immigration", re.compile(r"\bH1B\b|\bH-1B\b|\bvisa\b|\bgreen card\b|\bUSCIS\b|\bOPT\b|\bCPT\b", re.I)),
    ("jobs_interviews", re.compile(r"\binterview\b|\brecruiter\b|\boffer\b|\bresume\b|\bLC\b|\bjob\b", re.I)),
    ("ai_ml", re.compile(r"\bAI\b|\bML\b|\bmachine learning\b|\bLLM\b|\bGPT\b|\bmodel\b", re.I)),
    ("data_analytics", re.compile(r"\bdata engineer\b|\bdata scientist\b|\bSQL\b|\banalytics\b|\bBI\b", re.I)),
    ("career_story", re.compile(r"\bI quit\b|\bI left\b|\bjoined\b|\bstarted\b|\bjourney\b|\bgrateful\b", re.I)),
    ("money_salary", re.compile(r"\$\d|\bsalary\b|\bcompensation\b|\bTC\b|\bpay\b", re.I)),
    ("creator_business", re.compile(r"\bsponsor\b|\bbrand\b|\bcourse\b|\bnewsletter\b|\bLuma\b|\blnkd\.in\b", re.I)),
]

STOP = frozenset(
    """
    a about after again all also am an and any are as at be because been before being
    below between both but by can could did do does doing done down during each few for from
    further get go going gone got had has have having he her here hers herself him himself his how
    i if in into is it its itself just like me more most much my myself no nor not now of off on
    once only or other our ours ourselves out over own same she should so some such than that the
    their them themselves then there these they this those through to too under until up very was
    we were what when where which while who whom why will with you your yours yourself yourselves
    year years month weeks week days day time today into about your this that have with from they
    them their what when were been being have some would could should might must will just like
    make made many much more most very also only even well back then here over such each both few
    than into through during before after above below between under again further once
    """.split()
)

TOKEN_RE = re.compile(r"[a-z]{4,}")


def is_plausible_english_token(w: str) -> bool:
    if len(w) < 4 or len(w) > 14:
        return False
    vowels = sum(1 for c in w if c in "aeiou")
    vr = vowels / len(w)
    if vr < 0.28 or vr > 0.62:
        return False
    streak = 0
    for c in w:
        streak = streak + 1 if c not in "aeiou" else 0
        if streak > 4:
            return False
    return True

PEER_FILES: list[tuple[str, str]] = [
    ("AIshwaraya.md", "Aishwarya Srinivasan"),
    ("Amney.md", "Amney Mounir"),
    ("Ruchi Bhatia.md", "Ruchi Bhatia"),
    ("Sohan Sethi.md", "Sohan Sethi"),
    ("Sundas Khalid.md", "Sundas Khalid"),
    ("Venkata.md", "Venkata Sai"),
    ("Vishaka.md", "Vishaka Sadhwani"),
]

PRITESH_FILE = "Yudi J.md"
PRITESH_NAME = "Pritesh Jagani (Yudi J / UDJ)"


def parse_int(s: str) -> int:
    return int(s.replace(",", "").strip())


def parse_engagement_line(line: str) -> tuple[int, int, int, int]:
    line = line.strip()
    sc_m = re.search(r"\(Score:\s*([\d,]+)\)", line)
    score = parse_int(sc_m.group(1)) if sc_m else 0
    rx_m = re.search(r"([\d,]+)\s*reactions", line)
    reactions = parse_int(rx_m.group(1)) if rx_m else 0
    cm_m = re.search(r"([\d,]+)\s*comments", line)
    comments = parse_int(cm_m.group(1)) if cm_m else 0
    rp_m = re.search(r"([\d,]+)\s*reposts", line)
    reposts = parse_int(rp_m.group(1)) if rp_m else 0
    return reactions, comments, reposts, score


def parse_date(s: str) -> datetime | None:
    s = s.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


@dataclass
class Post:
    file: str
    author: str
    date_raw: str
    date: datetime | None
    reactions: int
    comments: int
    reposts: int
    score: int
    media: str
    url: str
    body: str

    @property
    def hook(self) -> str:
        t = " ".join(self.body.split())
        return t[:300] + ("…" if len(t) > 300 else "")

    @property
    def len_chars(self) -> int:
        return len(self.body.strip())


def configure_window(days: int, anchor: datetime) -> None:
    """Set rolling window [anchor - days, anchor] inclusive by calendar date."""
    global WINDOW_DAYS, WINDOW_ANCHOR
    WINDOW_DAYS = max(1, int(days))
    WINDOW_ANCHOR = anchor


def window_start_end() -> tuple[datetime, datetime]:
    start = (WINDOW_ANCHOR - timedelta(days=WINDOW_DAYS)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = WINDOW_ANCHOR
    return start, end


def in_window(p: Post) -> bool:
    if p.date is None:
        return False
    ws, we = window_start_end()
    return ws.date() <= p.date.date() <= we.date()


def parse_file(path: Path) -> tuple[list[Post], dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta: dict = {"file": path.name}
    m = EXPORTED.search(text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        meta["exported"] = f"{y}-{mo:02d}-{d:02d}"
    pm = PAGE.search(text)
    if pm:
        meta["page"] = pm.group(1)

    posts: list[Post] = []
    for blk in POST_BLOCK.finditer(text):
        d = parse_date(blk.group("date"))
        rx, cm, rp, sc = parse_engagement_line(blk.group("eng"))
        body = blk.group("body").strip()
        posts.append(
            Post(
                file=path.name,
                author=blk.group("author").strip(),
                date_raw=blk.group("date").strip(),
                date=d,
                reactions=rx,
                comments=cm,
                reposts=rp,
                score=sc,
                media=blk.group("media").strip(),
                url=blk.group("url").strip(),
                body=body,
            )
        )
    meta["posts_parsed"] = len(posts)
    return posts, meta


def topic_hits(body: str) -> list[str]:
    return [name for name, pat in TOPIC_PATTERNS if pat.search(body)]


def brand_hits(body: str) -> list[str]:
    return [name for name, pat in BRAND_PATTERNS if pat.search(body)]


def median(vals: list[int]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2


def summarize(xs: list[Post]) -> dict:
    if not xs:
        return {
            "n": 0,
            "median_reactions": 0.0,
            "median_comments": 0.0,
            "median_reposts": 0.0,
            "median_score": 0.0,
            "mean_reactions": 0.0,
            "mean_comments": 0.0,
            "mean_reposts": 0.0,
            "median_body_chars": 0.0,
            "mean_body_chars": 0.0,
            "comments_per_1k_rx": 0.0,
            "reposts_per_1k_rx": 0.0,
            "share_rx_ge_500": 0.0,
            "share_rx_ge_1000": 0.0,
            "max_reactions": 0,
            "max_comments": 0,
            "media_mix": {},
            "topic_posts": {},
            "brand_mentions_posts": {},
        }
    rx = [p.reactions for p in xs]
    cm = [p.comments for p in xs]
    rp = [p.reposts for p in xs]
    sc = [p.score for p in xs]
    lens = [p.len_chars for p in xs]
    media = Counter(p.media for p in xs)
    topics = Counter()
    brands = Counter()
    for p in xs:
        for t in topic_hits(p.body):
            topics[t] += 1
        for b in brand_hits(p.body):
            brands[b] += 1
    return {
        "n": len(xs),
        "median_reactions": median(rx),
        "median_comments": median(cm),
        "median_reposts": median(rp),
        "median_score": median(sc),
        "mean_reactions": sum(rx) / len(rx),
        "mean_comments": sum(cm) / len(cm),
        "mean_reposts": sum(rp) / len(rp),
        "median_body_chars": median(lens),
        "mean_body_chars": sum(lens) / len(lens),
        "comments_per_1k_rx": (sum(cm) / sum(rx) * 1000) if sum(rx) else 0,
        "reposts_per_1k_rx": (sum(rp) / sum(rx) * 1000) if sum(rx) else 0,
        "share_rx_ge_500": sum(1 for x in rx if x >= 500) / len(rx),
        "share_rx_ge_1000": sum(1 for x in rx if x >= 1000) / len(rx),
        "max_reactions": max(rx),
        "max_comments": max(cm),
        "media_mix": dict(media.most_common()),
        "topic_posts": dict(topics.most_common()),
        "brand_mentions_posts": dict(brands.most_common()),
    }


def window_posts(posts: list[Post]) -> list[Post]:
    return [p for p in posts if in_window(p)]


def top_by(posts: list[Post], key: str, k: int) -> list[Post]:
    xs = window_posts(posts)
    if key == "comments":
        xs.sort(key=lambda p: (p.comments, p.score), reverse=True)
    elif key == "reposts":
        xs.sort(key=lambda p: (p.reposts, p.score), reverse=True)
    elif key == "score":
        xs.sort(key=lambda p: (p.score, p.comments), reverse=True)
    else:
        raise ValueError(key)
    out: list[Post] = []
    seen: set[str] = set()
    for p in xs:
        if p.url in seen:
            continue
        seen.add(p.url)
        out.append(p)
        if len(out) >= k:
            break
    return out


def top_by_global(posts: list[Post], key: str, k: int) -> list[Post]:
    """Same as top_by but across all exported posts (ignores date window)."""
    xs = list(posts)
    if key == "comments":
        xs.sort(key=lambda p: (p.comments, p.score), reverse=True)
    elif key == "reposts":
        xs.sort(key=lambda p: (p.reposts, p.score), reverse=True)
    elif key == "score":
        xs.sort(key=lambda p: (p.score, p.comments), reverse=True)
    else:
        raise ValueError(key)
    out: list[Post] = []
    seen: set[str] = set()
    for p in xs:
        if p.url in seen:
            continue
        seen.add(p.url)
        out.append(p)
        if len(out) >= k:
            break
    return out


def first_exemplar_post(posts: list[Post]) -> tuple[Post | None, str]:
    """Best comment post in-window, else best outside window (full export)."""
    w = top_by(posts, "comments", 1)
    if w:
        return w[0], "in-window"
    g = top_by_global(posts, "comments", 1)
    if g:
        return g[0], "fallback-full-export"
    return None, "none"


def word_freq_and_docfreq(
    posts: list[Post],
) -> tuple[Counter[str], Counter[str]]:
    """Term frequency and document frequency (posts containing token)."""
    tf: Counter[str] = Counter()
    df: Counter[str] = Counter()
    for p in posts:
        seen: set[str] = set()
        for w in TOKEN_RE.findall(p.body.lower()):
            if w in STOP or not is_plausible_english_token(w):
                continue
            tf[w] += 1
            seen.add(w)
        for w in seen:
            df[w] += 1
    return tf, df


def distinctive_words(
    self_posts: list[Post], other_peer_posts: list[Post], max_words: int = 14
) -> list[tuple[str, float]]:
    sf, sdf = word_freq_and_docfreq(self_posts)
    of, _odf = word_freq_and_docfreq(other_peer_posts)
    sum_s = sum(sf.values()) or 1
    sum_o = sum(of.values()) or 1
    min_docs = 2 if len(self_posts) >= 12 else 1
    ranked: list[tuple[float, str]] = []
    for w, cnt in sf.items():
        if sdf[w] < min_docs:
            continue
        if cnt < max(6, min(14, len(self_posts) // 3)):
            continue
        lift = (cnt / sum_s) / (of.get(w, 0) / sum_o + 1e-9)
        # Short tokens with absurd lift are usually Unicode-mangled artifacts.
        if len(w) <= 5 and lift > 800:
            continue
        ranked.append((lift, w))
    ranked.sort(reverse=True)
    return [(w, round(lift, 2)) for lift, w in ranked[:max_words]]


def esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ").strip()


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for r in rows:
        lines.append("| " + " | ".join(esc(str(c)) for c in r) + " |")
    return "\n".join(lines)


def load_all(data_dir: Path) -> tuple[dict[str, list[Post]], dict[str, dict], list[Post]]:
    peer_by: dict[str, list[Post]] = {}
    metas: dict[str, dict] = {}
    all_peer: list[Post] = []
    for fn, _ in PEER_FILES:
        path = data_dir / fn
        if not path.exists():
            raise FileNotFoundError(f"Missing export: {path}")
        posts, meta = parse_file(path)
        peer_by[fn] = posts
        metas[fn] = meta
        all_peer.extend(posts)
    pj_path = data_dir / PRITESH_FILE
    if not pj_path.exists():
        raise FileNotFoundError(f"Missing export: {pj_path}")
    pritesh, meta_p = parse_file(pj_path)
    metas[PRITESH_FILE] = meta_p
    return peer_by, metas, pritesh


def build_report(data_dir: Path) -> str:
    peer_by, metas, pritesh = load_all(data_dir)
    pj_w = window_posts(pritesh)
    peers_w = window_posts([p for posts in peer_by.values() for p in posts])

    lines: list[str] = []
    L = lines.append

    L("# Pritesh Jagani (Yudi J / UDJ) — multi-creator LinkedIn audit")
    L("")
    L("This report is **machine-generated** from bulk caption exports so every creator is scored with the **same rubric**. ")
    L(
        f"**Time window:** last **{WINDOW_DAYS}** days — `{window_start_end()[0].date()}` through `{window_start_end()[1].date()}` (inclusive by post date)."
    )
    L("")
    L("---")
    L("")
    L("## 1. Executive read (non-repetitive)")
    L("")
    agg_peers = summarize(peers_w)
    sm_p = summarize(pj_w)
    L(
        f"- **Volume in window:** {agg_peers['n']} peer posts vs **{sm_p['n']}** Pritesh posts."
    )
    L(
        f"- **Typical post strength:** peer median **{agg_peers['median_reactions']:.0f}** reactions / **{agg_peers['median_comments']:.0f}** comments vs Pritesh **{sm_p['median_reactions']:.0f}** / **{sm_p['median_comments']:.0f}** — Pritesh has elite spikes but a thinner mid-tail."
    )
    L(
        f"- **Shareability:** peers **{agg_peers['reposts_per_1k_rx']:.1f}** reposts per 1k reactions vs Pritesh **{sm_p['reposts_per_1k_rx']:.1f}**."
    )
    L(
        "- **Lane:** peers collectively skew **AI / data / cloud-native vocabulary** in distinctive terms (see §4); Pritesh skews **visa + jobseeker** language in raw topic heuristics — use §4.8 for his own distinctive terms."
    )
    L(
        "- **Six-post plan (§7)** deliberately assigns **six different creators** as the primary pattern owner so the sprint is not anchored on a single peer."
    )
    L("")
    L("---")
    L("")
    L("## 2. Profiles (from export headers)")
    L("")
    prof_rows = []
    for fn, display in PEER_FILES:
        prof_rows.append([display, metas[fn].get("page", ""), str(len(window_posts(peer_by[fn]))), metas[fn].get("exported", "")])
    prof_rows.append(
        [
            PRITESH_NAME,
            metas[PRITESH_FILE].get("page", ""),
            str(len(pj_w)),
            metas[PRITESH_FILE].get("exported", ""),
        ]
    )
    L(md_table(["Creator", "Profile URL", "Posts in window", "Export date"], prof_rows))
    L("")
    L("---")
    L("")
    L("## 3. Window aggregates (single comparison table)")
    L("")
    rows = [
        [
            "Peers (7 combined)",
            f"{agg_peers['n']}",
            f"{agg_peers['median_reactions']:.0f}",
            f"{agg_peers['median_comments']:.0f}",
            f"{agg_peers['reposts_per_1k_rx']:.1f}",
            f"{agg_peers['comments_per_1k_rx']:.1f}",
            ", ".join(f"{k} {v}" for k, v in list(agg_peers["media_mix"].items())[:4]),
        ],
        [
            "Pritesh",
            f"{sm_p['n']}",
            f"{sm_p['median_reactions']:.0f}",
            f"{sm_p['median_comments']:.0f}",
            f"{sm_p['reposts_per_1k_rx']:.1f}",
            f"{sm_p['comments_per_1k_rx']:.1f}",
            ", ".join(f"{k} {v}" for k, v in list(sm_p["media_mix"].items())[:4]),
        ],
    ]
    L(
        md_table(
            [
                "Cohort",
                "n",
                "Med rx",
                "Med cm",
                "Rp/1k rx",
                "Cm/1k rx",
                "Media mix",
            ],
            rows,
        )
    )
    L("")
    L("---")
    L("")
    L("## 4. One subsection per peer (same structure for everyone)")
    L("")

    # Precompute "other" corpus for distinctiveness per file
    for idx, (fn, display) in enumerate(PEER_FILES, start=1):
        posts = peer_by[fn]
        w = window_posts(posts)
        others = [p for p in peers_w if p.file != fn]
        dist = distinctive_words(w, others)
        sm = summarize(w)
        meta = metas[fn]

        L(f"### 4.{idx} {display} (`{fn}`)")
        L("")
        L(f"- **Profile:** {meta.get('page', '')}")
        L(
            f"- **Medians:** {sm['median_reactions']:.0f} reactions · {sm['median_comments']:.0f} comments · {sm['median_reposts']:.0f} reposts · score {sm['median_score']:.0f}"
        )
        L(
            f"- **Means:** {sm['mean_reactions']:.1f} rx · {sm['mean_comments']:.1f} cm · reposts/1k rx **{sm['reposts_per_1k_rx']:.1f}**"
        )
        L(
            "- **Heuristic topics (post counts, non-exclusive):** "
            + ", ".join(f"{k} **{v}**" for k, v in sm["topic_posts"].items())
        )
        if sm["brand_mentions_posts"]:
            L(
                "- **Heuristic brand mentions:** "
                + ", ".join(f"{k} **{v}**" for k, v in list(sm["brand_mentions_posts"].items())[:10])
            )
        if dist:
            L(
                "- **Vocabulary more concentrated here than other peers (lift × token):** "
                + ", ".join(f"**{w}** ({lift})" for w, lift in dist)
            )
        L("")
        L("**Five highest-comment posts (deduped URLs):**")
        L("")
        for i, p in enumerate(top_by(posts, "comments", 5), 1):
            L(f"{i}. [{p.date_raw} — {p.comments} comments, {p.reactions} rx]({p.url})")
            L(f"   - {esc(p.hook)}")
        L("")
        L(
            "**One-line positioning (from corpus, not flattery):** "
            + _one_line_positioning(fn, sm, dist)
        )
        L("")
        L("---")
        L("")

    # Pritesh deep dive as 4.8
    L(f"### 4.{len(PEER_FILES) + 1} {PRITESH_NAME} (`{PRITESH_FILE}`)")
    others_all = peers_w
    dist_p = distinctive_words(pj_w, others_all)
    L("")
    L(f"- **Profile:** {metas[PRITESH_FILE].get('page', '')}")
    L(
        f"- **Medians:** {sm_p['median_reactions']:.0f} reactions · {sm_p['median_comments']:.0f} comments · {sm_p['median_reposts']:.0f} reposts"
    )
    L(
        "- **Heuristic topics:** "
        + ", ".join(f"{k} **{v}**" for k, v in sm_p["topic_posts"].items())
    )
    if sm_p["brand_mentions_posts"]:
        L(
            "- **Heuristic brand mentions:** "
            + ", ".join(f"{k} **{v}**" for k, v in list(sm_p["brand_mentions_posts"].items())[:12])
        )
    if dist_p:
        L(
            "- **Distinctive vs all peers:** "
            + ", ".join(f"**{w}** ({lift})" for w, lift in dist_p)
        )
    L("")
    L("**Five highest-comment posts:**")
    L("")
    for i, p in enumerate(top_by(pritesh, "comments", 5), 1):
        L(f"{i}. [{p.date_raw} — {p.comments} comments, {p.reactions} rx]({p.url})")
        L(f"   - {esc(p.hook)}")
    L("")
    L("---")
    L("")
    L("## 5. Pritesh vs each peer (three bullets each, data-backed)")
    L("")
    for fn, display in PEER_FILES:
        w_peer = window_posts(peer_by[fn])
        sm_peer = summarize(w_peer)
        L(f"### vs {display}")
        L(_three_bullets_compare(sm_p, sm_peer, display))
        L("")
    L("---")
    L("")
    L("## 6. Topic counts per creator (heuristic, non-exclusive)")
    L("")
    for fn, display in PEER_FILES:
        sm = summarize(window_posts(peer_by[fn]))
        tp = sm.get("topic_posts", {})
        top3 = sorted(tp.items(), key=lambda x: -x[1])[:3]
        L(f"- **{display}:** " + "; ".join(f"{k} ({v})" for k, v in top3))
    L("")
    L(
        "- **Pritesh:** "
        + "; ".join(
            f"{k} ({v})"
            for k, v in sorted(sm_p["topic_posts"].items(), key=lambda x: -x[1])[:5]
        )
    )
    L("")
    L("---")
    L("")
    L("## 7. Six-post sprint — **six different creators**, six patterns, six URLs")
    L("")
    L(
        "Sundas Khalid is **fully analyzed in §4.5** like every other peer; she is **not** the default template below. "
        "Rotate her formats in week 2 if comments plateau."
    )
    L("")
    # Six-post owners: explicitly exclude Sundas so the sprint is not anchored on one voice.
    rows6 = []
    patterns = [
        ("AIshwaraya.md", "Milestone / ecosystem pulse (funding, launch, conference)", "Ship one **company- or community-scale** update with named partners."),
        ("Amney.md", "Contrarian DA take + repost gravity", "Pick one contrarian **job-market mechanics** take for intl SWE; ask for reposts only if readers agree."),
        ("Ruchi Bhatia.md", "Credential ladder + named institutions", "Stack **proof objects** (offer, project, talk) in one post — fewer adjectives, more receipts."),
        ("Sohan Sethi.md", "Save/repost cheatsheet frame", "One **carousel** with a titled framework (interview system, not generic tips)."),
        ("Venkata.md", "Product narrative (“I built X that does Y in Z seconds”)", "Show **one** workflow demo (tooling + screen) for a narrow ICP."),
        ("Vishaka.md", "Comment-gated resource / employer badge energy", "One **free artifact** with comments as distribution; tie to your offer without spamming links."),
    ]
    for i, (fn, pat, remix) in enumerate(patterns, 1):
        p0, src = first_exemplar_post(peer_by[fn])
        ex = f"[exemplar]({p0.url})" if p0 else "—"
        if p0 and src != "in-window":
            ex += " *(outside 90d window — full export)*"
        rows6.append([str(i), display_for(fn), pat, ex, remix])

    L(
        md_table(
            ["#", "Pattern owner", "Pattern", "Primary exemplar (highest comments in window)", "Pritesh remix (original)"],
            rows6,
        )
    )
    L("")
    L("---")
    L("")
    L("## 8. Regenerate")
    L("")
    L("```bash")
    L("python3 audit_report.py --data /path/to/exports --days 90 --format md -o out/REPORT.md")
    L("python3 audit_report.py --data /path/to/exports --days 90 --format html -o out/REPORT.html")
    L("```")
    L("")
    return "\n".join(lines)


def display_for(fn: str) -> str:
    for f, d in PEER_FILES:
        if f == fn:
            return d
    return fn


def _one_line_positioning(fn: str, sm: dict, dist: list[tuple[str, float]]) -> str:
    topics = sm.get("topic_posts", {})
    top_t = max(topics, key=topics.get) if topics else "mixed"
    if fn == "AIshwaraya.md":
        return f"AI + builder milestones with public proof; strongest heuristic bucket **{top_t}**."
    if fn == "Amney.md":
        return "Data analyst career operator with funnels (Luma/lnkd.in) and contrarian DA hooks."
    if fn == "Ruchi Bhatia.md":
        return "AI + cloud product credibility via institutions and competition math; fewer posts, higher peaks."
    if fn == "Sohan Sethi.md":
        return "Data analytics education + cheatsheets; visa posts spike comments occasionally."
    if fn == "Sundas Khalid.md":
        return "BigTech + AI tools + lifestyle/career transitions; strong on **newsy hooks** and binary debates."
    if fn == "Venkata.md":
        return "Product-led posts (agents, resume tools) with extremely high comment gravity on demos."
    if fn == "Vishaka.md":
        return "Employer badge moments + large giveaways; NVIDIA join post is a category beacon."
    return f"Primary heuristic topic cluster: **{top_t}**."


def _three_bullets_compare(
    sm_p: dict, sm_peer: dict, display: str
) -> str:
    lines = []
    lines.append(
        f"- **Baseline:** median reactions **{sm_p['median_reactions']:.0f}** (PJ) vs **{sm_peer['median_reactions']:.0f}** ({display}) over n={sm_p['n']} vs {sm_peer['n']}."
    )
    # topic contrast: top topic each
    def top_key(d: dict) -> str:
        tp = d.get("topic_posts", {})
        return max(tp, key=tp.get) if tp else "n/a"

    lines.append(
        f"- **Topic center of mass:** Pritesh **{top_key(sm_p)}** vs {display} **{top_key(sm_peer)}** (heuristic tags; not mutually exclusive)."
    )
    # repost culture
    lines.append(
        f"- **Share loop:** reposts/1k rx **{sm_p['reposts_per_1k_rx']:.1f}** (PJ) vs **{sm_peer['reposts_per_1k_rx']:.1f}** ({display})."
    )
    return "\n".join(lines)


def _he(x: object) -> str:
    return html.escape(str(x), quote=True)


def _table(headers: list[str], rows: list[list[object]], table_class: str = "data") -> str:
    th = "".join(f"<th>{_he(h)}</th>" for h in headers)
    body = []
    for row in rows:
        cells = []
        for c in row:
            if isinstance(c, str) and c.strip().startswith("<"):
                cells.append(f"<td>{c}</td>")
            else:
                cells.append(f"<td>{_he(c)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f'<table class="{table_class}"><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def _link(url: str, label: str = "Open post") -> str:
    u = _he(url)
    return f'<a href="{u}" target="_blank" rel="noopener noreferrer">{_he(label)}</a>'


def _topic_keys() -> list[str]:
    return [name for name, _ in TOPIC_PATTERNS]


def _brand_columns(peer_by: dict, metas: dict, pritesh: list[Post]) -> list[str]:
    totals: Counter[str] = Counter()
    for fn, _ in PEER_FILES:
        sm = summarize(window_posts(peer_by[fn]))
        for k, v in sm.get("brand_mentions_posts", {}).items():
            totals[k] += v
    sm = summarize(window_posts(pritesh))
    for k, v in sm.get("brand_mentions_posts", {}).items():
        totals[k] += v
    return [b for b, _ in totals.most_common(14)]


def build_html_report(data_dir: Path) -> str:
    peer_by, metas, pritesh = load_all(data_dir)
    pj_w = window_posts(pritesh)
    peers_w = window_posts([p for posts in peer_by.values() for p in posts])
    ws, we = window_start_end()
    agg = summarize(peers_w)
    sm_p = summarize(pj_w)

    topic_cols = _topic_keys()
    brand_cols = _brand_columns(peer_by, metas, pritesh)

    def creator_metric_row(label: str, sm: dict) -> list[object]:
        mm = sm.get("media_mix") or {}
        mix = ", ".join(f"{k} {v}" for k, v in list(mm.items())[:5]) or "—"
        return [
            label,
            sm["n"],
            f"{sm['median_reactions']:.0f}",
            f"{sm['mean_reactions']:.1f}",
            f"{100 * sm['share_rx_ge_500']:.1f}%",
            f"{100 * sm['share_rx_ge_1000']:.1f}%",
            f"{sm['median_comments']:.0f}",
            f"{sm['reposts_per_1k_rx']:.1f}",
            f"{sm['comments_per_1k_rx']:.1f}",
            sm["max_reactions"],
            sm["max_comments"],
            mix,
        ]

    cohort_headers = [
        "Creator",
        "Posts (n)",
        "Med. rx",
        "Mean rx",
        "≥500 rx",
        "≥1k rx",
        "Med. cm",
        "Rp/1k rx",
        "Cm/1k rx",
        "Max rx",
        "Max cm",
        "Media mix",
    ]
    cohort_rows = []
    for fn, display in PEER_FILES:
        sm = summarize(window_posts(peer_by[fn]))
        cohort_rows.append(creator_metric_row(display, sm))
    cohort_rows.append(creator_metric_row(PRITESH_NAME, sm_p))

    topic_header = ["Creator"] + topic_cols
    topic_rows: list[list[object]] = []
    for fn, display in PEER_FILES:
        sm = summarize(window_posts(peer_by[fn]))
        tp = sm.get("topic_posts", {})
        topic_rows.append([display] + [tp.get(t, 0) for t in topic_cols])
    tp = sm_p.get("topic_posts", {})
    topic_rows.append([PRITESH_NAME] + [tp.get(t, 0) for t in topic_cols])

    brand_header = ["Creator"] + brand_cols
    brand_rows: list[list[object]] = []
    for fn, display in PEER_FILES:
        sm = summarize(window_posts(peer_by[fn]))
        bp = sm.get("brand_mentions_posts", {})
        brand_rows.append([display] + [bp.get(b, 0) for b in brand_cols])
    bp = sm_p.get("brand_mentions_posts", {})
    brand_rows.append([PRITESH_NAME] + [bp.get(b, 0) for b in brand_cols])

    def peer_compare_rows() -> list[list[object]]:
        out = []
        for fn, display in PEER_FILES:
            sm = summarize(window_posts(peer_by[fn]))
            out.append(
                [
                    display,
                    f"{sm_p['median_reactions']:.0f} vs {sm['median_reactions']:.0f}",
                    f"{sm_p['median_comments']:.0f} vs {sm['median_comments']:.0f}",
                    f"{100 * sm_p['share_rx_ge_500']:.1f}% vs {100 * sm['share_rx_ge_500']:.1f}%",
                    f"{sm_p['reposts_per_1k_rx']:.1f} vs {sm['reposts_per_1k_rx']:.1f}",
                ]
            )
        return out

    sections: list[str] = []

    def sec(sid: str, title: str, inner: str) -> None:
        sections.append(f'<section id="{_he(sid)}"><h2>{_he(title)}</h2>{inner}</section>')

    sec(
        "overview",
        "Executive snapshot (last " + str(WINDOW_DAYS) + " days)",
        "<p>Aggregates below are computed from the same export files for every creator. "
        "Heuristic topics and brands can overlap within a single post.</p>"
        + _table(
            ["Metric", "Peers (7)", PRITESH_NAME.split("(")[0].strip()],
            [
                ["Posts in window", agg["n"], sm_p["n"]],
                ["Median reactions", f"{agg['median_reactions']:.0f}", f"{sm_p['median_reactions']:.0f}"],
                ["Median comments", f"{agg['median_comments']:.0f}", f"{sm_p['median_comments']:.0f}"],
                ["Reposts / 1k rx", f"{agg['reposts_per_1k_rx']:.1f}", f"{sm_p['reposts_per_1k_rx']:.1f}"],
                ["Comments / 1k rx", f"{agg['comments_per_1k_rx']:.1f}", f"{sm_p['comments_per_1k_rx']:.1f}"],
                ["Share of posts with ≥500 rx", f"{100 * agg['share_rx_ge_500']:.1f}%", f"{100 * sm_p['share_rx_ge_500']:.1f}%"],
                ["Share of posts with ≥1000 rx", f"{100 * agg['share_rx_ge_1000']:.1f}%", f"{100 * sm_p['share_rx_ge_1000']:.1f}%"],
            ],
        ),
    )

    roster = []
    for fn, display in PEER_FILES:
        page = metas[fn].get("page", "")
        n = len(window_posts(peer_by[fn]))
        roster.append(
            [
                display,
                _link(page, page.replace("https://", "")) if page else "—",
                n,
                metas[fn].get("exported", "—"),
                fn,
            ]
        )
    page = metas[PRITESH_FILE].get("page", "")
    roster.append(
        [
            PRITESH_NAME,
            _link(page, page.replace("https://", "")) if page else "—",
            len(pj_w),
            metas[PRITESH_FILE].get("exported", "—"),
            PRITESH_FILE,
        ]
    )
    sec(
        "roster",
        "Creator roster & source files",
        _table(["Display name", "Profile URL", "Posts in window", "Export date", "File"], roster),
    )

    sec(
        "cohort-matrix",
        "Full metrics matrix (click-through column)",
        "<p>Compare baseline strength and “viral tail” (share of posts crossing reaction thresholds).</p>"
        + _table(cohort_headers, cohort_rows),
    )

    sec(
        "topics",
        "Heuristic topic counts by creator",
        "<p>Columns are regex-based tags; one post can increment multiple columns.</p>"
        + _table(topic_header, topic_rows),
    )

    sec(
        "brands",
        "Heuristic brand / vendor mentions (top signals across corpus)",
        "<p>Columns are the 14 most frequent brand keywords across all peers + Pritesh in this window. "
        "“Manifest” may include non-law uses; interpret in context.</p>"
        + _table(brand_header, brand_rows),
    )

    sec(
        "pritesh-vs-peers",
        "Pritesh vs each peer (same window)",
        _table(
            ["Peer", "Median rx (PJ vs peer)", "Median cm", "Share ≥500 rx", "Reposts/1k rx"],
            peer_compare_rows(),
        ),
    )

    patterns = [
        ("AIshwaraya.md", "Milestone / ecosystem pulse", "One company/community milestone with named partners."),
        ("Amney.md", "Contrarian DA + repost gravity", "Contrarian job-market mechanic for intl SWE + repost ask."),
        ("Ruchi Bhatia.md", "Credential ladder", "Proof-stack post: offers, talks, institutions."),
        ("Sohan Sethi.md", "Cheatsheet / save frame", "One titled carousel for interview system."),
        ("Venkata.md", "Product demo narrative", "One workflow demo for narrow ICP."),
        ("Vishaka.md", "Comment-gated resource", "Free artifact; comments as distribution."),
    ]
    six_rows = []
    for i, (fn, pat, remix) in enumerate(patterns, 1):
        p0, src = first_exemplar_post(peer_by[fn])
        if p0 is None:
            six_rows.append([i, display_for(fn), pat, "—", remix])
            continue
        lbl = "LinkedIn post" if src == "in-window" else "LinkedIn (best in full export — outside 90d)"
        six_rows.append([i, display_for(fn), pat, _link(p0.url, lbl), remix])
    sec(
        "six-posts",
        "Six-post sprint (six different exemplar owners)",
        "<p>Sundas Khalid is analyzed in her own section below; she is not duplicated here so the grid stays diverse.</p>"
        + _table(["#", "Pattern owner", "Pattern", "Top-comment exemplar", "Pritesh remix"], six_rows),
    )

    for idx, (fn, display) in enumerate(PEER_FILES, start=1):
        posts = peer_by[fn]
        w = window_posts(posts)
        others = [p for p in peers_w if p.file != fn]
        dist = distinctive_words(w, others)
        sm = summarize(w)
        dist_txt = ", ".join(f"{w} ({lift})" for w, lift in dist[:10]) if dist else "—"
        top_posts = top_by(posts, "comments", 15)
        note = ""
        if not top_posts:
            note = "<p class='warn'><strong>Note:</strong> No posts dated inside the 90-day window for this account in the export. "
            note += "The table below uses the <strong>full export</strong> ranked by comments.</p>"
            top_posts = top_by_global(posts, "comments", 15)
        pr = []
        for rank, p in enumerate(top_posts, 1):
            pr.append(
                [
                    rank,
                    p.date_raw,
                    p.reactions,
                    p.comments,
                    p.reposts,
                    p.score,
                    p.media,
                    _link(p.url, "View"),
                    _he(p.hook[:420]),
                ]
            )
        inner = (
            note
            + f"<p><strong>Profile:</strong> {_link(metas[fn]['page'], metas[fn]['page']) if metas[fn].get('page') else '—'}</p>"
            f"<p><strong>Distinctive vocabulary</strong> (lift vs other peers): {_he(dist_txt)}</p>"
            + _table(
                ["Metric", "Value"],
                [
                    ["Posts (n)", sm["n"]],
                    ["Median reactions", f"{sm['median_reactions']:.0f}"],
                    ["Median comments", f"{sm['median_comments']:.0f}"],
                    ["Median reposts", f"{sm['median_reposts']:.0f}"],
                    ["Mean reactions", f"{sm['mean_reactions']:.1f}"],
                    ["Mean comments", f"{sm['mean_comments']:.1f}"],
                    ["Reposts / 1k rx", f"{sm['reposts_per_1k_rx']:.1f}"],
                    ["Comments / 1k rx", f"{sm['comments_per_1k_rx']:.1f}"],
                    ["Posts ≥500 rx", f"{100 * sm['share_rx_ge_500']:.1f}%"],
                    ["Posts ≥1000 rx", f"{100 * sm['share_rx_ge_1000']:.1f}%"],
                    ["Positioning read", _one_line_positioning(fn, sm, dist)],
                ],
                "kv",
            )
            + "<h3>Top posts by comments (deduped URLs)</h3>"
            + _table(
                ["#", "Date", "Rx", "Cm", "Rp", "Score", "Media", "Link", "Hook (preview)"],
                pr,
            )
        )
        sid = f"creator-{idx}-{fn.replace('.', '').replace(' ', '-').lower()}"
        sec(sid, f"{idx}. {display}", inner)

    # Pritesh section
    others_all = peers_w
    dist_p = distinctive_words(pj_w, others_all)
    dist_txt_p = ", ".join(f"{w} ({lift})" for w, lift in dist_p[:12]) if dist_p else "—"
    top_p = top_by(pritesh, "comments", 15)
    note_p = ""
    if not top_p:
        note_p = "<p class='warn'><strong>Note:</strong> No Pritesh posts in the 90-day window; showing full-export leaders.</p>"
        top_p = top_by_global(pritesh, "comments", 15)
    pr_rows = []
    for rank, p in enumerate(top_p, 1):
        pr_rows.append(
            [
                rank,
                p.date_raw,
                p.reactions,
                p.comments,
                p.reposts,
                p.score,
                p.media,
                _link(p.url, "View"),
                _he(p.hook[:420]),
            ]
        )
    sec(
        "creator-pritesh",
        f"{len(PEER_FILES) + 1}. {PRITESH_NAME}",
        (
            note_p
            + f"<p><strong>Profile:</strong> {_link(metas[PRITESH_FILE]['page'], metas[PRITESH_FILE]['page']) if metas[PRITESH_FILE].get('page') else '—'}</p>"
            f"<p><strong>Distinctive vocabulary vs all peers:</strong> {_he(dist_txt_p)}</p>"
            + _table(
                ["Metric", "Value"],
                [
                    ["Posts (n)", sm_p["n"]],
                    ["Median reactions", f"{sm_p['median_reactions']:.0f}"],
                    ["Median comments", f"{sm_p['median_comments']:.0f}"],
                    ["Median reposts", f"{sm_p['median_reposts']:.0f}"],
                    ["Mean reactions", f"{sm_p['mean_reactions']:.1f}"],
                    ["Mean comments", f"{sm_p['mean_comments']:.1f}"],
                    ["Reposts / 1k rx", f"{sm_p['reposts_per_1k_rx']:.1f}"],
                    ["Comments / 1k rx", f"{sm_p['comments_per_1k_rx']:.1f}"],
                    ["Posts ≥500 rx", f"{100 * sm_p['share_rx_ge_500']:.1f}%"],
                    ["Posts ≥1000 rx", f"{100 * sm_p['share_rx_ge_1000']:.1f}%"],
                ],
                "kv",
            )
            + "<h3>Top posts by comments</h3>"
            + _table(["#", "Date", "Rx", "Cm", "Rp", "Score", "Media", "Link", "Hook (preview)"], pr_rows)
        ),
    )

    nav_items = [
        ("overview", "Overview"),
        ("roster", "Roster"),
        ("cohort-matrix", "Metrics matrix"),
        ("topics", "Topics"),
        ("brands", "Brands"),
        ("pritesh-vs-peers", "PJ vs peers"),
        ("six-posts", "Six-post plan"),
    ]
    for idx, (fn, display) in enumerate(PEER_FILES, start=1):
        sid = f"creator-{idx}-{fn.replace('.', '').replace(' ', '-').lower()}"
        nav_items.append((sid, display))
    nav_items.append(("creator-pritesh", "Pritesh"))

    nav = "<ul>" + "".join(f'<li><a href="#{_he(s)}">{_he(t)}</a></li>' for s, t in nav_items) + "</ul>"

    css = """
    :root { --bg:#0f1419; --card:#1a2332; --text:#e7ecf3; --muted:#9fb0c3; --accent:#5b9bd5; --border:#2d3a4d; }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: var(--bg); color: var(--text); margin:0; line-height:1.55; }
    .wrap { max-width: 1180px; margin: 0 auto; padding: 24px 20px 80px; }
    header { border-bottom: 1px solid var(--border); margin-bottom: 28px; padding-bottom: 20px; }
    h1 { font-size: 1.75rem; margin: 0 0 8px; }
    h2 { font-size: 1.25rem; margin-top: 36px; color: #cfe0f5; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
    h3 { font-size: 1.05rem; margin-top: 20px; color: #b8cce0; }
    p { color: var(--muted); max-width: 95ch; }
    nav ul { list-style: none; padding: 0; margin: 16px 0 0; display: flex; flex-wrap: wrap; gap: 8px 14px; }
    nav a { color: var(--accent); text-decoration: none; }
    nav a:hover { text-decoration: underline; }
    table.data { width: 100%; border-collapse: collapse; font-size: 0.88rem; margin: 16px 0 28px; background: var(--card); border-radius: 8px; overflow: hidden; }
    table.data th, table.data td { border: 1px solid var(--border); padding: 8px 10px; vertical-align: top; }
    table.data thead th { background: #243044; text-align: left; position: sticky; top: 0; z-index: 1; }
    table.data tbody tr:nth-child(even) { background: #151d28; }
    table.kv { max-width: 560px; }
    a { color: var(--accent); }
    code { background: #243044; padding: 2px 6px; border-radius: 4px; }
    .warn { color: #f0c674; }
    """

    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>UDJ / Pritesh — {WINDOW_DAYS}-day LinkedIn audit</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<header>
<h1>Pritesh Jagani (Yudi J / UDJ) — LinkedIn multi-creator audit</h1>
<p><strong>Window:</strong> last <code>{WINDOW_DAYS}</code> days, post dates <code>{ws.date()}</code> → <code>{we.date()}</code> inclusive.</p>
<p><strong>Generated:</strong> {gen} · Source: bulk caption exports in <code>{_he(data_dir)}</code></p>
<nav>{nav}</nav>
</header>
{"".join(sections)}
<footer>
<p>Engagement numbers are snapshots from the export files, not live LinkedIn. Topic/brand columns use heuristics. For questions about methodology, see <code>audit_report.py</code> in this repository.</p>
</footer>
</div>
</body>
</html>"""
    return doc


def parse_anchor_date(s: str) -> datetime:
    y, m, d = s.strip().split("-")
    return datetime(int(y), int(m), int(d), 23, 59, 59)


def anchor_datetime(s: str) -> datetime:
    """Window end: inclusive end of calendar day. Use host 'today' or YYYY-MM-DD."""
    key = (s or "today").strip().lower()
    if key in ("today", "now"):
        return datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)
    return parse_anchor_date(s)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate LinkedIn multi-creator audit (Markdown or HTML).",
    )
    ap.add_argument(
        "--data",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Directory containing the .md export files",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output file (.html or .md)",
    )
    ap.add_argument(
        "--days",
        type=int,
        default=90,
        help="Rolling window length in calendar days ending at --anchor",
    )
    ap.add_argument(
        "--anchor",
        type=str,
        default="today",
        help="Window end: YYYY-MM-DD or 'today' (local date; end-of-day inclusive)",
    )
    ap.add_argument(
        "--format",
        choices=("html", "md"),
        default="html",
        help="Output format",
    )
    args = ap.parse_args()
    configure_window(args.days, anchor_datetime(args.anchor))
    ws, we = window_start_end()
    data_dir = args.data.resolve()
    out = args.output
    if out is None:
        out = Path(__file__).resolve().parent / "out" / (
            "REPORT.html" if args.format == "html" else "REPORT.md"
        )
    if args.format == "html" and out.suffix.lower() != ".html":
        out = out.with_suffix(".html")
    if args.format == "md" and out.suffix.lower() not in (".md", ".markdown"):
        out = out.with_suffix(".md")

    if args.format == "html":
        text = build_html_report(data_dir)
    else:
        text = build_report(data_dir)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print("Wrote", out.resolve(), "chars", len(text))
    print(f"Anchor (window end): {we.date()} | Window start: {ws.date()} | Days: {args.days}")


if __name__ == "__main__":
    main()
