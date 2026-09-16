import os
import sqlite3
from flask import current_app, g


def db():
    if 'db' not in g:
        url = current_app.config['DATABASE_URL']
        if url.startswith('postgresql://'):
            import psycopg
            from psycopg.rows import dict_row
            g.db = psycopg.connect(url, row_factory=dict_row)
        else:
            path = url.removeprefix('sqlite:///')
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            g.db = sqlite3.connect(path, timeout=15)
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
            g.db.execute('PRAGMA journal_mode=WAL')
    return g.db


def execute(sql, args=()):
    if current_app.config['DATABASE_URL'].startswith('postgresql://'):
        sql = sql.replace('?', '%s')
    return db().execute(sql, args)


def one(sql, args=()):
    row = execute(sql, args).fetchone()
    return dict(row) if row else None


def rows(sql, args=()):
    return [dict(r) for r in execute(sql, args).fetchall()]


def init_db():
    from pathlib import Path
    for statement in Path(__file__).with_name('schema.sql').read_text().split(';'):
        if statement.strip():
            execute(statement)
    db().commit()


def close_db(error=None):
    connection = g.pop('db', None)
    if connection:
        connection.close()
