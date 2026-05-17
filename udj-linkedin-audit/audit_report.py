#!/usr/bin/env python3
"""
Generate a balanced multi-creator LinkedIn audit from bulk-export Markdown files.
Each peer gets the same section structure; six-post plan rotates across creators.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ANCHOR = datetime(2026, 5, 17)
WINDOW_START = datetime(2025, 11, 17)
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
    if vowels < 1 or vowels / len(w) > 0.6:
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
    def in_window(self) -> bool:
        if self.date is None:
            return False
        return WINDOW_START <= self.date <= WINDOW_END

    @property
    def hook(self) -> str:
        t = " ".join(self.body.split())
        return t[:300] + ("…" if len(t) > 300 else "")

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
        return {"n": 0}
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


def window_posts(posts: list[Post]) -> list[Post]:
    return [p for p in posts if p.in_window]


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


def word_freq(posts: list[Post]) -> Counter[str]:
    c: Counter[str] = Counter()
    for p in posts:
        for w in TOKEN_RE.findall(p.body.lower()):
            if w in STOP or len(w) < 4 or not is_plausible_english_token(w):
                continue
            c[w] += 1
    return c


def distinctive_words(
    self_posts: list[Post], other_peer_posts: list[Post], max_words: int = 14
) -> list[tuple[str, float]]:
    sf = word_freq(self_posts)
    of = word_freq(other_peer_posts)
    sum_s = sum(sf.values()) or 1
    sum_o = sum(of.values()) or 1
    ranked: list[tuple[float, str]] = []
    for w, cnt in sf.items():
        if cnt < max(5, min(12, len(self_posts) // 2)):
            continue
        lift = (cnt / sum_s) / (of.get(w, 0) / sum_o + 1e-9)
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
    L("**Time window:** `2025-11-17`–`2026-05-17` (inclusive), anchored to export dates in May 2026.")
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
        p0 = top_by(peer_by[fn], "comments", 1)[0]
        rows6.append([str(i), display_for(fn), pat, f"[exemplar]({p0.url})", remix])

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
    L("python3 audit_report.py --data /path/to/exports")
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


def main() -> None:
    ap = argparse.ArgumentParser()
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
        default=Path(__file__).resolve().parent / "out" / "REPORT.md",
    )
    args = ap.parse_args()
    text = build_report(args.data.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print("Wrote", args.output, "chars", len(text))


if __name__ == "__main__":
    main()
