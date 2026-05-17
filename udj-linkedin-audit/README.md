# UDJ / Pritesh LinkedIn multi-creator audit

Deterministic report generator: reads **eight** LinkedIn bulk-export Markdown files and writes a **balanced** audit (same rubric for every creator) plus comparison tables and a six-post sprint.

**Default:** last **90** calendar days ending `--anchor` (HTML output).

## Inputs

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

From the directory that contains these `.md` files (e.g. monorepo root):

```bash
# Detailed HTML (default): cohort matrix, topic & brand heatmaps, per-creator tables with LinkedIn links
python3 udj-linkedin-audit/audit_report.py --data . --days 90 --anchor 2026-05-17 --format html -o udj-linkedin-audit/out/REPORT.html

# Markdown variant
python3 udj-linkedin-audit/audit_report.py --data . --days 90 --format md -o udj-linkedin-audit/out/REPORT.md
```

Open the HTML in a browser:

```bash
xdg-open udj-linkedin-audit/out/REPORT.html   # Linux
open udj-linkedin-audit/out/REPORT.html       # macOS
```

### Flags

| Flag | Meaning |
|------|---------|
| `--data DIR` | Folder containing the eight exports |
| `--days N` | Rolling window length (default **90**) |
| `--anchor YYYY-MM-DD` | Window **end** date (default `2026-05-17`, aligned with repo exports) |
| `--format html\|md` | Output type (default **html**) |
| `-o PATH` | Output path (default `out/REPORT.html` or `out/REPORT.md`) |

If a creator has **no posts** inside the window, the HTML report still shows their section using **full-export** leaders and labels the link as outside the window.

## What the HTML report contains

- **Executive snapshot** and **full metrics matrix** (all eight accounts).
- **Topic** and **brand** count tables (heuristic regex tags).
- **Pritesh vs each peer** comparison row.
- **Six-post sprint** with six different exemplar owners and working LinkedIn URLs.
- **Per-creator deep dives**: KPI table + up to **15** top-comment posts with **clickable** post links and hook previews.

## Publish as its own GitHub repository

The cloud agent token may not be allowed to run `gh repo create`. On your machine:

```bash
cp -r udj-linkedin-audit /tmp/udj-linkedin-audit && cd /tmp/udj-linkedin-audit
git init && git add -A && git commit -m "Initial" && git branch -M main
gh repo create jatin-gallium/udj-linkedin-audit --public --source=. --remote=origin --push
```

## License

Internal use; data belongs to respective LinkedIn accounts.
