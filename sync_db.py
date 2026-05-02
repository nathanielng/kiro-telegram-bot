#!/usr/bin/env python3
"""
sync_db.py — Consolidate bookmark/info JSON files into SQLite and optionally sync to DynamoDB.

Usage:
  uv run sync_db.py              # JSON → SQLite only
  uv run sync_db.py --dynamodb   # JSON → SQLite → DynamoDB

Designed to run as a cron job:
  */15 * * * * cd ~/kiro-telegram-bot && uv run sync_db.py --dynamodb >> log/sync_db.log 2>&1

Environment variables (for DynamoDB sync):
  AWS_REGION              - AWS region (default: us-west-2)
  DYNAMODB_TABLE_BOOKMARKS - DynamoDB table for bookmarks (default: kiro-bookmarks)
  DYNAMODB_TABLE_INFO      - DynamoDB table for info notes (default: kiro-info)
"""

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DB_DIR = Path(__file__).parent / "db"
SQLITE_DB = DB_DIR / "kiro.db"


def init_sqlite():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL,
        text TEXT NOT NULL,
        ts TEXT NOT NULL,
        UNIQUE(chat_id, text, ts)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL,
        text TEXT NOT NULL,
        ts TEXT NOT NULL,
        UNIQUE(chat_id, text, ts)
    )""")
    conn.commit()
    return conn


def sync_json_to_sqlite(conn):
    """Read all bookmark/info JSON files and insert into SQLite."""
    count = 0
    for pattern, table in [("bookmarks_*.json", "bookmarks"), ("info_*.json", "info")]:
        for fp in DB_DIR.glob(pattern):
            chat_id = fp.stem.split("_", 1)[1]
            try:
                items = json.loads(fp.read_text())
            except Exception as e:
                logging.warning(f"Skipping {fp}: {e}")
                continue
            for item in items:
                try:
                    conn.execute(
                        f"INSERT OR IGNORE INTO {table} (chat_id, text, ts) VALUES (?, ?, ?)",
                        (chat_id, item["text"], item["ts"]),
                    )
                    count += 1
                except sqlite3.IntegrityError:
                    pass
    conn.commit()
    logging.info(f"SQLite sync: processed {count} records")
    return count


def sync_to_dynamodb(conn):
    """Sync SQLite records to DynamoDB."""
    try:
        import boto3
    except ImportError:
        logging.error("boto3 not installed — cannot sync to DynamoDB")
        return

    region = os.environ.get("AWS_REGION", "ap-southeast-1")
    table_bookmarks = os.environ.get("DYNAMODB_TABLE_BOOKMARKS", "kiro-bookmarks")
    table_info = os.environ.get("DYNAMODB_TABLE_INFO", "kiro-info")

    dynamodb = boto3.resource("dynamodb", region_name=region)

    for table_name, sql_table in [(table_bookmarks, "bookmarks"), (table_info, "info")]:
        try:
            table = dynamodb.Table(table_name)
            table.load()
        except Exception as e:
            logging.warning(f"DynamoDB table '{table_name}' not accessible: {e}. Skipping.")
            continue

        rows = conn.execute(f"SELECT chat_id, text, ts FROM {sql_table}").fetchall()
        count = 0
        with table.batch_writer() as batch:
            for chat_id, text, ts in rows:
                batch.put_item(Item={"chat_id": chat_id, "ts": ts, "text": text})
                count += 1
        logging.info(f"DynamoDB sync: wrote {count} records to {table_name}")


def main():
    use_dynamodb = "--dynamodb" in sys.argv
    conn = init_sqlite()
    sync_json_to_sqlite(conn)
    if use_dynamodb:
        sync_to_dynamodb(conn)
    conn.close()
    logging.info("Sync complete.")


if __name__ == "__main__":
    main()
