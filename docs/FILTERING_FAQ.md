# ESPN4CC4C Filtering FAQ (Known-Good Scenarios)

This FAQ focuses on **filter combinations that we know behave predictably right now**.  
It’s meant as a practical “recipes” file you can copy into your environment and then verify via:

- `http://<host>:8094/out/filteraudit.html`
- `bin/audit_filters.sh` (from inside the repo)

> ⚠️ Note: The `FILTER_REQUIRE_ESPN_PLUS` flag is currently **experimental** and can easily lead
> to a situation where *0 events match* your filters. For now, the examples below **do not**
> rely on that flag. Stick to these patterns unless you’re debugging.

---

## Q1: How do I run with **no filtering at all**?

If you want the “classic” behavior where everything from the ESPN Watch graph is included,
simply **omit** all `FILTER_*` env vars (or set them to empty). For example:

```yaml
environment:
  # No filtering
  - FILTER_ENABLED_NETWORKS=
  - FILTER_EXCLUDE_NETWORKS=
  - FILTER_ENABLED_LEAGUES=
  - FILTER_EXCLUDE_LEAGUES=
  - FILTER_ENABLED_LANGUAGES=
  - FILTER_EXCLUDE_LANGUAGES=
  - FILTER_EXCLUDE_REAIR=false
```

On refresh you should see something like:

```text
[filter] Total events: 885, Included: 885, Filtered out: 0
```

`filteraudit.html` will show **all** leagues and languages.

---

## Q2: How do I hide **women’s college** (NCAAW, etc.), Spanish feeds, and replays?

This is a very common pattern if you want to keep the guide “clean” but still broad:

```yaml
environment:
  # Leagues: exclude women's variants
  - FILTER_EXCLUDE_LEAGUES=NCAAW,Women's

  # Languages: keep English-only
  - FILTER_EXCLUDE_LANGUAGES=es

  # Event types: no re-airs
  - FILTER_EXCLUDE_REAIR=true

  # Matching behavior (recommended)
  - FILTER_CASE_INSENSITIVE=true
  - FILTER_PARTIAL_LEAGUE_MATCH=true
```

On refresh you should see something like:

```text
[filter] Total events: 762, Included: 370, Filtered out: 392
```

And in `filteraudit.html`:

- **Step 2**: `Languages still present` → only `en`
- **Step 2**: `Leagues still present` → no `ncaaw`, `ncaa women's` strings
- **Step 2**: `Re-airs still present` → `0`
- **Step 3**: `bad_slots_league`, `bad_slots_language_es`, `bad_slots_reair` → all `0`

This scenario has been exercised end-to-end and is **known-good**.

---

## Q3: I already get linear ESPN channels from my provider. How do I avoid **linear dupes**?

This is another common case: you want the ESPN+ / streaming extras but **not** the linear
channels that you already have via cable, TVE, etc.

The safest pattern right now is to **exclude** the linear networks you don’t want, and let
everything else (ESPN+, ESPN3, etc.) flow through:

```yaml
environment:
  # Don't REQUIRE ESPN+ packages (see Q4 for why)
  - FILTER_REQUIRE_ESPN_PLUS=false

  # Exclude known linear networks (you can tweak this list over time)
  - FILTER_EXCLUDE_NETWORKS=ESPN,ESPN2,ESPNU,ESPNEWS,ESPNDEPORTES,SECN,SECN+,ACCN,ACCNX,@ESPN,ESPNUnlimited

  # Optional but recommended
  - FILTER_CASE_INSENSITIVE=true
```

This pattern has been **verified in the wild** to:

- Remove the main ESPN linear networks from the guide
- Keep ESPN+ content
- Keep ESPN3 (since it’s not in the exclude list)

On refresh you should see something like:

```text
[filter] Total events: 883, Included: 478, Filtered out: 405
```

If you still see an unwanted network (e.g., ESPN Deportes), simply add it to `FILTER_EXCLUDE_NETWORKS`
and refresh again. `filteraudit.html` will show you which networks are still present so you can tune
the list.

---

