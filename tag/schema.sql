CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('staff','parent')), password TEXT NOT NULL,
 must_change INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
 token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS children (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, class_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guardians (
 child_id TEXT NOT NULL REFERENCES children(id), user_id TEXT NOT NULL REFERENCES users(id),
 PRIMARY KEY(child_id,user_id)
);
CREATE TABLE IF NOT EXISTS devices (
 id TEXT PRIMARY KEY, child_id TEXT UNIQUE NOT NULL REFERENCES children(id), token TEXT UNIQUE,
 pairing_hash TEXT UNIQUE, pairing_expires BIGINT, last_seen BIGINT
);
CREATE TABLE IF NOT EXISTS messages (
 id TEXT PRIMARY KEY, child_id TEXT NOT NULL REFERENCES children(id), sender_id TEXT NOT NULL REFERENCES users(id),
 kind TEXT NOT NULL CHECK(kind IN ('NOTICE','QUESTION')), body TEXT NOT NULL,
 created BIGINT NOT NULL, expires BIGINT NOT NULL, delivered BIGINT, response TEXT,
 responded BIGINT, request_key TEXT NOT NULL, UNIQUE(sender_id,request_key),
 CHECK(response IS NULL OR (kind='NOTICE' AND response='ACK') OR (kind='QUESTION' AND response IN ('YES','NO')))
);
CREATE TABLE IF NOT EXISTS alerts (
 id TEXT PRIMARY KEY, child_id TEXT NOT NULL REFERENCES children(id), created BIGINT NOT NULL,
 resolved BIGINT, resolved_by TEXT REFERENCES users(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_alert ON alerts(child_id) WHERE resolved IS NULL;
CREATE TABLE IF NOT EXISTS alert_receipts (
 alert_id TEXT NOT NULL REFERENCES alerts(id), user_id TEXT NOT NULL REFERENCES users(id), seen BIGINT,
 PRIMARY KEY(alert_id,user_id)
);
CREATE TABLE IF NOT EXISTS audit (
 id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, created BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS throttle (
 key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS message_child_time ON messages(child_id,created);
