# TfL Intelligence

Victoria line status and topology ingestion using Python, SQLAlchemy and PostgreSQL.
The backend can connect to Supabase or local PostgreSQL using `DATABASE_URL`.

## Configuration

Copy `.env.example` to `.env` at the repository root, then set `DATABASE_URL` to
your database connection string. For Supabase, copy the Session pooler URI from
the project's Connect dialog, insert the URL-encoded database password, and add
`sslmode=require`. Keep credentials in `.env`, which is ignored by Git.

`TFL_APP_KEY` is optional. `TFL_BASE_URL` defaults to `https://api.tfl.gov.uk`.

## Manual setup and collection

Run these commands from `backend/`:

```bash
uv sync --python 3.12
uv run python -m app.database
uv run python -m app.topology
```

The database setup command creates missing tables without dropping existing ones.
It enables row-level security for the application tables and revokes access from
Supabase's `anon` and `authenticated` API roles when those roles exist. The
backend's table-owner connection can still read and write. This phase accesses
the database through the backend, without browser API access.

`create_all()` does not alter existing table definitions. Changing an existing
column still requires a deliberate SQL schema change or a migration.

The topology command is a one-shot import of the Victoria line's inbound and
outbound route sequences. It validates both responses before updating metadata,
upserts lines and stations, and replaces route ordering in a single transaction.
Successful imports append two original responses to `collection_runs`, including
TfL's route geometry. Failed HTTP requests and invalid responses are also logged
there; if either direction fails, the existing topology is preserved.

Repeating the import updates current metadata without duplicating stations or
route positions. `route_sequence` and `stop_order` are numbered from 1 in TfL's
response order. The original branch identifiers remain available in the raw JSON.
Historical collection records are never replaced by a topology import.

For status collection:

```bash
uv run python -m app.ingestion
uv run python -m app.ingestion --loop
```

The first command collects once; the second polls approximately every 60 seconds
until stopped with Ctrl+C. Topology imports run separately; no background topology
schedule is installed.

## Inspect topology

In Supabase's Table Editor, inspect `lines`, `stations`, `line_stations` and
`collection_runs`. To list stations in route order, use the SQL Editor:

```sql
SELECT ls.direction, ls.route_sequence, ls.stop_order,
       s.id AS station_id, s.name, s.latitude, s.longitude
FROM public.line_stations AS ls
JOIN public.stations AS s ON s.id = ls.station_id
WHERE ls.line_id = 'victoria'
ORDER BY ls.direction, ls.route_sequence, ls.stop_order;
```

## Optional local PostgreSQL

The root `compose.yaml` starts PostgreSQL with a persistent Docker volume using
the `POSTGRES_*` settings in `.env`. The init SQL creates the original collection
table on first startup; run `python -m app.database` through `uv` as above to
create all application tables.

When using Supabase, Docker is not required. Existing local observations stay in
the Docker volume; switching `DATABASE_URL` does not transfer them automatically.
