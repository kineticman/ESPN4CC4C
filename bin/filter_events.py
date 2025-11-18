#!/usr/bin/env python3
"""
Event filtering for ESPN4CC4C.

This module loads filter configuration from an INI file and/or environment
variables and exposes:

- EventFilter: encapsulates all filter rules
- filter_events_from_db(conn, filter_config): applies filters to the events table

Environment variables (FILTER_*) override INI settings, which in turn fall back
to sane defaults. This makes it Docker/compose friendly while still supporting
a local filters.ini for power users.
"""

import configparser
import json
import os
import sqlite3
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class EventFilter:
    """Filters events based on configuration.

    The effective configuration is constructed as:

        env vars (FILTER_*) → filters.ini → built‑in defaults

    Attributes exposed on instances are used by should_include() and
    config_signature().
    """

    def __init__(self, config_path: str = "filters.ini", use_env: bool = False) -> None:
        self.config_path = Path(config_path)
        self.use_env = use_env

        self.case_insensitive: bool = True
        self.partial_league_match: bool = True

        # Filter sets (None = no restriction, empty set() = block everything)
        self.enabled_networks: Optional[Set[str]] = None
        self.exclude_networks: Set[str] = set()

        self.enabled_sports: Optional[Set[str]] = None
        self.exclude_sports: Set[str] = set()

        self.enabled_leagues: Optional[Set[str]] = None
        self.exclude_leagues: Set[str] = set()

        self.enabled_event_types: Optional[Set[str]] = None
        self.exclude_event_types: Set[str] = set()

        self.enabled_languages: Optional[Set[str]] = None
        self.exclude_languages: Set[str] = set()

        # Flags
        self.require_espn_plus: Optional[bool] = None
        self.exclude_ppv: bool = False
        self.exclude_reair: bool = False
        self.exclude_no_sport: bool = False

        cfg = self._load_config()
        self._parse_filters(cfg)

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_config(self) -> configparser.ConfigParser:
        """Load INI config, fill defaults, and apply env overrides."""
        config = configparser.ConfigParser()

        if self.config_path.exists():
            config.read(self.config_path, encoding="utf-8")
        else:
            print(f"[filter] No INI file found at {self.config_path}, using defaults", flush=True)

        if "filters" not in config:
            config["filters"] = {}

        f = config["filters"]

        # Defaults for any missing keys
        defaults = {
            "enabled_networks": "*",
            "exclude_networks": "",
            "enabled_sports": "*",
            "exclude_sports": "",
            "enabled_leagues": "*",
            "exclude_leagues": "",
            "require_espn_plus": "",
            "exclude_ppv": "false",
            "exclude_reair": "false",
            "enabled_event_types": "*",
            "exclude_event_types": "",
            "enabled_languages": "*",
            "exclude_languages": "",
            "case_insensitive": "true",
            "partial_league_match": "true",
            "exclude_no_sport": "false",
        }

        for key, default_value in defaults.items():
            if key not in f:
                f[key] = default_value

        # Environment overrides
        if self.use_env:
            env_mapping = {
                "FILTER_ENABLED_NETWORKS": "enabled_networks",
                "FILTER_EXCLUDE_NETWORKS": "exclude_networks",
                "FILTER_ENABLED_SPORTS": "enabled_sports",
                "FILTER_EXCLUDE_SPORTS": "exclude_sports",
                "FILTER_ENABLED_LEAGUES": "enabled_leagues",
                "FILTER_EXCLUDE_LEAGUES": "exclude_leagues",
                "FILTER_REQUIRE_ESPN_PLUS": "require_espn_plus",
                "FILTER_EXCLUDE_PPV": "exclude_ppv",
                "FILTER_EXCLUDE_REAIR": "exclude_reair",
                "FILTER_ENABLED_EVENT_TYPES": "enabled_event_types",
                "FILTER_EXCLUDE_EVENT_TYPES": "exclude_event_types",
                "FILTER_ENABLED_LANGUAGES": "enabled_languages",
                "FILTER_EXCLUDE_LANGUAGES": "exclude_languages",
                "FILTER_CASE_INSENSITIVE": "case_insensitive",
                "FILTER_PARTIAL_LEAGUE_MATCH": "partial_league_match",
                "FILTER_EXCLUDE_NO_SPORT": "exclude_no_sport",
            }

            applied: List[str] = []
            for env_var, cfg_key in env_mapping.items():
                env_value = os.environ.get(env_var)
                if env_value is not None:
                    # Trim surrounding quotes some compose/Portainer UIs add
                    if (
                        isinstance(env_value, str)
                        and len(env_value) >= 2
                        and env_value[0] == env_value[-1]
                        and env_value[0] in ('"', "'")
                    ):
                        env_value = env_value[1:-1]
                    f[cfg_key] = env_value
                    applied.append(f"{env_var}={env_value}")

            if applied:
                print("[filter] Applied environment overrides:", flush=True)
                for line in applied:
                    print(f"[filter]   {line}", flush=True)

        return config

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_filters(self, config: configparser.ConfigParser) -> None:
        f = config["filters"]

        # Options
        self.case_insensitive = f.get("case_insensitive", "true").strip().lower() == "true"
        self.partial_league_match = f.get("partial_league_match", "true").strip().lower() == "true"

        # Network filters
        self.enabled_networks = self._parse_set(f.get("enabled_networks", "*"))
        self.exclude_networks = self._parse_set(f.get("exclude_networks", "")) or set()

        # Sports
        self.enabled_sports = self._parse_set(f.get("enabled_sports", "*"))
        self.exclude_sports = self._parse_set(f.get("exclude_sports", "")) or set()

        # Leagues
        self.enabled_leagues = self._parse_set(f.get("enabled_leagues", "*"))
        self.exclude_leagues = self._parse_set(f.get("exclude_leagues", "")) or set()

        # Event types
        self.enabled_event_types = self._parse_set(f.get("enabled_event_types", "*"))
        self.exclude_event_types = self._parse_set(f.get("exclude_event_types", "")) or set()

        # Languages
        self.enabled_languages = self._parse_set(f.get("enabled_languages", "*"))
        self.exclude_languages = self._parse_set(f.get("exclude_languages", "")) or set()

        # Flags
        self.require_espn_plus = self._parse_bool(f.get("require_espn_plus", ""))
        self.exclude_ppv = f.get("exclude_ppv", "false").strip().lower() == "true"
        self.exclude_reair = f.get("exclude_reair", "false").strip().lower() == "true"
        self.exclude_no_sport = f.get("exclude_no_sport", "false").strip().lower() == "true"

    def _parse_set(self, value: Optional[str]) -> Optional[Set[str]]:
        """Parse a comma-separated list into a set.

        Returns:
            None  → "no restriction" (i.e., * or all)
            set() → "block everything" (empty/none)
        """
        if value is None:
            return None

        raw = value.strip()
        if raw == "" or raw.lower() == "none":
            return set()

        if raw in ("*", "all", "ALL"):
            return None

        items = {s.strip() for s in raw.split(",") if s.strip()}
        if self.case_insensitive:
            items = {s.lower() for s in items}
        return items

    def _parse_bool(self, value: str) -> Optional[bool]:
        value = value.strip().lower()
        if not value:
            return None
        return value in ("true", "yes", "1", "on")

    def _normalize(self, value: Optional[str]) -> str:
        if not value:
            return ""
        return value.lower() if self.case_insensitive else value

    def _match_in_set(
        self,
        value: Optional[str],
        filter_set: Optional[Set[str]],
        partial: bool = False,
    ) -> bool:
        """Return True if value is allowed by filter_set.

        filter_set is interpreted as:
          - None → no restriction (always True)
          - set() → block everything (never match)
          - non-empty set → value must be in set (or partially match)
        """
        if filter_set is None:
            return True  # no restriction

        if not value:
            return False

        norm = self._normalize(value)

        if partial:
            for token in filter_set:
                if token in norm:
                    return True
            return False

        return norm in filter_set

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def _check_packages(self, packages: Any) -> Dict[str, bool]:
        """Inspect packages JSON for ESPN+ and PPV flags."""
        is_espn_plus = False
        is_ppv = False

        if not packages:
            return {"is_espn_plus": False, "is_ppv": False}

        data = None
        if isinstance(packages, str):
            try:
                data = json.loads(packages)
            except Exception:
                data = None
        else:
            data = packages

        if isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = data
        else:
            items = []

        for pkg in items:
            try:
                code = str(pkg.get("code") or pkg.get("id") or "")
            except Exception:
                code = ""
            up = code.upper()
            if "PLUS" in up or "ESPN+" in up or "ESPN_PLUS" in up:
                is_espn_plus = True
            if "PPV" in up or "PAY_PER_VIEW" in up:
                is_ppv = True

        return {"is_espn_plus": is_espn_plus, "is_ppv": is_ppv}

    def should_include(self, event: Dict[str, Any]) -> bool:
        """Return True if the event passes all filters."""
        # Normalize commonly used fields
        network = event.get("network") or event.get("network_short") or ""
        sport = event.get("sport") or event.get("sport_abbr") or ""
        league = event.get("league_name") or event.get("league_abbr") or ""
        event_type = event.get("event_type") or ""
        language = event.get("language") or ""

        # Networks
        if not self._match_in_set(network, self.enabled_networks):
            return False
        if self.exclude_networks and self._match_in_set(network, self.exclude_networks):
            return False

        # Sports
        if not self._match_in_set(sport, self.enabled_sports):
            return False
        if self.exclude_sports and self._match_in_set(sport, self.exclude_sports):
            return False

        # Leagues
        if not self._match_in_set(league, self.enabled_leagues, partial=self.partial_league_match):
            return False
        if self.exclude_leagues and self._match_in_set(league, self.exclude_leagues, partial=self.partial_league_match):
            return False

        # Event types
        if not self._match_in_set(event_type, self.enabled_event_types):
            return False
        if self.exclude_event_types and self._match_in_set(event_type, self.exclude_event_types):
            return False

        # Languages
        if not self._match_in_set(language, self.enabled_languages):
            return False
        if self.exclude_languages and self._match_in_set(language, self.exclude_languages):
            return False

        # ESPN+ / PPV
        packages_info = self._check_packages(event.get("packages"))

        if self.require_espn_plus is not None:
            is_espn_plus = packages_info["is_espn_plus"] or (
                network and "ESPN+" in network.upper()
            )
            if self.require_espn_plus and not is_espn_plus:
                return False
            if not self.require_espn_plus and is_espn_plus:
                return False

        if self.exclude_ppv and packages_info["is_ppv"]:
            return False

        # Re-air
        if self.exclude_reair:
            is_reair = event.get("is_reair")
            if isinstance(is_reair, str):
                is_reair_flag = is_reair.strip().lower() in ("true", "yes", "1")
            else:
                is_reair_flag = bool(is_reair)
            if is_reair_flag:
                return False

        # Non-sport events
        if self.exclude_no_sport and not sport:
            return False

        return True

    # ------------------------------------------------------------------
    # Summaries & signatures
    # ------------------------------------------------------------------

    def get_filter_summary(self) -> str:
        """Return a human-friendly summary of active filters."""

        def format_set(s: Optional[Set[str]]) -> str:
            if s is None:
                return "All (*)"
            if not s:
                return "None (blocked)"
            values = sorted(s)
            head = ", ".join(values[:10])
            return head + ("..." if len(values) > 10 else "")

        # Detect "no filters at all" situation
        no_sets = (
            self.enabled_networks is None
            and not self.exclude_networks
            and self.enabled_sports is None
            and not self.exclude_sports
            and self.enabled_leagues is None
            and not self.exclude_leagues
            and self.enabled_event_types is None
            and not self.exclude_event_types
            and self.enabled_languages is None
            and not self.exclude_languages
        )
        no_flags = (
            self.require_espn_plus is None
            and not self.exclude_ppv
            and not self.exclude_reair
            and not self.exclude_no_sport
        )

        if no_sets and no_flags:
            return "No filters active (all events included)"

        lines: List[str] = ["Active Filters:"]

        if self.enabled_networks is not None or self.exclude_networks:
            lines.append(f"  Networks: {format_set(self.enabled_networks)}")
            if self.exclude_networks:
                lines.append(f"    Excluding: {format_set(self.exclude_networks)}")

        if self.enabled_sports is not None or self.exclude_sports:
            lines.append(f"  Sports: {format_set(self.enabled_sports)}")
            if self.exclude_sports:
                lines.append(f"    Excluding: {format_set(self.exclude_sports)}")

        if self.enabled_leagues is not None or self.exclude_leagues:
            lines.append(f"  Leagues: {format_set(self.enabled_leagues)}")
            if self.exclude_leagues:
                lines.append(f"    Excluding: {format_set(self.exclude_leagues)}")

        if self.enabled_event_types is not None or self.exclude_event_types:
            lines.append(f"  Event Types: {format_set(self.enabled_event_types)}")
            if self.exclude_event_types:
                lines.append(f"    Excluding: {format_set(self.exclude_event_types)}")

        if self.enabled_languages is not None or self.exclude_languages:
            lines.append(f"  Languages: {format_set(self.enabled_languages)}")
            if self.exclude_languages:
                lines.append(f"    Excluding: {format_set(self.exclude_languages)}")

        if self.require_espn_plus is not None:
            lines.append(f"  ESPN+ Required: {self.require_espn_plus}")

        if self.exclude_ppv:
            lines.append("  Exclude PPV: True")

        if self.exclude_reair:
            lines.append("  Exclude Re-Air Events: True")

        if self.exclude_no_sport:
            lines.append("  Exclude Non-Sport Content: True (studio shows, news)")

        lines.append(f"  Case-insensitive matching: {self.case_insensitive}")
        lines.append(f"  Partial league match: {self.partial_league_match}")

        return "\n".join(lines)

    def config_signature(self) -> str:
        """Return a stable hash representing the effective filter config.

        This is used by refresh_in_container.py to detect filter changes
        across runs, regardless of whether they came from env vars or INI.
        """
        payload = {
            "enabled_networks": sorted(self.enabled_networks) if self.enabled_networks is not None else None,
            "exclude_networks": sorted(self.exclude_networks),
            "enabled_sports": sorted(self.enabled_sports) if self.enabled_sports is not None else None,
            "exclude_sports": sorted(self.exclude_sports),
            "enabled_leagues": sorted(self.enabled_leagues) if self.enabled_leagues is not None else None,
            "exclude_leagues": sorted(self.exclude_leagues),
            "enabled_event_types": sorted(self.enabled_event_types) if self.enabled_event_types is not None else None,
            "exclude_event_types": sorted(self.exclude_event_types),
            "enabled_languages": sorted(self.enabled_languages) if self.enabled_languages is not None else None,
            "exclude_languages": sorted(self.exclude_languages),
            "require_espn_plus": self.require_espn_plus,
            "exclude_ppv": self.exclude_ppv,
            "exclude_reair": self.exclude_reair,
            "exclude_no_sport": self.exclude_no_sport,
            "case_insensitive": self.case_insensitive,
            "partial_league_match": self.partial_league_match,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def filter_events_from_db(conn: sqlite3.Connection, filter_config: EventFilter) -> List[str]:
    """Apply filters to events in the DB and return included event IDs."""
    cursor = conn.cursor()

    # NOTE: Column names/order must match the DB schema created by db_migrate.py.
    # We select only fields that are relevant to filtering.
    cursor.execute(
        """
        SELECT
            id,
            network_short,
            sport,
            sport_abbr,
            league_name,
            league_abbr,
            packages,
            event_type,
            language,
            is_reair
        FROM events
        """
    )

    included_ids: List[str] = []
    total = 0

    for row in cursor.fetchall():
        total += 1
        event = {
            "id": row[0],
            "network_short": row[1],
            "sport": row[2],
            "sport_abbr": row[3],
            "league_name": row[4],
            "league_abbr": row[5],
            "packages": row[6],
            "event_type": row[7],
            "language": row[8],
            "is_reair": row[9],
        }
        if filter_config.should_include(event):
            included_ids.append(event["id"])

    filtered_out = total - len(included_ids)
    print(f"[filter] Total events: {total}, Included: {len(included_ids)}, Filtered out: {filtered_out}", flush=True)
    return included_ids


if __name__ == "__main__":
    # Simple CLI for debugging filters against a DB:
    #   python3 filter_events.py /app/data/eplus_vc.sqlite3 /app/filters.ini
    import sys

    if len(sys.argv) < 2:
        print("Usage: filter_events.py <db_path> [filters.ini]", file=sys.stderr)
        sys.exit(1)

    db_path = sys.argv[1]
    config_path = sys.argv[2] if len(sys.argv) > 2 else "filters.ini"

    filt = EventFilter(config_path, use_env=True)
    print(filt.get_filter_summary())
    print()

    conn = sqlite3.connect(db_path)
    ids = filter_events_from_db(conn, filt)
    conn.close()

    print("\nFirst 10 included event IDs:")
    for eid in ids[:10]:
        print(f"  {eid}")
