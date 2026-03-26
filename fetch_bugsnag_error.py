#!/usr/bin/env python3
"""
Fetch Bugsnag error details given an error URL.

Parses the URL to extract org/project/error, resolves IDs via API,
and returns a concise markdown summary with stack trace, breakdowns,
and breadcrumbs.

Usage:
    python fetch_bugsnag_error.py <bugsnag_error_url>
    python fetch_bugsnag_error.py --error-id <id> --project-id <id>
"""

import os
import sys
import re
import json
import argparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_BASE = "https://api.bugsnag.com"

_cache = {}


def get_token():
    token = os.environ.get("BUGSNAG_API_KEY") or os.environ.get("BUGSNAG_AUTH_TOKEN")
    if not token:
        print("Error: BUGSNAG_API_KEY or BUGSNAG_AUTH_TOKEN env var required", file=sys.stderr)
        sys.exit(1)
    return token


def api_get(path, token):
    """Make a GET request to the Bugsnag API."""
    url = f"{API_BASE}{path}"
    req = Request(url, headers={"Authorization": f"token {token}"})
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Bugsnag API {e.code} on {path}: {body}")


def parse_bugsnag_url(url):
    """Parse org slug, project slug, and error ID from a Bugsnag URL."""
    m = re.match(r"https?://app\.bugsnag\.com/([^/]+)/([^/]+)/errors/([a-f0-9]+)", url)
    if not m:
        return None
    return {"org_slug": m.group(1), "project_slug": m.group(2), "error_id": m.group(3)}


def resolve_org_id(org_slug, token):
    cache_key = f"org:{org_slug}"
    if cache_key in _cache:
        return _cache[cache_key]

    orgs = api_get("/user/organizations", token)
    for org in orgs:
        if org.get("slug") == org_slug or org.get("name", "").lower().replace(" ", "-") == org_slug:
            _cache[cache_key] = org["id"]
            return org["id"]

    raise RuntimeError(f"Organization '{org_slug}' not found. Available: {[o.get('slug', o.get('name')) for o in orgs]}")


def resolve_project_id(org_id, project_slug, token):
    cache_key = f"project:{org_id}:{project_slug}"
    if cache_key in _cache:
        return _cache[cache_key]

    projects = api_get(f"/organizations/{org_id}/projects?per_page=100", token)
    for proj in projects:
        if proj.get("slug") == project_slug or proj.get("name", "").lower().replace(" ", "-") == project_slug:
            _cache[cache_key] = proj["id"]
            return proj["id"]

    raise RuntimeError(f"Project '{project_slug}' not found in org. Available: {[p.get('slug', p.get('name')) for p in projects]}")


def format_stacktrace(exceptions, max_frames=15):
    """Format exception chain with stack traces."""
    lines = []
    for i, exc in enumerate(exceptions or []):
        error_class = exc.get("errorClass", "Unknown")
        message = exc.get("message", "")
        label = "Exception" if i == 0 else "Caused by"
        lines.append(f"**{label}: {error_class}**")
        if message:
            lines.append(f"> {message}")
        lines.append("")

        frames = exc.get("stacktrace", [])
        shown = 0
        for frame in frames:
            if shown >= max_frames:
                remaining = len(frames) - shown
                lines.append(f"  ... {remaining} more frames")
                break

            file = frame.get("file", "?")
            line_num = frame.get("lineNumber", "?")
            method = frame.get("method", "?")
            in_project = frame.get("inProject", False)

            marker = ">" if in_project else " "
            lines.append(f"  {marker} {file}:{line_num} in `{method}`")
            shown += 1

        lines.append("")

    return "\n".join(lines)


def format_breadcrumbs(breadcrumbs, max_items=20):
    """Format breadcrumbs, keeping the most recent ones."""
    if not breadcrumbs:
        return "*No breadcrumbs*"

    recent = breadcrumbs[-max_items:]
    lines = []

    for bc in recent:
        ts = bc.get("timestamp", "")
        name = bc.get("name", "?")
        bc_type = bc.get("type", "manual")

        if "T" in ts:
            ts = ts.split("T")[1].split(".")[0] if "." in ts.split("T")[1] else ts.split("T")[1]

        meta = bc.get("metaData", {})
        meta_str = ""
        if meta:
            useful = {k: v for k, v in meta.items() if v and str(v).strip()}
            if useful:
                parts = [f"{k}={v}" for k, v in list(useful.items())[:3]]
                meta_str = f" ({', '.join(parts)})"

        lines.append(f"  `{ts}` [{bc_type}] {name}{meta_str}")

    if len(breadcrumbs) > max_items:
        lines.insert(0, f"  ... {len(breadcrumbs) - max_items} earlier breadcrumbs omitted")

    return "\n".join(lines)


