# Installing from the image

Each release is published as `ghcr.io/tropotek/esky`, tagged with its version
(`:0.1.0`) and `:latest`. An install from the image needs no source checkout:
just a folder holding a compose file, an optional `.env`, and `data/`.

## Fresh install

```bash
mkdir esky && cd esky
curl -fsSLo docker-compose-live.yml \
  https://raw.githubusercontent.com/tropotek/esky/main/docker-compose-example.yml
cat > .env <<'ENV'
ESKY_BIND=192.168.0.12
ESKY_PORT=8011
ESKY_UID=1000
ESKY_GID=1000
ENV
mkdir data
docker compose -f docker-compose-live.yml up -d
curl -s http://192.168.0.12:8011/health        # -> {"status":"ok"}
```

Then create a profile and issue its token, as in the
[README](https://github.com/tropotek/esky#set-up-a-profile), with
`docker compose -f docker-compose-live.yml exec esky esky …` in place of
`docker compose exec esky esky …`.

`docker-compose-live.yml` is the name `livesites.sh` looks for. Any name works
if you don't use it.

## Upgrading

```bash
docker compose -f docker-compose-live.yml pull
docker compose -f docker-compose-live.yml up -d
docker compose -f docker-compose-live.yml exec esky esky profile list
```

`pull_policy: always` means a plain stop and start also picks up a new
`:latest`. To stay on one release instead, set `ESKY_TAG=0.1.0` in `.env`.

If the release notes say the schema changed, run
`esky profile migrate <name>` for every profile. If the embedding model
changed, run `esky profile reindex <name>` too.

`docker compose exec esky env | grep ESKY_VERSION` shows which release is
running.

## Moving an existing install

All the state is in `data/`, one SQLite file per profile. Tokens are stored in
each profile's file, so clients keep working once they point at the new
address.

1. Stop the old server: `docker compose stop esky`.
2. Copy `data/*.db` into the new install's `data/`.
3. Start the new install and check `/health` and `/api/profiles`.
4. Point each client at the new URL, as in [connecting](connecting.md).

## Backups

Stop the container, or snapshot each file with
`sqlite3 data/<profile>.db ".backup <dest>"`, and archive `data/`.
