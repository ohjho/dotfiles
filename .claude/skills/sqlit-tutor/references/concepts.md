# Concepts

Short, consistent framings for the ideas the skill teaches. Each entry says what the thing
is, why it matters for speed, and the shape it took in a real tuning session (a request →
people_found → players_found chain on MySQL, six huge rosters, an 8-month window). Reuse the
framing; swap in the user's tables.

## Reading a plan

**EXPLAIN.** Asks the optimizer how it *would* run the query without running it. Free, so
always first. Each output row is one table in join order.

**Driving table.** The first row of the plan. Every later table is probed once per row that
survives from the tables before it, so a bad driving table multiplies everything after it.
Starting from a 178-row `rosters` table looked cheap but forced a walk through most of a
32M-row child table before the date filter was ever checked.

**Access type** (`type` column, MySQL names; other engines have equivalents):
- `ALL` — full table scan. Sometimes correct for tiny tables, otherwise a red flag.
- `index` — full scan of an index instead of the table.
- `range` — a slice of an index (`>=`, `BETWEEN`, `IN`).
- `ref` — index lookup that can return several rows per probe (non-unique index).
- `eq_ref` — one row per probe via a unique or primary key. The cheapest join step.

**`rows` and `filtered`.** `rows` is the estimated number of rows examined at that step;
`filtered` the estimated share that survives the WHERE conditions applied there. Multiply
down the plan to see the fan-out. These are estimates from statistics, not measurements.

**`Extra` hints worth naming.** `Using index` (covering: no row fetch), `Using index
condition` (predicate checked inside the index before fetching), `Using where` (filter
after fetch), `Using temporary` (GROUP BY / DISTINCT staging), `Backward index scan`
(reading an index newest-first, what makes `ORDER BY id DESC LIMIT n` stop early).

## Predicates and indexes

**Selective predicate.** One that discards most rows. Speed comes from applying the most
selective predicate first, through an index. When the selective predicates live on a table
the plan reaches late, millions of rows are built and thrown away.

**Single-column vs composite index.** A composite index sorts rows by column A, then B
within A, then C within B. It can serve a query that pins a leading prefix with equalities
and then ranges on the next column; it cannot skip a leading column. Three single-column
indexes on the same table do not add up to this: the engine picks one and filters the rest
row by row.

**Column order rule.** Equality columns first (an `IN (…)` list counts as equality, one
probe per value), then the single range column, then columns the query reads so the index
is *covering*. `(roster_id, match_type, request_id, people_found_id)` turned each roster into
a tight slice from `(120, 'number', <first id in window>)` forward, and never touched the
table rows.

**Covering index.** Every column the query needs from that table is in the index, so the
row itself is never fetched. Shows as `Using index`.

**Left-prefix rule, in reverse.** Drop the leading column from the query and the composite
index becomes useless for that query. Say which shapes an index will not serve before
recommending it.

**Cardinality.** The optimizer's estimate of distinct values in an index, refreshed from
sampled statistics. When it is wrong the plan is wrong: an `IN` list of six rosters was
estimated at more rows than the whole table, so the roster index looked hopeless and the
optimizer scanned instead.

**Auto-named indexes.** Tools that create indexes without a name produce `Index 2`,
`Index 3`… The number is per table, so `Index 2` is request_id on one table and something
else on its neighbour. Back-quote them in hints; better, tell the owner to name them.

**Time-ordered surrogate keys.** An auto-increment id grows with the row's creation time, so
`id >= (SELECT MIN(id) FROM t WHERE created > X)` is an indexed stand-in for a date filter
on tables that have no indexed date. Verify with a sample; the ordering is not perfect, and
boundary rows can differ by a handful either way. Keep the real date check as a trailing
primary-key join when that matters.

**A date column that means something else.** `created_date` on a derived table often records
when the derived row was (re)computed, not when the source event happened. Measure the lag
against the parent's date in a sample before offering it as a filter.

## Steering the optimizer

**STRAIGHT_JOIN (MySQL).** Forces the join order as written. Use it when you have shown with
EXPLAIN that the optimizer's order is the problem. It is a hint, so document why it is there.

**FORCE INDEX vs USE INDEX.** `FORCE INDEX` makes a table scan look prohibitively expensive so
the named index is used if it can be; `USE INDEX` only narrows the candidates and still
allows a scan. Both are brittle: they break if the index is renamed or dropped and they hide
a better index added later. Fine in an ad-hoc analysis; in shipped code prefer the right
index and no hint.

**Scalar subquery vs IN-subquery vs derived table.** A scalar subquery (`>= (SELECT MIN(id)
…)`) runs once and yields a range bound: cheap and useful. `IN (SELECT …)` and
`JOIN (SELECT …) d` are rewritten by modern optimizers into ordinary joins (semijoin
flattening), so they do not change the plan; join order still decides everything.

**Dropping a join.** A table joined only to filter on a column the child already carries, or
only for columns available elsewhere, costs one probe per surviving row for nothing. Remove
it, or demote it to a trailing `eq_ref` on the primary key if exactness needs it.

## Shaping results

**Newest N per group, cheaply.** One small query per group over the group's index with
`ORDER BY id DESC LIMIT N`, combined with `UNION ALL`. Each block reads the index backward
and stops after N hits. Seconds even on tens of millions of rows.

**Random N per group.** `ROW_NUMBER() OVER (PARTITION BY g ORDER BY RAND())` then
`WHERE rn <= N`. Has to see every candidate, so it costs the same as a full count over the
window and needs the same chunking. Deterministic variants (`ORDER BY id DESC`) still scan.

**Groups smaller than N.** Return fewer rows; exact equality across groups means picking N
no larger than the smallest group's total, which the count query tells you.

## Measuring honestly

**Count, don't select.** `SELECT COUNT(*)` with the same joins and WHERE has the same plan as
the wide select and no transfer cost, and it is not truncated by a client row limit.

**Cold vs warm.** The first query pulls pages from disk into the buffer pool; the second one
finds them there. A candidate measured after the original ran on the same window will look
faster than it is. Run the candidate cold first, or compare on disjoint windows, and say
which you did.

**Chunking.** Splitting a range by month or id band bounds each call under connection
limits and gives a per-chunk cost to extrapolate from. Identical per-chunk counts between
two shapes are evidence the rewrite is equivalent.

**Server timeout vs connection reset.** `max_execution_time = 0` means the server will run
forever; a "lost connection" after ~25 minutes then points at a proxy, load balancer, or VPN
tunnel. The query may be fine and simply too long for the path; chunk it.

**Never run the known-slow original in full.** Its slowness is the premise. A baseline is
nice; tying up a shared replica for half an hour to confirm it is not. Time the original on
a small window if a comparison is wanted.