def format_breadcrumb_samples(samples, label=None):
    """Format multiple distinct breadcrumb series collected from different events."""
    if not samples:
        return ""
    lines = []
    if len(samples) == 1:
        heading = f"## Breadcrumbs" if not label else f"**Breadcrumbs ({label}):**"
        lines.append(heading)
        lines.append(format_breadcrumbs(samples[0]))
    else:
        heading = f"## Breadcrumbs ({len(samples)} distinct paths)" if not label else f"**Breadcrumbs ({label}, {len(samples)} distinct paths):**"
        lines.append(heading)
        for j, bc_series in enumerate(samples, 1):
            lines.append(f"**Path {j}:**")
            lines.append(format_breadcrumbs(bc_series))
            lines.append("")
    lines.append("")
    return "\n".join(lines)


def format_pivot_summary(pivot):
    """Format a single pivot as a one-liner with percentages."""
    summary = pivot.get("summary", {})
    items = summary.get("list", [])
    if not items:
        return None

    total = sum(item.get("events", 0) for item in items) + summary.get("no_value", 0)
    if total == 0:
        return None

    parts = []
    for item in items[:5]:
        value = item.get("value", "?")
        count = item.get("events", 0)
        pct = count * 100 // total if total else 0
        parts.append(f"{value} {pct}%")

    other = summary.get("other", 0)
    if other:
        parts.append(f"other {other * 100 // total}%")

    return " | ".join(parts)


def get_trace_signature(exceptions):
    """Build a signature from the top inProject frames of the first exception."""
    if not exceptions:
        return ""
    frames = exceptions[0].get("stacktrace", [])
    in_proj = [f.get("method", "") for f in frames if f.get("inProject")][:5]
    if in_proj:
        return "|".join(in_proj)
    return "|".join([f.get("method", "") for f in frames[:5]])


def format_error_summary(error, event, pivots, distinct_traces):
    """Build a concise markdown summary."""
    lines = []

    error_class = error.get("error_class", event.get("errorClass", "Unknown"))
    message = error.get("message", event.get("context", ""))
    lines.append(f"# {error_class}")
    if message:
        lines.append(f"> {message}")
    lines.append("")

    # Overview
    status = error.get("status", "?")
    severity = event.get("severity", error.get("severity", "?"))
    events_count = error.get("events", "?")
    users_count = error.get("users", "?")
    first_seen = error.get("first_seen", "")
    last_seen = error.get("last_seen", "")

    lines.append("## Overview")
    lines.append(f"- **Status:** {status}")
    lines.append(f"- **Severity:** {severity}")
    lines.append(f"- **Occurrences:** {events_count}")
    lines.append(f"- **Affected users:** {users_count}")
    if first_seen:
        lines.append(f"- **First seen:** {first_seen}")
    if last_seen:
        lines.append(f"- **Last seen:** {last_seen}")

    # Release stages from error
    release_stages = error.get("release_stages", [])
    if release_stages:
        lines.append(f"- **Release stages:** {', '.join(release_stages)}")

    # Linked issues
    linked = error.get("linked_issues", [])
    if linked:
        lines.append(f"- **Linked issues:** {len(linked)}")
        for issue in linked:
            url = issue.get("url", "")
            iid = issue.get("id", "?")
            lines.append(f"  - [{iid}]({url})")

    lines.append("")

    # Breakdowns from pivots
    interesting_pivots = [
        "os.version", "device.manufacturer", "device.model",
        "release.seen_in", "app.in_foreground", "app.isLaunching",
        "metaData.User.country_code", "metaData.device.networkAccess",
    ]

    pivot_map = {p.get("event_field_display_id"): p for p in pivots}
    breakdown_lines = []
    for field_id in interesting_pivots:
        pivot = pivot_map.get(field_id)
        if not pivot:
            continue
        formatted = format_pivot_summary(pivot)
        if formatted:
            name = pivot.get("name", field_id)
            breakdown_lines.append(f"- **{name}:** {formatted}")

    if breakdown_lines:
        lines.append("## Breakdowns")
        lines.extend(breakdown_lines)
        lines.append("")

    # Stack traces with breadcrumbs per variant
    if len(distinct_traces) == 1:
        sig, data = list(distinct_traces.items())[0]
        ev = data["event"]
        lines.append("## Stack Trace")
        lines.append(format_stacktrace(ev.get("exceptions", [])))
        bc_samples = data.get("breadcrumb_samples", [])
        if bc_samples:
            lines.append(format_breadcrumb_samples(bc_samples))
    elif len(distinct_traces) > 1:
        lines.append(f"## Stack Traces ({len(distinct_traces)} distinct)")
        for i, (sig, data) in enumerate(distinct_traces.items(), 1):
            count = data["count"]
            ev = data["event"]
            ctx = ev.get("context", "")
            lines.append(f"### Variant {i} ({count}x) {ctx}")
            lines.append(format_stacktrace(ev.get("exceptions", []), max_frames=8))
            bc_samples = data.get("breadcrumb_samples", [])
            if bc_samples:
                lines.append(format_breadcrumb_samples(bc_samples, label=f"variant {i}"))
    else:
        # Fallback to latest event
        exceptions = event.get("exceptions", [])
        if exceptions:
            lines.append("## Stack Trace")
            lines.append(format_stacktrace(exceptions))
        breadcrumbs = event.get("breadcrumbs", [])
        if breadcrumbs:
            lines.append("## Breadcrumbs")
            lines.append(format_breadcrumbs(breadcrumbs))
            lines.append("")

    # Metadata from latest event (kept brief)
    meta = event.get("metaData", {})
    if meta:
        lines.append("## Metadata (latest event)")
        for tab_name, tab_data in meta.items():
            if not isinstance(tab_data, dict):
                continue
            if len(json.dumps(tab_data)) > 2000:
                keys = list(tab_data.keys())[:10]
                lines.append(f"**{tab_name}:** {', '.join(keys)}{'...' if len(tab_data) > 10 else ''}")
            else:
                lines.append(f"**{tab_name}:**")
                for k, v in list(tab_data.items())[:15]:
                    val = str(v)
                    if len(val) > 200:
                        val = val[:200] + "..."
                    lines.append(f"  - {k}: {val}")
        lines.append("")

    return "\n".join(lines)


