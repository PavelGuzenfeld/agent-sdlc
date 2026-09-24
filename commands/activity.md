---
description: Monthly activity report from Claude Code transcripts — per-day work/personal hours with a one-sentence summary. Optional YYYY-MM argument, defaults to the current month.
---

# Activity

Build a per-day activity report for one month from the local Claude Code transcripts
under `~/.claude/projects/`, split work vs personal, and write it to the path the
script's `###REPORT###` block prints (`ACTIVITY_OUT`, default: the current directory).

## Input

`$ARGUMENTS` is an optional `YYYY-MM`. Empty means the current month. Reject anything
else rather than guessing.

## Instructions

1. **Write the script.** Copy the fenced block at the bottom of this file *verbatim* to
   `<scratchpad>/activity.sh`, `chmod +x` it, and run it with the month as its only
   argument. It takes ~10 s over ~130 transcripts and ~30 repos. Do not reimplement it
   inline — the gap-capping, midnight-splitting and DST handling are already tested.

2. **Read its output.** Five TSV blocks on stdout:
   - Day metrics: `date, space, start, end, active_h, span_h`. Three rows per calendar
     day — `work`, `personal`, `all`. `all` is recomputed, not summed.
   - `###SESSIONS###` — one row per **session-day**:
     `date, space, start, end, project_dir, session_id, title`.
   - `###REPOS###` — `touch_count, date, space, repo`: how many records that day
     referenced a path under that repo. This is the honest signal for what was worked on.
   - `###COMMITS###` — `date, space, repo_identity, subject`: your own commits that day
     across every repo in both spaces, deduped by SHA across worktrees.
   - `###REPORT###` — one line: the absolute path to write the report to.

3. **Write one sentence per non-empty (day, space) cell — from `###REPOS###` and
   `###COMMITS###`, not from the titles.** The `title` field is the session's *first
   prompt*, and it lies constantly: August 2026 produced `hi`, `done`, `cleanup`,
   `What's next`, `Model opus`. One session titled `Model opus` made 2,129 references to
   naval-planner files while doing a feature rip-out. Rank the day's repos by touch count, name
   the top two or three, and say what landed using the commit subjects. Use titles only
   to disambiguate. Use `—` for an empty cell.

4. **Emit one table**, `all` rendered as a bold per-date subtotal subrow. Blank the
   Date cell on the second and third subrows. Skip days where all three rows are zero,
   but list the skipped dates in Totals.

   | Date | Space | Start | End | Active | Span | Summary |
   |---|---|---|---|---|---|---|
   | 08-24 | work | 00:01 | 23:59 | 11.36 | 23.96 | … |
   | | personal | — | — | 0.00 | 0.00 | — |
   | | **day** | **00:01** | **23:59** | **11.36** | **23.96** | |

5. **Write** the table to the path from `###REPORT###` with `Totals`, `Method`
   and `Caveats` sections, and print the table in the terminal too. Totals should include
   the busiest repos by touch count and the commit count per repo.

6. **End your reply with the link to the file you wrote** — the absolute path on its own
   line so it is clickable in the terminal:

   `Report: <path from ###REPORT###>`

   Never publish it as an Artifact or to any other external surface: the report names
   internal repos and hosts, which the banned-name list at the `banned_names_file`
   named in `.mutation-gate.toml` bars from leaving the machine. If a shareable
   copy is ever wanted, ask first and sanitize.

## Definitions — keep these stable so months stay comparable

- **Timezone:** the system timezone, DST-correct (override with `ACTIVITY_TZ`). Days
  split at local midnight.
- **Output:** written under `ACTIVITY_OUT` (default: the current directory).
- **Active:** union of each session's engaged intervals, where a gap between
  consecutive events counts as `min(gap, 30 min)`. Union, not sum, so concurrent
  sessions never double-count — this matters: a naive sum reports 23.21 h for
  2026-08-30 against the 12.12 h the union gives.
- **Span:** last event − first event that day, per space. Independent of Active.
- **Day row:** Active is the union over the merged work+personal event stream. Span is
  the union of the work and personal brackets, so a gap between an afternoon work block
  and an evening personal block is not counted as time at the desk.
- **Work vs personal:** by directory under `$HOME`. Dirs named in `ACTIVITY_PERSONAL_DIRS`
  (default `personalspace`) are personal; **everything else is work**, including `-tmp`
  and any project dir added later. Nothing is dropped.
- **Commits:** yours only, matched via `git config user.name`/`user.email` (override with
  `ACTIVITY_AUTHOR`), deduped by SHA so a worktree pair like `foo`/`foo-worktree` counts
  once. Git stash entries are filtered out. Repos are found under the dirs in
  `ACTIVITY_DIRS` (default `workspace personalspace`), one level deep under `$HOME`.
