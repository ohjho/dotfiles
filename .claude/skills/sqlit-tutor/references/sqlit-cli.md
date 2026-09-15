# sqlit from a shell

`sqlit` (installed at `~/.local/bin/sqlit`, checked against v1.6.4) is a terminal UI for SQL
databases. The UI cannot be driven from a tool call; only the non-interactive subcommands
matter here.

## Preflight

```bash
command -v sqlit && sqlit --version
```

Not installed? Project page: https://github.com/Maxteabag/sqlit. Install command:

```bash
pipx install sqlit-tui
```

Offer both to the user and wait for an explicit yes before running the install. Never
install anything, this tool or a driver it asks for, without the user's permission in the
conversation. (`sqlit` may prompt to install a missing database driver on first connect;
that counts too, so run the first query in the foreground and read its output.)

## Commands you will use

```bash
sqlit connections list                       # saved connections: name, type, host, user
sqlit query -c NAME -q "SQL" -o csv          # one-shot query, CSV to stdout
sqlit query -c NAME -f file.sql -o csv       # same, SQL read from a file
sqlit query -c NAME -q "SQL" -o json         # JSON when you want to parse it
sqlit query -c NAME -q "SQL" -l 0            # lift the default 1000-row limit
sqlit query -c NAME -q "SQL" -d OTHER_DB     # override the connection's default database
```

Flags: `-c/--connection` (required), `-q/--query` or `-f/--file`, `-o/--format`
`{table,csv,json}` (default `table`), `-l/--limit` (default 1000, `0` unlimited),
`-d/--database`.

Temporary, unsaved connections exist too (`sqlit --db-type sqlite --file-path x.db ...`,
`--db-type postgresql --host ... --username ... --password-stdin`). Prefer saved
connections; credentials stay out of the transcript.

`sqlit connections add/edit/delete` change the saved list. Do not run them unless the user
asks to manage connections.

## Habits that keep results readable

- **Multi-line SQL goes in a file.** Write it to the scratchpad and pass `-f`. Quoting a long
  statement inside `-q` breaks on backticks and nested quotes.
- **CSV output has a blank line and a `(N row(s) returned)` line.** Pipe through
  `grep -v '^$'`; keep the row-count line, it is useful evidence.
- **Names with spaces need back-quotes** (MySQL auto-named indexes like `` `Index 4` ``),
  and inside a `-q` double-quoted string the back-quotes need escaping. Another reason to
  use `-f`.
- **The 1000-row default limit truncates silently.** Irrelevant for counts and EXPLAIN;
  pass `-l 0` when you actually need all rows, and think about whether you do.
- **Time a call with the shell**, not by feel:
  ```bash
  s=$(date +%s); sqlit query -c NAME -f q.sql -o csv | grep -v '^$'; echo "elapsed_s=$(( $(date +%s) - s ))"
  ```
  Startup overhead is a fraction of a second, so seconds are fine as a unit.
- **Anything that might take more than a minute runs in the background** with an explicit
  timeout, and you read its output file when the completion notice arrives. Sequence two
  timings inside one background command when their order matters for cold/warm fairness.
- **Each `sqlit query` is its own session.** `SET SESSION ...`, temporary tables, and
  user variables do not carry over to the next call. Put everything a query needs into that
  one statement (scalar subqueries instead of variables).

## Error shapes

- `(2013, 'Lost connection to MySQL server during query ... Connection reset by peer')`
  after a long wait: something between you and the server dropped the connection. Check
  `max_execution_time` and the `*_timeout` variables before blaming the query; if the server
  has no execution limit, the reset came from a proxy or tunnel, and the fix is to chunk the
  work so each call finishes well inside that window.
- `File 'x.sql' not found`: the working directory reset between shell calls. Use absolute
  paths for `-f`.
