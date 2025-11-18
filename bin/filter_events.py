#!/usr/bin/env python3
"""
Event filtering for ESPN4CC4C
Reads filters.ini and/or environment variables and applies filters to events from the database.
Environment variables take precedence over INI file settings.
"""
import configparser
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class EventFilter:
    """Filters events based on configuration"""

    def __init__(self, config_path: str = "filters.ini", use_env: bool = True):
        self.config_path = Path(config_path)
        self.use_env = use_env
        self.config = self._load_config()
        self._parse_filters()

    def _load_config(self) -> configparser.ConfigParser:
        """Load filter configuration from INI file and/or environment variables"""
        config = configparser.ConfigParser()

        # Load from INI file if it exists
        if self.config_path.exists():
            config.read(self.config_path)
            print(f"[filter] Loaded configuration from: {self.config_path}")
            if "filters" not in config:
                config["filters"] = {}
        else:
            print(f"[filter] No INI file found at {self.config_path}, using defaults")
            # Set defaults if no INI file
            config["filters"] = {}

        # Apply defaults for any missing keys
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
            if key not in config["filters"]:
                config["filters"][key] = default_value

        # Override with environment variables if use_env is True
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

            env_overrides = []
            for env_var, config_key in env_mapping.items():
                env_value = os.environ.get(env_var)
                if env_value is not None:
                    # Trim surrounding quotes if present
                    if len(env_value) >= 2 and env_value[0] == env_value[-1] and env_value[0] in ('"', "'"):
                        env_value = env_value[1:-1]
                    config["filters"][config_key] = env_value
                    env_overrides.append(f"{env_var}={env_value}")
            
            if env_overrides:
                print(f"[filter] Applied {len(env_overrides)} environment variable override(s):")
                for override in env_overrides:
                    print(f"[filter]   {override}")

        return config

    def _parse_filters(self):
        """Parse configuration into filter sets"""
        f = self.config["filters"]

        # Parse options
        self.case_insensitive = f.get("case_insensitive", "true").lower() == "true"
        self.partial_league_match = (
            f.get("partial_league_match", "true").lower() == "true"
        )

        # Parse network filters
        self.enabled_networks = self._parse_set(f.get("enabled_networks", "*"))
        self.exclude_networks = self._parse_set(f.get("exclude_networks", ""))

        # Parse sport filters
        self.enabled_sports = self._parse_set(f.get("enabled_sports", "*"))
        self.exclude_sports = self._parse_set(f.get("exclude_sports", ""))

        # Parse league filters
        self.enabled_leagues = self._parse_set(f.get("enabled_leagues", "*"))
        self.exclude_leagues = self._parse_set(f.get("exclude_leagues", ""))

        # Parse event type filters
        self.enabled_event_types = self._parse_set(f.get("enabled_event_types", "*"))
        self.exclude_event_types = self._parse_set(f.get("exclude_event_types", ""))

        # Parse language filters
        self.enabled_languages = self._parse_set(f.get("enabled_languages", "*"))
        self.exclude_languages = self._parse_set(f.get("exclude_languages", ""))

        # Parse ESPN+ / PPV filters
        self.require_espn_plus = self._parse_bool(f.get("require_espn_plus", ""))
        self.exclude_ppv = f.get("exclude_ppv", "false").lower() == "true"

        # Parse Re-Air filter
        self.exclude_reair = f.get("exclude_reair", "false").lower() == "true"

        # Parse studio show / non-sport filter
        self.exclude_no_sport = f.get("exclude_no_sport", "false").lower() == "true"

    def _parse_set(self, value: str) -> Optional[Set[str]]:
        """Parse comma-separated string into set, handling wildcards"""
        value = value.strip()

        if not value or value.lower() in ("", "none"):
            return set()  # Empty set = block all (nothing passes this filter)

        if value in ("*", "all"):
            return None  # None = allow all (no filtering applied)

        # Split by comma and normalize
        items = {s.strip() for s in value.split(",") if s.strip()}

        if self.case_insensitive:
            items = {s.lower() for s in items}

        return items

    def _parse_bool(self, value: str) -> Optional[bool]:
        """Parse boolean config value, None if empty"""
        value = value.strip().lower()
        if not value:
            return None
        return value in ("true", "yes", "1", "on")

    def _normalize(self, value: Optional[str]) -> str:
        """Normalize string for comparison"""
        if not value:
            return ""
        return value.lower() if self.case_insensitive else value

    def _match_in_set(
        self,
        value: Optional[str],
        filter_set: Optional[Set[str]],
        partial: bool = False,
    ) -> bool:
        """Check if value matches filter set"""
        if filter_set is None:  # None = include all
            return True

        if not value:
            return False

        norm_value = self._normalize(value)

        if partial:
            # Partial matching: check if any filter item is substring of value
            return any(item in norm_value or norm_value in item for item in filter_set)
        else:
            # Exact matching
            return norm_value in filter_set

    def _check_packages(self, packages_json: Optional[str]) -> Dict[str, bool]:
        """Parse packages JSON and check for ESPN+ and PPV"""
        result = {"is_espn_plus": False, "is_ppv": False}

        if not packages_json:
            return result

        try:
            packages = json.loads(packages_json)
            if not isinstance(packages, list):
                return result

            for pkg in packages:
                pkg_upper = pkg.upper()
                if "ESPN_PLUS" in pkg_upper or "ESPNPLUS" in pkg_upper:
                    result["is_espn_plus"] = True
                if "PPV" in pkg_upper:
                    result["is_ppv"] = True
        except (json.JSONDecodeError, TypeError):
            pass

        return result

    def should_include(self, event: Dict[str, Any]) -> bool:
        """
        Determine if an event should be included based on filters.

        Args:
            event: Dict with keys: network, network_short, sport, sport_abbr,
                   league_name, league_abbr, packages, event_type, language

        Returns:
            True if event passes all filters, False otherwise
        """
        # Network filtering
        network = event.get("network") or event.get("network_short")
        if self.enabled_networks is not None:  # If filtering is active
            if not self._match_in_set(network, self.enabled_networks):
                return False
        if self.exclude_networks:  # Exclusions always apply
            if self._match_in_set(network, self.exclude_networks):
                return False

        # Sport filtering
        sport = event.get("sport") or event.get("sport_abbr")
        if self.enabled_sports is not None:
            if not self._match_in_set(sport, self.enabled_sports):
                return False
        if self.exclude_sports:
            if self._match_in_set(sport, self.exclude_sports):
                return False

        # League filtering (with partial matching option)
        league = event.get("league_name") or event.get("league_abbr")
        if self.enabled_leagues is not None:
            if not self._match_in_set(
                league, self.enabled_leagues, partial=self.partial_league_match
            ):
                return False
        if self.exclude_leagues:
            if self._match_in_set(
                league, self.exclude_leagues, partial=self.partial_league_match
            ):
                return False

        # Event type filtering
        event_type = event.get("event_type")
        if self.enabled_event_types is not None:
            if not self._match_in_set(event_type, self.enabled_event_types):
                return False
        if self.exclude_event_types:
            if self._match_in_set(event_type, self.exclude_event_types):
                return False

        # Language filtering
        language = event.get("language")
        if self.enabled_languages is not None:
            if not self._match_in_set(language, self.enabled_languages):
                return False
        if self.exclude_languages:
            if self._match_in_set(language, self.exclude_languages):
                return False

        # ESPN+ / PPV filtering
        packages_info = self._check_packages(event.get("packages"))

        # Check ESPN+ requirement
        if self.require_espn_plus is not None:
            # Also check network for ESPN+ (some events only marked there)
            is_espn_plus = (
                packages_info["is_espn_plus"] or network and "ESPN+" in network.upper()
            )

            if self.require_espn_plus and not is_espn_plus:
                return False
            if not self.require_espn_plus and is_espn_plus:
                return False

        # Check PPV exclusion
        if self.exclude_ppv and packages_info["is_ppv"]:
            return False

        # Check Re-Air exclusion
        if self.exclude_reair:
            is_reair = event.get("is_reair")
            if is_reair == 1 or is_reair is True:
                return False

        # Exclude events with no sport (studio shows, talk shows, news programs)
        # These typically don't have valid ESPN deeplinks
        if self.exclude_no_sport:
            sport = event.get("sport") or event.get("sport_abbr")
            if not sport:
                return False

        return True

    def get_filter_summary(self) -> str:
        """Return a human-readable summary of active filters"""
        lines = ["Active Filters:"]

        def format_set(s):
            if s is None:
                return "All (*)"
            if not s:
                return "None (blocked)"  # Empty set blocks everything
            return ", ".join(sorted(s)[:10]) + ("..." if len(s) > 10 else "")

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
            lines.append(f"  Exclude PPV: {self.exclude_ppv}")

        if self.exclude_reair:
            lines.append("  Exclude Re-Air Events: True")

        if self.exclude_no_sport:
            lines.append("  Exclude Non-Sport Content: True (studio shows, news)")

        if len(lines) == 1:
            return "No filters active (all events included)"

        return "\n".join(lines)


