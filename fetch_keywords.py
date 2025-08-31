#!/usr/bin/env python3
"""
Fetch App Store keywords for one or more apps and locales using ONLY public
Apple iTunes Search/Lookup APIs (no App Store Connect access required).

Input identifiers:
- App Store ID: id123456789 or 123456789
- Bundle ID: com.example.myapp

For each requested locale (e.g., en-US), the script prints the app name and a
heuristically constructed comma-separated keywords string (<=100 chars),
based on public metadata such as title, genres, and description tokens.

Example output:
Name: My Great App id123456789 [en-US]
========================================
garageband,ringtone maker,garage,ringtones,garage rigtones,garage band,ringtone,zedge
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import requests

# Rich (for colorful output). Fallback to plain prints if unavailable.
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    _RICH_AVAILABLE = True
except Exception:  # pragma: no cover
    Console = None  # type: ignore
    Panel = None  # type: ignore
    Text = None  # type: ignore
    box = None  # type: ignore
    _RICH_AVAILABLE = False

ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"

# Locale → iTunes storefront country mapping (subset; falls back to --country)
LOCALE_TO_COUNTRY: Dict[str, str] = {
    "en": "us",
    "en-US": "us",
    "es": "es",
    "es-MX": "mx",
    "pt-PT": "pt",
    "pt-BR": "br",
    "fr": "fr",
    "de": "de",
    "it": "it",
    "tr": "tr",
    "hi": "in",
    "ja": "jp",
    "ko": "kr",
    "ar": "sa",
    "zh-Hans": "cn",
}

SIMPLE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-']+")


def normalize_itunes_id(value: str) -> Optional[str]:
    m = re.fullmatch(r"id?(\d+)", value.strip())
    return m.group(1) if m else None


def is_bundle_id(value: str) -> bool:
    return "." in value and not value.lower().startswith("id") and not value.isdigit()


def map_locale_to_country(locale: str, default_country: str) -> str:
    if not locale:
        return default_country
    if locale in LOCALE_TO_COUNTRY:
        return LOCALE_TO_COUNTRY[locale]
    base = locale.split("-")[0]
    return LOCALE_TO_COUNTRY.get(base, default_country)


def itunes_lookup_by_id(itunes_id: str, country: str, timeout_seconds: int = 20) -> Optional[Dict]:
    try:
        resp = requests.get(
            ITUNES_LOOKUP_URL,
            params={"id": itunes_id, "country": country, "entity": "software"},
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultCount", 0) > 0:
            # Prefer software entries
            for item in data.get("results", []):
                if (item.get("kind") == "software") or (item.get("wrapperType") == "software"):
                    return item
            return data["results"][0]
        return None
    except Exception:
        return None


def itunes_lookup_by_bundle_id(bundle_id: str, country: str, timeout_seconds: int = 20) -> Optional[Dict]:
    try:
        resp = requests.get(
            ITUNES_LOOKUP_URL,
            params={"bundleId": bundle_id, "country": country, "entity": "software"},
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultCount", 0) > 0:
            # Prefer software entries
            for item in data.get("results", []):
                if (item.get("kind") == "software") or (item.get("wrapperType") == "software"):
                    return item
            return data["results"][0]
        return None
    except Exception:
        return None


def _extract_terms_from_itunes(item: Dict) -> List[str]:
    terms: List[str] = []
    if not item:
        return terms
    title = (item.get("trackName") or "").lower()
    desc = (item.get("description") or "").lower()
    genres = [str(g).lower() for g in (item.get("genres") or [])]
    # Title tokens
    terms.extend(SIMPLE_TOKEN_RE.findall(title))
    # Description tokens
    terms.extend(SIMPLE_TOKEN_RE.findall(desc))
    # Genres
    for g in genres:
        terms.extend(SIMPLE_TOKEN_RE.findall(g))
    # Basic filtering and de-dup
    out: List[str] = []
    seen = set()
    for t in terms:
        if t.isdigit():
            continue
        if len(t) <= 1 and t not in {"ai"}:
            continue
        if t in {
            "app",
            "apps",
            "application",
            "applications",
            "iphone",
            "ipad",
            "ios",
            "free",
            "best",
            "new",
            "pro",
            "lite",
            "hd",
        }:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def build_keywords_from_itunes(item: Dict, char_limit: int = 100) -> Optional[str]:
    if not item:
        return None
    tokens = _extract_terms_from_itunes(item)
    # Heuristic scoring: title > genres > description
    title = (item.get("trackName") or "").lower()
    genres = [str(g).lower() for g in (item.get("genres") or [])]
    token_scores: Dict[str, int] = {}
    for tok in tokens:
        score = 1
        if tok in title:
            score += 4
        if any(tok in g for g in genres):
            score += 2
        token_scores[tok] = token_scores.get(tok, 0) + score
    # Sort by score desc then by token
    sorted_terms = sorted(token_scores.items(), key=lambda kv: (-kv[1], kv[0]))
    # Compose <= char_limit comma-delimited
    out_parts: List[str] = []
    cur_len = 0
    for term, _ in sorted_terms:
        candidate = term.replace(" ", ",")
        add_len = len(candidate) + (1 if out_parts else 0)
        if cur_len + add_len > char_limit:
            continue
        out_parts.append(candidate)
        cur_len += add_len
        if cur_len >= char_limit:
            break
    return ",".join(out_parts) if out_parts else None


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch App Store keywords for apps and locales using public iTunes APIs (no ASC).",
    )
    parser.add_argument(
        "apps",
        nargs="+",
        help="App identifiers: App Store IDs (id12345 or 12345) or Bundle IDs (com.example.app)",
    )
    parser.add_argument(
        "-l",
        "--locales",
        nargs="+",
        default=["en-US"],
        help="Locales to fetch (e.g., en-US de-DE fr-FR). Default: en-US",
    )
    parser.add_argument(
        "--country",
        default=os.getenv("DEFAULT_COUNTRY", "us"),
        help="Default country storefront for lookups when locale is unknown. Default: us",
    )
    parser.add_argument(
        "--char-limit",
        type=int,
        default=int(os.getenv("ASO_CHAR_LIMIT", "100")),
        help="Max characters for the keywords string (default: 100)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored/pretty output",
    )
    return parser.parse_args(argv)


def _should_use_color(no_color_flag: bool) -> bool:
    if no_color_flag:
        return False
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty() and _RICH_AVAILABLE


def _render_output(
    console: Optional[Console],
    use_color: bool,
    name: str,
    printed_id: str,
    locale: str,
    keywords: Optional[str],
) -> None:
    if not use_color or console is None or not _RICH_AVAILABLE:
        # Plain fallback
        print(f"Name: {name} {printed_id} [{locale}]")
        print("=" * 40)
        print((keywords or "(no keywords)").strip() or "(no keywords)")
        return

    # Build colored header
    header = Text()
    header.append("Name: ", style="bold white")
    header.append(name, style="bold cyan")
    header.append(" ")
    header.append(printed_id, style="magenta")
    header.append(" ")
    header.append(f"[{locale}]", style="green")

    # Build keywords text
    if keywords and keywords.strip():
        kw_text = Text()
        terms = [t for t in keywords.strip().split(",") if t]
        # Alternate styles for readability
        styles = ["yellow", "bright_cyan", "bright_magenta", "bright_green", "bright_blue", "bright_yellow"]
        for idx, term in enumerate(terms):
            style = styles[idx % len(styles)]
            if idx > 0:
                kw_text.append(",", style="dim")
            kw_text.append(term, style=style)
    else:
        kw_text = Text("(no keywords)", style="dim")

    panel = Panel(
        kw_text,
        title=header,
        title_align="left",
        border_style="blue",
        box=box.ROUNDED if box else None,
        padding=(1, 2),
    )
    console.print(panel)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    use_color = _should_use_color(args.no_color)
    console: Optional[Console] = Console() if use_color and _RICH_AVAILABLE else None

    any_errors = False

    for app_input in args.apps:
        for locale in args.locales:
            country = map_locale_to_country(locale, args.country)

            # Resolve iTunes item by ID or bundle ID for this country
            item: Optional[Dict] = None
            itunes_id = normalize_itunes_id(app_input)
            printed_id: str
            if itunes_id:
                item = itunes_lookup_by_id(itunes_id, country=country)
                printed_id = f"id{itunes_id}"
            elif is_bundle_id(app_input):
                item = itunes_lookup_by_bundle_id(app_input, country=country)
                printed_id = app_input
            else:
                # Unknown identifier format
                item = None
                printed_id = app_input

            name = (item or {}).get("trackName") or "Unknown App"
            keywords = build_keywords_from_itunes(item, char_limit=args.char_limit) if item else None

            _render_output(console, use_color, name, printed_id, locale, keywords)

            if not item:
                any_errors = True
    return 1 if any_errors else 0


if __name__ == "__main__":
    sys.exit(main())
