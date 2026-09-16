# Deploy TAG to tag.trykobi.com

## Server and DNS

The pilot needs a Linux VPS with Docker Engine and the Compose plugin. Allow 2 CPU cores, 2–4 GB RAM and 20 GB disk initially; Andy’s stated 32-core / 42 GB VPS is ample. This is a planning estimate, not a load-test result.

Point the DNS A record `tag.trykobi.com` at the VPS’s public IPv4 address. Add an AAAA record only if that VPS serves IPv6 correctly. Allow inbound TCP 80 and 443, and restrict SSH to the administrator. Do not expose PostgreSQL or Gunicorn directly. If ports 80/443 already serve another application, adapt the existing reverse proxy instead of starting the supplied Caddy service unchanged.

## First launch

```sh
git clone https://github.com/andykirkpublic-cmd/TAG.git
cd TAG
cp .env.example .env
openssl rand -hex 32
```

Put the generated value in `POSTGRES_PASSWORD` in `.env`, and set `SCHOOL_NAME`. Keep `PUBLIC_URL=https://tag.trykobi.com`. Use a hex password so it is safe in the database connection URL. Protect `.env` with `chmod 600 .env`.

```sh
docker compose up -d --build
docker compose exec app python -m tag.manage create-staff --email YOUR_EMAIL --name 'YOUR_NAME'
docker compose ps
curl --fail https://tag.trykobi.com/healthz
```

The migration service creates the schema before the application starts. Caddy obtains and renews HTTPS certificates once DNS and ports are correct. The application runs as an unprivileged container user. PostgreSQL is accessible only on the internal Compose network.

Sign in, add a parent account, privately share its temporary password, create a child and pair a virtual device. Use fictional details for the first walkthrough. For an entirely fictional demo, run `docker compose exec app python -m tag.manage demo` **instead of** creating the first staff account; demo seeding refuses nonempty databases.

## Acceptance walkthrough

1. Sign in as staff in one browser and a parent in another. Pair `/device` in a third browser context.
2. Send a NOTICE from the parent. Check it changes from queued to delivered, then acknowledge on the device. Confirm the parent sees the acknowledgement.
3. Send a QUESTION and answer NO. Confirm the recorded response cannot change.
4. Hold the device’s left button for three seconds. Confirm both staff and parent see the same help request. Mark it seen as parent; school’s receipt remains independent. Resolve as staff after checking.
5. Stop the device browser, wait 30 seconds, and check that the dashboard shows it offline. Send a message, reopen the device, and confirm it arrives.
6. Sign in as an unrelated parent and verify they cannot see the other child or alert. Test device revocation.

## Account administration

```sh
docker compose exec app python -m tag.manage create-staff --email PERSON_EMAIL --name 'PERSON_NAME'
docker compose exec app python -m tag.manage reset-password --email PERSON_EMAIL
docker compose exec app python -m tag.manage disable-account --email PERSON_EMAIL
docker compose exec app python -m tag.manage prune
```

Resetting a password revokes existing account sessions and issues a temporary password that must be changed. Disabling an account revokes sessions and prevents login. Sessions expire after 12 hours. Device pairing lasts until re-pairing, revocation or cookie expiry (one year); losing browser storage requires pairing again.

## Backups and restoration

Back up PostgreSQL regularly, encrypt the backup and keep an off-server copy. The frequency and retention must be agreed before real use. A database backup contains personal information, hashed credentials and message content.

```sh
docker compose exec -T db pg_dump -U tag -d tag --format=custom > tag-backup.dump
```

For a restoration drill, use a **separate test database**. Never test restore by overwriting the live database:

```sh
docker compose exec db createdb -U tag tag_restore_test
docker compose exec -T db pg_restore -U tag -d tag_restore_test --no-owner < tag-backup.dump
```

Verify child/message/alert counts and application access against that test database before declaring the backup usable. Keep `.env` and DNS/proxy configuration safely recoverable too. PostgreSQL and Caddy data are held in named volumes; `docker compose down -v` destroys those volumes and must not be used on the live installation.

## Updates and monitoring

Take a backup first. Pull the intended reviewed commit, then run `docker compose up -d --build`. Check `/healthz`, container health and one message round trip. Follow logs with `docker compose logs --tail=100 app caddy`. Request bodies and passwords are not intentionally logged; protect infrastructure logs nonetheless.

This initial version uses idempotent schema creation, not a versioned migration framework. Future schema changes need explicit migration scripts and backup/rollback instructions. Do not assume rolling back code also rolls back database structure.

Monitor uptime, disk space and backup success. The school must designate who keeps its dashboard open and handles help alerts. In-app alert visibility is not proof that an adult has seen it; the separate receipt records adult acknowledgement.

## Before real-child use

Agree guardian verification, who can administer school accounts, retention/deletion handling and a response procedure with the school. Only grant staff accounts to people entitled to see all pilot children and messages. Complete the school’s relevant data-protection and security review. This repository supplies software, not certification of legal compliance or a safety-critical communications service.
