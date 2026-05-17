# UDJ / Pritesh LinkedIn multi-creator audit

This repository contains a **single, deterministic report generator** that reads LinkedIn bulk-export Markdown files and writes a **balanced** audit: one full subsection per creator (not one peer repeated as the “template” for everything).

## Inputs

Place export files in a directory (default: parent folder when run from the monorepo):

| File | Account |
|------|---------|
| `Yudi J.md` | Pritesh Jagani (UDJ / Yudi J brand) |
| `AIshwaraya.md` | Aishwarya Srinivasan |
| `Amney.md` | Amney Mounir |
| `Ruchi Bhatia.md` | Ruchi Bhatia |
| `Sohan Sethi.md` | Sohan Sethi |
| `Sundas Khalid.md` | Sundas Khalid |
| `Venkata.md` | Venkata Sai |
| `Vishaka.md` | Vishaka Sadhwani |

## Run

```bash
python3 audit_report.py --data /path/to/folder/with/md/exports
```

Output: `out/REPORT.md`

## What is different from a shallow “one peer exemplar” write-up

- **§4** walks **every** peer file with the same rubric: medians, media mix, heuristic topics/brands, **distinctive vocabulary** vs other peers, and **five** high-comment posts with URLs.
- **§6** maps a **six-post** sprint so **six different creators** supply the primary pattern (Sundas is **not** the default anchor).
- Engagement lines are parsed **flexibly** (some exports omit `reposts` or `comments` segments).

## Publish as its own GitHub repository

The Cursor cloud agent token **cannot** call `gh repo create` in this environment. On your machine:

```bash
cp -r udj-linkedin-audit /tmp/udj-linkedin-audit && cd /tmp/udj-linkedin-audit
git init && git add -A && git commit -m "Initial" && git branch -M main
gh repo create jatin-gallium/udj-linkedin-audit --public --source=. --remote=origin --push
```

Copy your eight `*.md` exports into `/tmp/udj-linkedin-audit/data/` (or pass `--data` to wherever they live) before generating `out/REPORT.md`.

## License

Internal use; data belongs to respective LinkedIn accounts.
