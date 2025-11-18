# ESPN4CC4C Event Filtering - Environment Variables

## Overview

Event filtering can now be configured via **environment variables** in your `docker-compose.yml` or Docker run command. Environment variables take precedence over `filters.ini` settings.

## Quick Start Example

```yaml
services:
  espn4cc4c:
    image: your-espn4cc4c-image
    environment:
      # Exclude specific networks
      FILTER_EXCLUDE_NETWORKS: "ACCN,ESPN,ESPN2,ESPNDeportes,ESPNU"
      
      # Only include specific sports
      FILTER_ENABLED_SPORTS: "Football,Basketball,Baseball"
      
      # Exclude PPV and Re-Air events
      FILTER_EXCLUDE_PPV: "true"
      FILTER_EXCLUDE_REAIR: "true"
      
      # Only ESPN+ content
      FILTER_REQUIRE_ESPN_PLUS: "true"
```

## All Available Environment Variables

### Network Filtering

- **`FILTER_ENABLED_NETWORKS`** (default: `*`)
  - Comma-separated list of networks to include
  - Use `*` for all networks
  - Example: `ESPN+,SEC Network,ACC Network`

- **`FILTER_EXCLUDE_NETWORKS`** (default: empty)
  - Comma-separated list of networks to exclude
  - Example: `ACCN,ESPN,ESPN2,ESPNDeportes,ESPNU`

### Sport Filtering

- **`FILTER_ENABLED_SPORTS`** (default: `*`)
  - Comma-separated list of sports to include
  - Use `*` for all sports
  - Example: `Football,Basketball,Baseball,Hockey`

- **`FILTER_EXCLUDE_SPORTS`** (default: empty)
  - Comma-separated list of sports to exclude
  - Example: `Golf,Tennis`

### League Filtering

- **`FILTER_ENABLED_LEAGUES`** (default: `*`)
  - Comma-separated list of leagues to include
  - Use `*` for all leagues
  - Example: `NFL,NBA,MLB,NHL`

- **`FILTER_EXCLUDE_LEAGUES`** (default: empty)
  - Comma-separated list of leagues to exclude
  - Example: `MLS,WNBA`

- **`FILTER_PARTIAL_LEAGUE_MATCH`** (default: `true`)
  - Allow partial/substring matching for league names
  - Example: `NCAA` will match `NCAA Football`, `NCAA Basketball`, etc.
  - Set to `false` for exact matching only

### Event Type Filtering

- **`FILTER_ENABLED_EVENT_TYPES`** (default: `*`)
  - Comma-separated list of event types to include
  - Use `*` for all types
  - Example: `Live,Upcoming`

- **`FILTER_EXCLUDE_EVENT_TYPES`** (default: empty)
  - Comma-separated list of event types to exclude
  - Example: `Replay,Condensed`

### Language Filtering

- **`FILTER_ENABLED_LANGUAGES`** (default: `*`)
  - Comma-separated list of languages to include
  - Use `*` for all languages
  - Example: `en,es` (English and Spanish)

- **`FILTER_EXCLUDE_LANGUAGES`** (default: empty)
  - Comma-separated list of languages to exclude
  - Example: `es` (exclude Spanish content)

### Package/Subscription Filtering

- **`FILTER_REQUIRE_ESPN_PLUS`** (default: empty)
  - Set to `true` to only include ESPN+ content
  - Set to `false` to exclude ESPN+ content
  - Leave empty for no ESPN+ filtering

- **`FILTER_EXCLUDE_PPV`** (default: `false`)
  - Set to `true` to exclude Pay-Per-View events
  - Example: `true`

- **`FILTER_EXCLUDE_REAIR`** (default: `false`)
  - Set to `true` to exclude Re-Air/replay events
  - Example: `true`

- **`FILTER_EXCLUDE_NO_SPORT`** (default: `false`)
  - Set to `true` to exclude non-sport content (studio shows, news, talk shows)
  - These typically don't have valid ESPN deeplinks
  - Example: `true`

### General Options

- **`FILTER_CASE_INSENSITIVE`** (default: `true`)
  - Use case-insensitive matching for all filters
  - Set to `false` for case-sensitive matching

## Common Use Cases

### ESPN+ Only (No Cable/Satellite Content)

```yaml
environment:
  FILTER_REQUIRE_ESPN_PLUS: "true"
  FILTER_EXCLUDE_PPV: "true"
  FILTER_EXCLUDE_REAIR: "true"
```

### Exclude All ESPN Linear Networks (Keep ESPN+, SEC, ACC, etc.)

```yaml
environment:
  FILTER_EXCLUDE_NETWORKS: "ESPN,ESPN2,ESPNU,ESPNDeportes,ESPNEWS"
```

### Only Big 4 US Sports

```yaml
environment:
  FILTER_ENABLED_SPORTS: "Football,Basketball,Baseball,Hockey"
  # or
  FILTER_ENABLED_LEAGUES: "NFL,NBA,MLB,NHL"
```

### College Sports Only

```yaml
environment:
  FILTER_ENABLED_LEAGUES: "NCAA"
  FILTER_PARTIAL_LEAGUE_MATCH: "true"
```

### No International Content

```yaml
environment:
  FILTER_ENABLED_LANGUAGES: "en"
  FILTER_EXCLUDE_NETWORKS: "ESPNDeportes"
```

### Live Events Only (No Replays or Studio Shows)

```yaml
environment:
  FILTER_EXCLUDE_REAIR: "true"
  FILTER_EXCLUDE_NO_SPORT: "true"
```

## Priority Order

1. **Environment variables** (highest priority)
2. **filters.ini** file at `/app/filters.ini`
3. **Default values** (all events included)

## Debugging

To see which filters are active, check your container logs during refresh:

```bash
docker logs espn4cc4c-container
```

Look for output like:

```
Step 2/5: Applying event filters...
Active Filters:
  Networks: All (*)
    Excluding: accn, espn, espn2, espndeportes, espnu
  Exclude PPV: True
  Exclude Re-Air Events: True
[filter] Total events: 5000, Included: 2500, Filtered out: 2500
[filter] Removed 2500 events that didn't pass filters
```

## Migration from filters.ini

If you have an existing `filters.ini`, you can keep using it! The environment variables are **optional** and only override specific settings when present.

To migrate, simply copy your settings from `filters.ini` to environment variables:

**filters.ini:**
```ini
[filters]
exclude_networks = ACCN,ESPN,ESPN2
exclude_ppv = true
```

**docker-compose.yml:**
```yaml
environment:
  FILTER_EXCLUDE_NETWORKS: "ACCN,ESPN,ESPN2"
  FILTER_EXCLUDE_PPV: "true"
```

## Notes

- Comma-separated values should have no spaces after commas (or spaces will be included in the filter)
- Values are case-insensitive by default (controlled by `FILTER_CASE_INSENSITIVE`)
- Use `*` to mean "all" (no filtering)
- Use empty string or omit variable to mean "no restriction" for enabled_ variables
- Exclude filters always apply even if enabled filters are set to `*`
