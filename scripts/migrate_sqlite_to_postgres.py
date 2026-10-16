#!/usr/bin/env python3
"""One-time offline SQLite -> PostgreSQL migration. Use only after write freeze.

Usage:
  DATABASE_URL=postgresql+psycopg://... python scripts/migrate_sqlite_to_postgres.py \
      --sqlite /data/voice_foundry.db --backup /data/voice_foundry-before-v3.db --dry-run
  DATABASE_URL=... python scripts/migrate_sqlite_to_postgres.py \
      --sqlite /data/voice_foundry.db --backup /data/voice_foundry-before-v3.db

No secrets are printed. Both source backup and count verification are mandatory.
"""
import argparse
import shutil
import sqlite3
import sys
from pathlib import Path
from sqlalchemy import text
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import db
from app.config import get_settings

TABLES=['agents','plans','calls','events','contacts','agent_releases',
        'agent_contact_permissions','memories','memory_events','tasks','missions','mission_events','audit_events']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite',required=True,type=Path)
    parser.add_argument('--backup',required=True,type=Path)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    if not get_settings().database_url.startswith('postgresql'):
        parser.error('DATABASE_URL must point to the target PostgreSQL database')
    if not args.sqlite.is_file(): parser.error('SQLite source does not exist')
    if args.sqlite.resolve()==args.backup.resolve(): parser.error('Backup path must differ from source')
    if args.backup.exists(): parser.error('Backup already exists; refusing overwrite')
    args.backup.parent.mkdir(parents=True,exist_ok=True)
    source=sqlite3.connect(str(args.sqlite));source.row_factory=sqlite3.Row
    with sqlite3.connect(str(args.backup)) as backup: source.backup(backup)
    counts={}
    with source:
        for table in TABLES:
            if not source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                continue
            counts[table]=source.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
    print('Source counts:',counts)
    print('Verified SQLite backup:',args.backup)
    if args.dry_run:
        print('DRY RUN: no PostgreSQL changes were made.')
        return
    db.init_db()
    target=db.engine()
    with target.begin() as conn:
        for table,count in counts.items():
            rows=source.execute(f'SELECT * FROM {table}').fetchall()
            target_columns={c['name'] for c in __import__('sqlalchemy').inspect(conn).get_columns(table)}
            for item in rows:
                fields=[key for key in item.keys() if key in target_columns]
                columns=','.join(f'"{key}"' for key in fields)
                placeholders=','.join(f':{key}' for key in fields)
                conn.execute(text(f'INSERT INTO {table} ({columns}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'),
                             {key:item[key] for key in fields})
            after=conn.execute(text(f'SELECT count(*) FROM {table}')).scalar_one()
            if after<count:
                raise RuntimeError(f'Validation failure {table}: source={count}, target={after}')
            print(f'{table}: source={count}, destination={after}')
    print('Migration committed; validate critical app workflows before switching DATABASE_URL.')

if __name__=='__main__': main()