- **Excluded:** `<session>/subagents/*.jsonl` — subagents run inside a parent session,
  so counting them double-counts the parent's hours.

## Caveats to carry into the report

- A public repo can live under a work directory (a personal open-source project
  checked out alongside client work). The directory rule still counts it as work. Say so.
- Active can exceed Span on a day whose last event is followed by a long gap: the
  30-minute capped tail lands inside that day but past the last event.
- Truncated transcripts abort `jq` mid-file; the parsed prefix is kept and the rest of
  that session is silently missing.
- Repo touch counts include reads, not just edits, so a repo consulted as a reference
  will appear. Cross-check against `###COMMITS###` before calling it the day's work.
- Commits by teammates are excluded, so a repo can show heavy touches and no commits.
- claude.ai web conversations are not in any local file. Only `claude.ai/settings →
  Privacy → Export data` can add them.

## Script

```bash
#!/usr/bin/env bash
# Per-day Claude Code activity for one month.
# stdout: day-metrics TSV (date, space, start, end, active_h, span_h), then ###SESSIONS###.
set -eu

MONTH="${1:-$(date +%Y-%m)}"
[ -n "${ACTIVITY_TZ:-}" ] && export TZ="$ACTIVITY_TZ"
OUT_DIR="${ACTIVITY_OUT:-$PWD}"
CAP="${ACTIVITY_GAP_CAP:-1800}"
PROJECTS="$HOME/.claude/projects"
PERSONAL_DIRS="${ACTIVITY_PERSONAL_DIRS:-personalspace}"
BASE_DIRS="${ACTIVITY_DIRS:-workspace personalspace}"
HOME_ENC=$(printf '%s' "$HOME" | sed 's#/#-#g')
AUTHOR="${ACTIVITY_AUTHOR:-}"
if [ -z "$AUTHOR" ]; then
  AUTHOR=$(git config --get user.name 2>/dev/null || true)
  email=$(git config --get user.email 2>/dev/null || true)
  [ -n "$email" ] && AUTHOR="${AUTHOR:+$AUTHOR\\|}$email"
fi
home_esc=$(printf '%s' "$HOME" | sed 's/\./[.]/g')
alt=$(printf '%s' "$BASE_DIRS" | tr ' ' '|')
home_regex="$home_esc/($alt)/[A-Za-z0-9._-]+"

month_start=$(date -d "$MONTH-01 00:00:00" +%s)
next_month=$(date -d "$MONTH-01 +32 days" +%Y-%m)
month_end=$(date -d "$next_month-01 00:00:00" +%s)

work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
: > "$work/events"; : > "$work/titles"

d=$month_start
while [ "$d" -lt "$month_end" ]; do
  printf '%s\t%s\n' "$(date -d "@$d" +%F)" "$d"
  d=$(date -d "$(date -d @$d +%F) +1 day" +%s)
done > "$work/bounds"

# Truncated transcripts abort jq mid-file; `|| true` keeps the parsed prefix.
while IFS= read -r -d '' f; do
  dir=$(basename "$(dirname "$f")")
  sid=$(basename "$f" .jsonl)
  space=work
  for pd in $PERSONAL_DIRS; do
    case "$dir" in "$HOME_ENC-$pd"*) space=personal ;; esac
  done
  label=${dir#"$HOME_ENC"-}; [ -n "$label" ] || label=$dir

  jq -r --arg s "$space" --arg i "$sid" \
    'select(.timestamp)|.timestamp|sub("\\.[0-9]+Z$";"Z")|fromdateiso8601|"\($s)\t\($i)\t\(.)"' \
    "$f" 2>/dev/null >> "$work/events" || true

  title=$(jq -r 'select(.type=="ai-title")|.aiTitle // empty' "$f" 2>/dev/null | tail -1 || true)
  if [ -z "$title" ]; then
    title=$(jq -r 'select(.type=="last-prompt")|.lastPrompt // empty' "$f" 2>/dev/null | tail -1 || true)
  fi
  printf '%s\t%s\t%s\t%s\n' "$sid" "$space" "$label" \
    "$(printf '%s' "$title" | tr '\t\n' '  ' | cut -c1-160)" >> "$work/titles"
done < <(find "$PROJECTS" -mindepth 2 -maxdepth 2 -name '*.jsonl' -print0)

cat > "$work/agg.awk" <<'AWKEOF'
BEGIN {
  FS = OFS = "\t"
  while ((getline line < bf) > 0) { split(line, b, FS); nd++; dname[nd]=b[1]; dstart[nd]=b[2]+0 }
  for (i=1; i<=nd; i++) dend[i] = (i<nd ? dstart[i+1] : me+0)
  ms += 0; me += 0; cap += 0
}
function addrun(space, s, e,   i, a, z) {
  if (s < ms) s = ms
  if (e > me) e = me
  if (e <= s) return
  for (i=1; i<=nd; i++) {
    a = (s > dstart[i] ? s : dstart[i]); z = (e < dend[i] ? e : dend[i])
    if (z > a) iv[space][i][++ivn[space][i]] = a OFS z
  }
}
function flush(   i, s, e) {
  if (nev < 1) return
  s = ev[1]; e = ev[1]
  for (i=2; i<=nev; i++) {
    if (ev[i] - ev[i-1] <= cap) e = ev[i]
    else { addrun(csp, s, e + cap); addrun("all", s, e + cap); s = ev[i]; e = ev[i] }
  }
  addrun(csp, s, e); addrun("all", s, e)
  delete ev; nev = 0
}
{
  if ($1 != csp || $2 != csid) { flush(); csp = $1; csid = $2 }
  t = $3 + 0
  ev[++nev] = t
  if (t >= ms && t < me) for (j=1; j<=nd; j++) if (t >= dstart[j] && t < dend[j]) {
    if (!((csp, j) in fst) || t < fst[csp, j]) fst[csp, j] = t
    if (!((csp, j) in lst) || t > lst[csp, j]) lst[csp, j] = t
    if (!(("all", j) in fst) || t < fst["all", j]) fst["all", j] = t
    if (!(("all", j) in lst) || t > lst["all", j]) lst["all", j] = t
    break
  }
}
END {
  flush()
  split("work personal all", SP, " ")
  for (k=1; k<=3; k++) {
    sp = SP[k]
    for (i=1; i<=nd; i++) {
      act = union_len(sp, i)
      f = ((sp, i) in fst) ? fst[sp, i] : 0
      l = ((sp, i) in lst) ? lst[sp, i] : 0
      spn = (sp == "all") ? span_all(i) : ((l > f) ? l - f : 0)
      print dname[i], sp, (f ? strftime("%H:%M", f) : "-"), (l ? strftime("%H:%M", l) : "-"),
            sprintf("%.2f", act/3600), sprintf("%.2f", spn/3600)
    }
  }
}
function union_len(sp, day,   c, arr, i, tot, cs, ce, x) {
  if (!(sp in iv) || !(day in iv[sp])) return 0
  c = ivn[sp][day]
  for (i=1; i<=c; i++) arr[i] = iv[sp][day][i]
  if (c > 1) c = asort(arr, arr, "cmp_start")
  split(arr[1], x, OFS); cs = x[1]+0; ce = x[2]+0; tot = 0
  for (i=2; i<=c; i++) {
    split(arr[i], x, OFS)
    if (x[1]+0 > ce) { tot += ce - cs; cs = x[1]+0; ce = x[2]+0 }
    else if (x[2]+0 > ce) ce = x[2]+0
  }
  return tot + ce - cs
}
function cmp_start(i1, v1, i2, v2,   a, b) {
  split(v1, a, OFS); split(v2, b, OFS)
  return (a[1]+0 < b[1]+0) ? -1 : ((a[1]+0 > b[1]+0) ? 1 : 0)
}
# Day span unions the two space brackets, so a gap between a work block and a
# personal block is not counted as time at the desk.
function span_all(day,   a1, a2, b1, b2, la, lb) {
  a1 = (("work", day) in fst) ? fst["work", day] : 0; a2 = (("work", day) in lst) ? lst["work", day] : 0
  b1 = (("personal", day) in fst) ? fst["personal", day] : 0; b2 = (("personal", day) in lst) ? lst["personal", day] : 0
  la = (a2 > a1) ? a2 - a1 : 0; lb = (b2 > b1) ? b2 - b1 : 0
  if (la == 0) return lb
  if (lb == 0) return la
  if (a1 <= b2 && b1 <= a2) return ((a2 > b2) ? a2 : b2) - ((a1 < b1) ? a1 : b1)
  return la + lb
}
AWKEOF

sort -t$'\t' -k1,1 -k2,2 -k3,3n "$work/events" |
  gawk -v ms="$month_start" -v me="$month_end" -v cap="$CAP" -v bf="$work/bounds" -f "$work/agg.awk"

cat > "$work/sessions.awk" <<'AWKEOF'
BEGIN { FS = OFS = "\t"; ms += 0; me += 0
  while ((getline line < bf) > 0) { split(line, b, FS); nd++; dname[nd]=b[1]; dstart[nd]=b[2]+0 }
  for (i=1; i<=nd; i++) dend[i] = (i<nd ? dstart[i+1] : me)
}
NR==FNR {
  t = $3 + 0
  if (t < ms || t >= me) next
  for (j=1; j<=nd; j++) if (t >= dstart[j] && t < dend[j]) {
    k = $2 SUBSEP j
    if (!(k in lo) || t < lo[k]) lo[k] = t
    if (!(k in hi) || t > hi[k]) hi[k] = t
    break
  }
  next
}
{
  for (j=1; j<=nd; j++) {
    k = $1 SUBSEP j
    if (k in lo)
      print dname[j], $2, strftime("%H:%M", lo[k]), strftime("%H:%M", hi[k]),
            $3, substr($1, 1, 8), $4
  }
}
AWKEOF

echo "###SESSIONS###"
gawk -F'\t' -v ms="$month_start" -v me="$month_end" -v bf="$work/bounds" \
  -f "$work/sessions.awk" "$work/events" "$work/titles" | sort

cat > "$work/repos.awk" <<'AWKEOF'
function to_epoch(iso,   y,mo,d,h,mi,s,era,yoe,doy,doe,days) {
  y=substr(iso,1,4)+0; mo=substr(iso,6,2)+0; d=substr(iso,9,2)+0
  h=substr(iso,12,2)+0; mi=substr(iso,15,2)+0; s=substr(iso,18,2)+0
  y -= (mo <= 2)
  era = int((y >= 0 ? y : y-399) / 400); yoe = y - era*400
  doy = int((153*(mo + (mo > 2 ? -3 : 9)) + 2)/5) + d-1
  doe = yoe*365 + int(yoe/4) - int(yoe/100) + doy
  days = era*146097 + doe - 719468
  return days*86400 + h*3600 + mi*60 + s
}
BEGIN{ OFS="\t"
  while((getline l < DF)>0){split(l,a," "); ok[a[1]"/"a[2]]=1}
  while((getline l < BF)>0){split(l,b,"\t"); nd++; dn[nd]=b[1]; ds[nd]=b[2]+0}
  for(i=1;i<=nd;i++) de[i]=(i<nd?ds[i+1]:ds[nd]+86400)
  np=split(PD, pdarr, " "); for(i=1;i<=np;i++) pset[pdarr[i]]=1
  hlen=length(HOMEDIR)
}
{ if (match($0, /"timestamp":"[0-9T:.Z-]+"/)) ts=substr($0,RSTART+13,RLENGTH-14); else next
  t=to_epoch(ts); day=0
  for(j=1;j<=nd;j++) if(t>=ds[j] && t<de[j]){day=j; break}
  if(!day) next
  delete seen; s=$0
  while (match(s, HR)) {
    p=substr(s,RSTART,RLENGTH); s=substr(s,RSTART+RLENGTH)
    rest=substr(p, hlen+2); n=split(rest,a,"/")
    if(n>=2 && !(a[2] in seen) && ((a[1]"/"a[2]) in ok)){ seen[a[2]]=1
      c[dn[day] OFS ((a[1] in pset)?"personal":"work") OFS a[2]]++ } }
}
END{ for(k in c) print c[k], k }
AWKEOF

: > "$work/dirs"
for bd in $BASE_DIRS; do
  for p in "$HOME/$bd"/*/; do [ -d "$p" ] && echo "$bd $(basename "$p")" >> "$work/dirs"; done
done

echo "###REPOS###"
find "$PROJECTS" -mindepth 2 -maxdepth 2 -name '*.jsonl' -print0 |
  xargs -0 -r gawk -v DF="$work/dirs" -v BF="$work/bounds" -v PD="$PERSONAL_DIRS" -v HR="$home_regex" \
    -v HOMEDIR="$HOME" -f "$work/repos.awk" |
  sort -t$'\t' -k2,2 -k1,1nr

echo "###COMMITS###"
: > "$work/craw"
if [ -n "$AUTHOR" ]; then
  for bd in $BASE_DIRS; do
    sp=work
    for pd in $PERSONAL_DIRS; do [ "$bd" = "$pd" ] && sp=personal; done
    for p in "$HOME/$bd"/*/; do
      git -C "$p" rev-parse --git-dir >/dev/null 2>&1 || continue
      id=$(git -C "$p" remote get-url origin 2>/dev/null | sed 's|.*[:/]\([^/]*/[^/]*\)$|\1|; s|\.git$||')
      [ -n "$id" ] || id=$(basename "$p")
      git -C "$p" log --all -i --since="$MONTH-01 -10 days" --until="$next_month-05" \
        --author="$AUTHOR" \
        --date=format-local:'%Y-%m-%d' --pretty="%H%x09%ad%x09$sp%x09$id%x09%s" 2>/dev/null >> "$work/craw" || true
    done
  done
fi
sort -u "$work/craw" | gawk -F'\t' -v M="$MONTH" '!seen[$1]++ && $2 ~ "^" M' \
  | grep -v $'\t\(index on\|On \|untracked files on\|WIP on\)' | cut -f2- | sort

echo "###REPORT###"
printf '%s\n' "$OUT_DIR/$MONTH-activity.md"
```