def fetch_distinct_traces(project_id, error_id, token, sample_size=30, max_breadcrumb_samples=5):
    """Fetch events and group by distinct stack trace patterns, keeping multiple breadcrumb samples."""
    events = api_get(
        f"/projects/{project_id}/errors/{error_id}/events?per_page={sample_size}&full_reports=true",
        token
    )

    traces = {}
    for ev in events:
        exceptions = ev.get("exceptions", [])
        sig = get_trace_signature(exceptions)
        if sig not in traces:
            traces[sig] = {"count": 0, "event": ev, "breadcrumb_samples": []}
        traces[sig]["count"] += 1

        bc = ev.get("breadcrumbs", [])
        if bc and (max_breadcrumb_samples is None or len(traces[sig]["breadcrumb_samples"]) < max_breadcrumb_samples):
            # Only add if breadcrumbs are meaningfully different from existing samples
            bc_sig = "|".join(b.get("name", "") for b in bc[-5:])
            existing_sigs = [
                "|".join(b.get("name", "") for b in s[-5:])
                for s in traces[sig]["breadcrumb_samples"]
            ]
            if bc_sig not in existing_sigs:
                traces[sig]["breadcrumb_samples"].append(bc)

    return traces


def main():
    parser = argparse.ArgumentParser(description="Fetch Bugsnag error details")
    parser.add_argument("url", nargs="?", help="Bugsnag error URL")
    parser.add_argument("--error-id", help="Error ID (alternative to URL)")
    parser.add_argument("--project-id", help="Project ID (required with --error-id)")
    parser.add_argument("-b", "--breadcrumbs", default="5",
                        help="Max distinct breadcrumb paths per trace variant (default: 5, or 'all')")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    token = get_token()

    if args.url:
        parsed = parse_bugsnag_url(args.url)
        if not parsed:
            print(f"Error: Could not parse Bugsnag URL: {args.url}", file=sys.stderr)
            sys.exit(1)

        if args.verbose:
            print(f"Parsed: {parsed}", file=sys.stderr)

        org_id = resolve_org_id(parsed["org_slug"], token)
        project_id = resolve_project_id(org_id, parsed["project_slug"], token)
        error_id = parsed["error_id"]

    elif args.error_id and args.project_id:
        project_id = args.project_id
        error_id = args.error_id
    else:
        print("Error: Provide a Bugsnag URL or --error-id with --project-id", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Fetching error {error_id} from project {project_id}", file=sys.stderr)

    # Fetch error details, latest event, pivots, and distinct traces
    error = api_get(f"/projects/{project_id}/errors/{error_id}", token)
    event = api_get(f"/errors/{error_id}/latest_event", token)

    try:
        pivots = api_get(f"/projects/{project_id}/errors/{error_id}/pivots", token)
    except RuntimeError:
        pivots = []

    max_bc = None if args.breadcrumbs.lower() == "all" else int(args.breadcrumbs)
    distinct_traces = fetch_distinct_traces(project_id, error_id, token, max_breadcrumb_samples=max_bc)

    output = format_error_summary(error, event, pivots, distinct_traces)
    print(output)


if __name__ == "__main__":
    main()
