#!/usr/bin/env python3
"""
setup_db.py — Initialize SQLite database and optionally create DynamoDB tables.

Usage:
  uv run setup_db.py                # SQLite only
  uv run setup_db.py --dynamodb     # SQLite + DynamoDB tables
"""

import os
import sqlite3
import sys
from pathlib import Path

DB_DIR = Path(__file__).parent / "db"
SQLITE_DB = DB_DIR / "kiro.db"
ENV_FILE = Path(__file__).parent / ".env"
DEFAULT_REGION = "ap-southeast-1"


def load_env_region():
    """Read AWS_REGION from .env if it exists."""
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("AWS_REGION="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return None


def setup_sqlite():
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
    conn.close()
    print(f"✅ SQLite database initialized at {SQLITE_DB}")


def setup_dynamodb(region):
    try:
        import boto3
    except ImportError:
        print("❌ boto3 not installed. Run: pip install boto3")
        sys.exit(1)

    dynamodb = boto3.resource("dynamodb", region_name=region)

    for table_name in ["kiro-bookmarks", "kiro-info"]:
        try:
            table = dynamodb.Table(table_name)
            table.load()
            print(f"✅ DynamoDB table '{table_name}' already exists in {region}")
        except dynamodb.meta.client.exceptions.ResourceNotFoundException:
            print(f"Creating DynamoDB table '{table_name}' in {region}...")
            dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {"AttributeName": "chat_id", "KeyType": "HASH"},
                    {"AttributeName": "ts", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "chat_id", "AttributeType": "S"},
                    {"AttributeName": "ts", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            print(f"✅ DynamoDB table '{table_name}' created in {region}")
        except Exception as e:
            print(f"❌ Failed to access '{table_name}': {e}")


def main():
    use_dynamodb = "--dynamodb" in sys.argv

    # Determine region
    region = input(f"AWS region [{DEFAULT_REGION}]: ").strip() or DEFAULT_REGION

    env_region = load_env_region()
    if env_region and env_region != region:
        print(f"⚠️  Warning: .env has AWS_REGION={env_region} but you entered {region}")
        proceed = input("Continue anyway? [y/N] ").strip().lower()
        if proceed not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)

    setup_sqlite()

    if use_dynamodb:
        setup_dynamodb(region)
    else:
        print("ℹ️  Skipping DynamoDB setup. Use --dynamodb to create tables.")

    print("\n✅ Setup complete.")


if __name__ == "__main__":
    main()
