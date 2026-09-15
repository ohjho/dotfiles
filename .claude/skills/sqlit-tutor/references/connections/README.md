# Per-connection notes

One file per saved `sqlit` connection, named exactly as `sqlit connections list` prints it
(for example `riq-prod-readonly.md`). The skill reads the matching file before its first
query and appends facts as it verifies them, so later sessions start from what earlier ones
learned instead of re-inventorying the same tables.

Record structure and behaviour, not data. Index lists, which ids are monotonic with which
dates, what a confusingly named column actually means, how long a query can run before the
connection drops. Never paste result rows, ids of real records, or anything that identifies
a person. Row counts are fine with a date stamp because they help size a query; they are
not the data itself.

These files are committed with the skill. Ask the user before committing new notes; do not
commit on your own.

## Template

```markdown
# <connection name>

## Connection
- Engine / version:
- User is read-only: yes / no / unknown
- Default database:
- Timeouts: `max_execution_time` = , `wait_timeout` = ; observed connection resets after ~N min (proxy/tunnel, not server)
- Access notes (VPN / tunnel needed, replica lag, etc.):

## Tables

### <table>
Rows: ~N (YYYY-MM-DD). Primary key: `<col>`.

| Index | Columns (in order) | Notes |
|---|---|---|
| PRIMARY | id | |
| `Index 4` | roster_id | auto-named; back-quote in hints |

Key semantics:
- `<col>`: what it really means, nullability surprises, enum values seen.

## Time-ordered keys
- `<child>.<id>` grows with `<parent>.<date>`; sampled N rows, K% off by more than a day, worst lag X. Good as a range bound; boundary rows may differ by a handful.

## Pitfalls
- e.g. `<table>.created_date` is a reprocessing timestamp, not the event date.
- e.g. a handful of group ids hold most of `<big table>`; the optimizer estimates their IN list above the table size and picks the wrong index.

## Queries worth remembering
Short description + the final shape (no result data), with the measured time and window.
```
