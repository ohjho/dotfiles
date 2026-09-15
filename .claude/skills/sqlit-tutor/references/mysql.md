# MySQL (8.x) specifics

Everything here was exercised against MySQL 8.4 through `sqlit query`. Older 5.7 servers
lack window functions and backward index scans; check `SELECT VERSION()` first.

## Inspection

```sql
SELECT DATABASE(), VERSION();

SHOW INDEX FROM t;                      -- Key_name, Seq_in_index, Column_name, Cardinality, Non_unique
SHOW CREATE TABLE t;                    -- full DDL, when you need engine/charset/partitioning

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't'
ORDER BY ORDINAL_POSITION;

SELECT TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME, CARDINALITY
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('a','b')
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

SELECT TABLE_NAME, TABLE_ROWS, ROUND(DATA_LENGTH/1e9,1) data_gb, ROUND(INDEX_LENGTH/1e9,1) idx_gb
FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('a','b');
-- TABLE_ROWS is an estimate; COUNT(*) on the PK for the truth when it matters.

SHOW VARIABLES WHERE Variable_name IN
  ('max_execution_time','wait_timeout','interactive_timeout','net_read_timeout','net_write_timeout');
```

Sampling the newest rows cheaply: `WHERE id > (SELECT MAX(id) - 100000 FROM t)` walks the
tail of the primary key. Use it to check null ratios, enum values, and id↔date monotonicity
without scanning history.

## EXPLAIN

`EXPLAIN SELECT …` returns one row per table in join order with `type`, `possible_keys`,
`key`, `rows`, `filtered`, `Extra` (definitions in `concepts.md`). `EXPLAIN FORMAT=TREE`
prints the nested execution tree with cost estimates and is easier to read for deep joins.
`EXPLAIN ANALYZE` executes the query to report actual rows and times; treat it as running
the query, with all the guardrails that implies.

Signs to react to:

- Driving table is a small dimension (`rows` in the hundreds) followed by a `ref` step with
  thousands of rows per probe: the plan fans out before filtering.
- `range` on a `create_date` index estimating millions of rows: a date-window driver that
  will multiply through every child.
- `possible_keys` lists the index you want but `key` is another one or NULL: cardinality
  misestimate, candidate for `FORCE INDEX`.
- `rows` larger than the table: the estimate is broken; do not trust the choice it led to.

## Steering

```sql
SELECT STRAIGHT_JOIN …  FROM a JOIN b … ;             -- keep written join order
FROM players_found PPF FORCE INDEX (`Index 2`)        -- pin an index; back-quote odd names
FROM t USE INDEX (idx_a, idx_b)                       -- narrow candidates, scan still allowed
FROM t IGNORE INDEX (idx_bad)
```

Optimizer hints (`/*+ JOIN_ORDER(a,b) INDEX(t idx) */`) exist in 8.x and are the more
surgical form; the table-level hints above are what most readers recognise.

MySQL rewrites `IN (SELECT …)` and derived tables into semijoins/joins, so they do not
change the plan. A scalar subquery (`>= (SELECT MIN(id) …)`) is evaluated once and yields a
constant range bound; EXPLAIN shows it as a separate `SUBQUERY` row.

## Useful 8.x features

- Window functions: `ROW_NUMBER() OVER (PARTITION BY g ORDER BY …)` for per-group ranking.
- Backward index scans: `ORDER BY pk DESC LIMIT n` over a `ref` on a secondary index reads
  newest-first and stops early (`Extra: Backward index scan`).
- `UNION ALL` of parenthesised `SELECT … ORDER BY … LIMIT n` blocks keeps each block's limit.
- Descending and functional indexes exist, so an index on `(created_date)` or on an
  expression is possible if the owner wants one.

## Gotchas met in practice

- Each `sqlit query` call is a fresh session: `SET SESSION max_execution_time = …`, user
  variables and temp tables do not persist into the next call. Put a per-statement limit
  in the query itself with `SELECT /*+ MAX_EXECUTION_TIME(300000) */ …` when you want the
  server to cut a probe off.
- `max_execution_time = 0` with a connection reset after ~25 minutes means a proxy or tunnel
  is dropping idle-looking connections. Chunk the work; the server was not the limit.
- Auto-named indexes (`Index 4`) are per table. Print the mapping before quoting one.
- `Cardinality` in `SHOW INDEX` comes from sampled statistics; `ANALYZE TABLE` refreshes it
  but is a write-ish operation on a production replica. Note the suspicion, do not run it.
- Comparing `datetime` to a `'YYYY-MM-DD'` string works (midnight), but `> '2026-09-08'`
  excludes rows at exactly midnight; mention it if the boundary matters.
- `VARCHAR` filters like `match_type = 'number'` use the column collation; no index helps
  unless the column is inside a composite index after the equality prefix.
