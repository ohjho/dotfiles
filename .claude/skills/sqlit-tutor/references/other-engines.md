# Other engines sqlit can reach

The workflow in SKILL.md is engine-agnostic: inventory indexes, read the plan, move the
selective predicates forward, measure fairly, recommend an index. What changes is the
syntax for each step. The notes below come from general knowledge, not from a session that
exercised them; when a claim matters, confirm it against the plan you actually read and say
so if you could not.

## PostgreSQL family (PostgreSQL, Redshift, CockroachDB, Supabase, Aurora PG)

- **Indexes:** `SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 't';` or `\d t`
  is not available through sqlit, so use the catalog query.
- **Columns:** `information_schema.columns` as on MySQL.
- **Sizes:** `SELECT relname, n_live_tup FROM pg_stat_user_tables;`
  `pg_relation_size('t')`.
- **Plan:** `EXPLAIN (FORMAT TEXT) …` for estimates; `EXPLAIN (ANALYZE, BUFFERS) …` executes
  the query, so it counts as running it. Read cost, rows, and node types (Seq Scan, Index
  Scan, Index Only Scan, Bitmap Heap Scan, Nested Loop, Hash Join, Merge Join). "Index Only
  Scan" is the covering case.
- **Steering:** no `STRAIGHT_JOIN`/`FORCE INDEX`. Join order can be pinned with
  `SET join_collapse_limit = 1` (session-scoped, so it does not survive between sqlit calls)
  or by restructuring with CTEs marked `MATERIALIZED`. The `pg_hint_plan` extension adds
  hints if installed. Usually the better lever is `ANALYZE t` (owner) and a composite index.
- **Stats:** `pg_stats` shows `n_distinct` and correlation; a low correlation on an id column
  weakens the "id is a date proxy" trick.
- **Sampling:** `TABLESAMPLE SYSTEM (1)` for cheap approximate samples; `ROW_NUMBER()` and
  `LATERAL` joins for per-group top-N (`JOIN LATERAL (SELECT … ORDER BY id DESC LIMIT n)`),
  which stops early like the UNION ALL pattern.
- **Redshift** has no secondary indexes: think sort keys and dist keys instead, and
  `SVL_QUERY_SUMMARY` for what actually ran. CockroachDB accepts `EXPLAIN` and index hints
  as `t@index_name`.

## SQLite

- **Indexes:** `PRAGMA index_list('t'); PRAGMA index_info('idx');` or query
  `sqlite_master WHERE type = 'index'`.
- **Plan:** `EXPLAIN QUERY PLAN …`; look for `SCAN t` (full) vs `SEARCH t USING INDEX …`
  and `USING COVERING INDEX`.
- **Steering:** `INDEXED BY idx` forces an index, `NOT INDEXED` forbids one; `CROSS JOIN`
  pins join order. Statistics come from `ANALYZE` (writes `sqlite_stat1`; owner's call).
- Window functions since 3.25; `ORDER BY rowid DESC LIMIT n` is the newest-N idiom.

## DuckDB / MotherDuck

- Columnar and vectorised: there are no secondary indexes to inventory in the usual sense
  (min/max zone maps do the pruning). Ask about partitioning/ordering of the underlying
  files instead.
- **Plan:** `EXPLAIN …` for the tree, `EXPLAIN ANALYZE …` to execute with timings.
- Join order is chosen well; filters are pushed down aggressively. Slow queries are usually
  wide scans of unpruned files or accidental cross products. `PRAGMA enable_profiling`.

## SQL Server (mssql)

- **Indexes:** `sys.indexes` joined to `sys.index_columns` and `sys.columns`;
  `sp_helpindex 't'`.
- **Plan:** `SET SHOWPLAN_ALL ON` / `SET STATISTICS IO, TIME ON` are session settings and
  will not persist across sqlit calls; `EXPLAIN` is not T-SQL. Use
  `SELECT … OPTION (RECOMPILE)` with the plan cache views
  (`sys.dm_exec_query_plan`) when you can, or ask the user to capture the actual plan in
  their client.
- **Steering:** `OPTION (FORCE ORDER)` for join order, `WITH (INDEX(idx))` table hint,
  `OPTION (MAXDOP n)`. Included columns make an index covering:
  `CREATE INDEX … ON t (a, b) INCLUDE (c)`.
- Top-N per group: `CROSS APPLY (SELECT TOP (n) … ORDER BY id DESC)`.

## Warehouses (BigQuery, Snowflake, Trino/Presto/Athena, Databricks, ClickHouse)

- No B-tree indexes. The equivalents are partitioning, clustering/sort keys, and pruning
  statistics. Inventory those (`INFORMATION_SCHEMA.PARTITIONS`, `SHOW CREATE TABLE`,
  `system.parts` on ClickHouse).
- **Plan:** `EXPLAIN` exists on all of them with different shapes; the thing to look for is
  whether the partition/cluster column filter reached the scan stage ("partition pruning",
  "bytes scanned"). Cost is usually bytes read, and the dry-run/estimate features
  (BigQuery `--dry_run`, Snowflake query profile) tell you before you pay.
- **Steering:** hints are rare; restructure so the pruned column is filtered directly
  (a constant, not a join to a dimension) and avoid functions on it.
- **Sampling:** `TABLESAMPLE` variants; `QUALIFY ROW_NUMBER() OVER (…) <= n` on Snowflake,
  BigQuery and Databricks is the idiomatic per-group top-N.

## Everything else in sqlit's list

Oracle, DB2, HANA, Teradata, Firebird, Exasol, SurrealDB, osquery, Turso/D1 and the rest:
the same questions apply (what is indexed, what does the plan say, where are the selective
predicates applied), but the syntax is uncertain. Look up the exact commands rather than
guessing, tell the user which parts are unverified, and lean harder on measurement with
small windows.