def filter_events_from_db(conn, filter_config: EventFilter) -> List[str]:
    """
    Apply filters to events in database and return list of event IDs to include.

    Args:
        conn: sqlite3 connection
        filter_config: EventFilter instance

    Returns:
        List of event IDs that pass filters
    """
    cursor = conn.cursor()

    # Fetch all events with filter-relevant fields
    cursor.execute(
        """
        SELECT id, network, network_short, sport, sport_abbr,
               league_name, league_abbr, packages, event_type, language,
               is_reair
        FROM events
    """
    )

    included_ids = []
    total = 0

    for row in cursor:
        total += 1
        event = {
            "id": row[0],
            "network": row[1],
            "network_short": row[2],
            "sport": row[3],
            "sport_abbr": row[4],
            "league_name": row[5],
            "league_abbr": row[6],
            "packages": row[7],
            "event_type": row[8],
            "language": row[9],
            "is_reair": row[10],
        }

        if filter_config.should_include(event):
            included_ids.append(event["id"])

    filtered_count = total - len(included_ids)
    print(
        f"[filter] Total events: {total}, Included: {len(included_ids)}, Filtered out: {filtered_count}"  # noqa: E501
    )

    return included_ids


# CLI for testing
if __name__ == "__main__":
    import sqlite3
    import sys

    if len(sys.argv) < 2:
        print("Usage: python filter_events.py <db_path> [filters.ini]")
        sys.exit(1)

    db_path = sys.argv[1]
    config_path = sys.argv[2] if len(sys.argv) > 2 else "filters.ini"

    # Load filters
    filters = EventFilter(config_path)
    print(filters.get_filter_summary())
    print()

    # Apply to database
    conn = sqlite3.connect(db_path)
    included_ids = filter_events_from_db(conn, filters)
    conn.close()

    print("\nFirst 10 included event IDs:")
    for eid in included_ids[:10]:
        print(f"  {eid}")