## Q4: Why doesn’t `FILTER_REQUIRE_ESPN_PLUS=true` behave like I expect?

Short answer: **ESPN+ is tagged differently than linear channels**, and the current implementation
of `FILTER_REQUIRE_ESPN_PLUS` is strict enough that it can easily result in **zero events matching**.

In the database:

- ESPN+ events are usually identified by `packages` containing `"ESPN_PLUS"` and often have a
  **blank `network_short`**.
- Linear channels (ESPN, ESPN2, SECN, ACCN, ESPN3, etc.) have a real `network_short` and an
  **empty `packages`** field.

If you combine `FILTER_REQUIRE_ESPN_PLUS=true` with a tight network list (e.g. “Networks: espn+, espn3”),
you can end up in a situation where **no event satisfies both conditions at once**. In that case the log shows:

```text
[filter] Total events: 885, Included: 0, Filtered out: 885
```

For safety, when `Included = 0`, the refresh script **does not delete anything** from the `events` table,
so your guide ends up effectively unfiltered even though the “Active Filters” summary looks correct.

> ✅ Recommendation (for now): Prefer `FILTER_EXCLUDE_NETWORKS` patterns (see Q3) over
> `FILTER_REQUIRE_ESPN_PLUS` for typical setups. Treat `FILTER_REQUIRE_ESPN_PLUS` as **advanced/experimental**
> until it’s improved in a future release.

---

## Q5: How do I know my filters actually worked?

After a refresh, use **both** of these:

1. **Container logs** – look for a line like:

   ```text
   [filter] Total events: 883, Included: 478, Filtered out: 405
   ```

   - If `Included` is **0**, your guide is effectively unfiltered and you should revisit your config.
   - Otherwise, some events were pruned before planning.

2. **HTML audit page** – open:

   ```text
   http://<host>:8094/out/filteraudit.html
   ```

   This page shows:

   - Active filters (Step 1)
   - How many events survived, league & language breakdown (Step 2)
   - Sanity checks that blocked content (e.g. NCAAW, Spanish, re-airs) is **not** in the plan (Step 3)

If all the “bad_slots_*” numbers in Step 3 are `0`, then:

- ✅ Your filters are ON  
- ✅ The DB only contains allowed events  
- ✅ The guide/plan is not using any blocked content  

---

## Q6: I tried a filter combo and the audit shows `Included: 0` but my guide looks unfiltered. Is that a bug?

It’s confusing, but it’s **intentional safety behavior**.

When a filter combo results in `Included: 0`, the refresh script assumes you probably misconfigured
something (instead of really wanting an empty guide). To avoid nuking your data, it **skips deleting**
any events from the DB. The side effect is that the guide uses the full, unfiltered dataset.

If you see this, treat it like an error:

1. Revisit your `FILTER_*` env vars (especially combinations involving `FILTER_REQUIRE_ESPN_PLUS`).
2. Refresh again.
3. Check logs + `filteraudit.html` until `Included` is non-zero and the league/language breakdown
   matches your expectations.

---

## Q7: Where should I start as a “safe default” for most users?

If you’re not sure what you want yet, this is a solid starting point:

```yaml
environment:
  # Hide obvious duplicates / fringe content
  - FILTER_EXCLUDE_LEAGUES=NCAAW,Women's
  - FILTER_EXCLUDE_LANGUAGES=es
  - FILTER_EXCLUDE_REAIR=true

  # Avoid linear ESPN dupes if you already have them elsewhere
  - FILTER_EXCLUDE_NETWORKS=ESPN,ESPN2,ESPNU,ESPNEWS,ESPNDEPORTES,SECN,SECN+,ACCN,ACCNX,@ESPN,ESPNUnlimited

  # Recommended matching behavior
  - FILTER_CASE_INSENSITIVE=true
  - FILTER_PARTIAL_LEAGUE_MATCH=true
```

Then:

1. Run a refresh.  
2. Open `filteraudit.html`.  
3. Adjust the exclude lists as you see what’s actually in your guide.

This pattern has been exercised and is **known to behave well** with the current release.
