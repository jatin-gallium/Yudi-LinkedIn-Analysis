#!/usr/bin/env python3
"""Parse LinkedIn bulk export .md files and emit JSON stats + markdown report inputs."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Anchor "today" from latest export metadata in repo (May 17, 2026).
ANCHOR = datetime(2026, 5, 17)
WINDOW_START = datetime(2025, 11, 17)  # inclusive ~6 months
WINDOW_END = ANCHOR

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

def parse_engagement_line(line: str) -> tuple[int, int, int, int]:
    """Robust parse for variants like 'rx, cm, rp (Score:)' or missing cm/rp."""
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


def parse_int(s: str) -> int:
    return int(s.replace(",", "").strip())


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
    def in_window(self) -> bool:
        if self.date is None:
            return False
        return WINDOW_START <= self.date <= WINDOW_END

    @property
    def hook(self) -> str:
        t = " ".join(self.body.split())
        return t[:220] + ("…" if len(t) > 220 else "")

    @property
    def len_chars(self) -> int:
        return len(self.body.strip())


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
    hits = []
    for name, pat in TOPIC_PATTERNS:
        if pat.search(body):
            hits.append(name)
    return hits


def brand_hits(body: str) -> list[str]:
    hits = []
    for name, pat in BRAND_PATTERNS:
        if pat.search(body):
            hits.append(name)
    return hits


def summarize_posts(posts: list[Post], window_only: bool) -> dict:
    xs = [p for p in posts if (p.in_window if window_only else True)]
    if not xs:
        return {"n": 0}

    def median(vals: list[int]) -> float:
        s = sorted(vals)
        n = len(s)
        mid = n // 2
        if n % 2:
            return float(s[mid])
        return (s[mid - 1] + s[mid]) / 2

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
        "media_mix": dict(media.most_common()),
        "topic_posts": dict(topics.most_common()),
        "brand_mentions_posts": dict(brands.most_common()),
    }


def top_posts(posts: list[Post], window_only: bool, key: str, k: int) -> list[Post]:
    xs = [p for p in posts if (p.in_window if window_only else True)]
    if key == "comments":
        xs.sort(key=lambda p: p.comments, reverse=True)
    elif key == "score":
        xs.sort(key=lambda p: p.score, reverse=True)
    elif key == "reposts":
        xs.sort(key=lambda p: p.reposts, reverse=True)
    else:
        raise ValueError(key)
    return xs[:k]


def main() -> None:
    peer_files = [
        "AIshwaraya.md",
        "Amney.md",
        "Ruchi Bhatia.md",
        "Sohan Sethi.md",
        "Sundas Khalid.md",
        "Venkata.md",
        "Vishaka.md",
    ]
    pritesh_file = "Yudi J.md"

    all_peer_posts: list[Post] = []
    peer_by_file: dict[str, list[Post]] = {}
    metas = {}

    for fn in peer_files + [pritesh_file]:
        path = ROOT / fn
        posts, meta = parse_file(path)
        metas[fn] = meta
        if fn != pritesh_file:
            peer_by_file[fn] = posts
            all_peer_posts.extend(posts)

    pritesh_posts, _ = parse_file(ROOT / pritesh_file)

    peer_win = [p for p in all_peer_posts if p.in_window]
    pritesh_win = [p for p in pritesh_posts if p.in_window]

    out = {
        "window": {
            "start": WINDOW_START.strftime("%Y-%m-%d"),
            "end": WINDOW_END.strftime("%Y-%m-%d"),
            "anchor_note": "Window uses 2025-11-17 through 2026-05-17 (six months to latest export date in repo).",
        },
        "meta": metas,
        "counts": {
            "peer_posts_total": len(all_peer_posts),
            "peer_posts_in_window": len(peer_win),
            "pritesh_posts_total": len(pritesh_posts),
            "pritesh_posts_in_window": len(pritesh_win),
        },
        "aggregate_peers_window": summarize_posts(all_peer_posts, True),
        "pritesh_window": summarize_posts(pritesh_posts, True),
        "per_peer_window": {fn: summarize_posts(peer_by_file[fn], True) for fn in peer_files},
    }

    (ROOT / "reports" / "export_analysis.json").parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "reports" / "export_analysis.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )

    # Top exemplars for report (peers only)
    def post_dict(p: Post) -> dict:
        return {
            "file": p.file,
            "author": p.author,
            "date": p.date.strftime("%Y-%m-%d") if p.date else None,
            "reactions": p.reactions,
            "comments": p.comments,
            "reposts": p.reposts,
            "score": p.score,
            "media": p.media,
            "url": p.url,
            "hook": p.hook,
            "body_chars": p.len_chars,
        }

    exemplars: dict = {}
    for fn in peer_files:
        posts = peer_by_file[fn]
        exemplars[fn] = {
            "top_comments": [post_dict(p) for p in top_posts(posts, True, "comments", 8)],
            "top_score": [post_dict(p) for p in top_posts(posts, True, "score", 3)],
            "top_reposts": [post_dict(p) for p in top_posts(posts, True, "reposts", 3)],
        }

    exemplars["pritesh"] = {
        "top_comments": [post_dict(p) for p in top_posts(pritesh_posts, True, "comments", 8)],
        "top_score": [post_dict(p) for p in top_posts(pritesh_posts, True, "score", 3)],
    }

    (ROOT / "reports" / "export_exemplars.json").write_text(
        json.dumps(exemplars, indent=2, default=str), encoding="utf-8"
    )

    print("Wrote reports/export_analysis.json and reports/export_exemplars.json")
    print("Peer window posts:", len(peer_win), "Pritesh window posts:", len(pritesh_win))


if __name__ == "__main__":
    main()
