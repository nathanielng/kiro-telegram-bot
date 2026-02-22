#!/usr/bin/env python3
"""
Folder Monitor for Kiro CLI Outputs

Watches KIRO_OUTPUT_DIR for new or modified files, optionally redacts PII
from text-based files, uploads them to an S3 bucket, and sends a Telegram
message containing the CloudFront URL of each uploaded file.

Required environment variables:
  KIRO_OUTPUT_DIR       - Directory to monitor
  S3_BUCKET_NAME        - S3 bucket to upload files to
  TELEGRAM_API_KEY      - Telegram bot token
  TELEGRAM_CHAT_ID      - Telegram chat to notify

Optional environment variables:
  S3_PREFIX             - Key prefix within the S3 bucket (default: none)
  CLOUDFRONT_BASE_URL   - Base URL for generating public file URLs
  AWS_REGION            - AWS region (default: us-west-2)
  ENABLE_PII_REDACTION  - "true" to redact PII before upload (default: true)
"""

import hashlib
import logging
import mimetypes
import os
import re
import sys
import time
from pathlib import Path

import boto3
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # env vars can be provided externally

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII patterns
# ---------------------------------------------------------------------------

# Each entry is (compiled_regex, replacement_token).
_PII_PATTERNS = [
    # Email addresses
    (re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'), "[EMAIL]"),
    # US phone numbers (various formats)
    (re.compile(r'\b(\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b'), "[PHONE]"),
    # US Social Security Numbers
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), "[SSN]"),
    # Credit / debit card numbers (16 digits, with optional spaces or dashes)
    (re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'), "[CARD]"),
    # AWS Access Key IDs
    (re.compile(r'\bAKIA[A-Z0-9]{16}\b'), "[AWS_KEY]"),
]

# File extensions and MIME prefixes that are safe to read as text
_TEXT_EXTENSIONS = {
    ".txt", ".md", ".html", ".htm", ".css", ".js", ".ts",
    ".jsx", ".tsx", ".json", ".xml", ".yaml", ".yml",
    ".csv", ".py", ".sh", ".conf", ".cfg", ".ini", ".toml",
    ".log", ".rst", ".tex",
}

_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml",
                       "application/javascript", "application/x-yaml",
                       "application/x-sh", "application/toml")


def _is_text_file(path):
    if path.suffix.lower() in _TEXT_EXTENSIONS:
        return True
    mime, _ = mimetypes.guess_type(str(path))
    return mime and any(mime.startswith(p) for p in _TEXT_MIME_PREFIXES)


def redact_pii(content):
    """Replace PII in *content* with redaction tokens.

    Returns (redacted_content, list_of_summary_strings).
    """
    redacted = content
    summary = []
    for pattern, token in _PII_PATTERNS:
        hits = pattern.findall(redacted)
        if hits:
            summary.append(f"{token}: {len(hits)} occurrence(s)")
            redacted = pattern.sub(token, redacted)
    return redacted, summary


# ---------------------------------------------------------------------------
# S3 uploader
# ---------------------------------------------------------------------------

class S3Uploader:
    def __init__(self, bucket, prefix, region):
        self.bucket = bucket
        self.prefix = prefix.strip("/") if prefix else ""
        self._client = boto3.client("s3", region_name=region)

    def _s3_key(self, file_path, base_dir):
        rel = Path(file_path).relative_to(base_dir)
        return f"{self.prefix}/{rel}" if self.prefix else str(rel)

    @staticmethod
    def _content_type(path):
        mime, _ = mimetypes.guess_type(str(path))
        return mime or "application/octet-stream"

    def upload(self, file_path, base_dir, enable_pii_redaction):
        """Upload *file_path* to S3, returning the S3 key on success."""
        path = Path(file_path)
        key = self._s3_key(path, base_dir)

        try:
            if enable_pii_redaction and _is_text_file(path):
                raw = path.read_text(encoding="utf-8", errors="replace")
                content, summary = redact_pii(raw)
                if summary:
                    log.info("PII redacted from %s: %s", path.name, "; ".join(summary))
                self._client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=content.encode("utf-8"),
                    ContentType=self._content_type(path),
                )
            else:
                self._client.upload_file(
                    str(path),
                    self.bucket,
                    key,
                    ExtraArgs={"ContentType": self._content_type(path)},
                )

            log.info("Uploaded %s -> s3://%s/%s", path.name, self.bucket, key)
            return key

        except Exception as exc:
            log.error("Upload failed for %s: %s", path.name, exc)
            return None


# ---------------------------------------------------------------------------
# Telegram notifier
# ---------------------------------------------------------------------------

class TelegramNotifier:
    def __init__(self, api_key, chat_id):
        self._api_key = api_key
        self._chat_id = chat_id

    def send(self, text):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self._api_key}/sendMessage",
                json={"chat_id": self._chat_id, "text": text},
                timeout=10,
            )
        except Exception as exc:
            log.error("Telegram send failed: %s", exc)


# ---------------------------------------------------------------------------
# Watchdog event handler
# ---------------------------------------------------------------------------

def _file_hash(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class _OutputFolderHandler(FileSystemEventHandler):
    def __init__(self, base_dir, uploader, notifier,
                 cloudfront_base_url, enable_pii_redaction):
        super().__init__()
        self._base_dir = Path(base_dir)
        self._uploader = uploader
        self._notifier = notifier
        self._cf_base = cloudfront_base_url.rstrip("/") if cloudfront_base_url else ""
        self._redact = enable_pii_redaction
        # Track last-seen hash per file to de-duplicate rapid events
        self._seen = {}

    def _should_skip(self, path):
        p = Path(path)
        # Skip hidden files, temp files, and directories
        if p.name.startswith(".") or p.suffix in (".tmp", ".part", ".swp"):
            return True
        return False

    def _handle(self, src_path):
        path = Path(src_path)
        if not path.is_file() or self._should_skip(src_path):
            return

        # Brief pause so the writer can finish flushing
        time.sleep(0.3)

        try:
            current_hash = _file_hash(path)
        except OSError:
            return

        if self._seen.get(src_path) == current_hash:
            return  # already processed this exact version
        self._seen[src_path] = current_hash

        s3_key = self._uploader.upload(path, self._base_dir, self._redact)

        if s3_key and self._cf_base:
            url = f"{self._cf_base}/{s3_key}"
            self._notifier.send(
                f"New file synced to S3:\n"
                f"  File: {path.name}\n"
                f"  URL:  {url}"
            )

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    watch_dir = os.environ.get("KIRO_OUTPUT_DIR", "").strip()
    s3_bucket = os.environ.get("S3_BUCKET_NAME", "").strip()
    s3_prefix = os.environ.get("S3_PREFIX", "").strip()
    cf_base = os.environ.get("CLOUDFRONT_BASE_URL", "").strip()
    region = os.environ.get("AWS_REGION", "us-west-2")
    tg_key = os.environ.get("TELEGRAM_API_KEY", "").strip()
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    enable_redaction_raw = os.environ.get("ENABLE_PII_REDACTION", "true").lower()
    enable_redaction = enable_redaction_raw in ("true", "1", "yes")

    errors = []
    if not watch_dir:
        errors.append("KIRO_OUTPUT_DIR is not set")
    if not s3_bucket:
        errors.append("S3_BUCKET_NAME is not set")
    if not tg_key or not tg_chat:
        errors.append("TELEGRAM_API_KEY and TELEGRAM_CHAT_ID must be set")
    if errors:
        for e in errors:
            print(f"Error: {e}")
        sys.exit(1)

    watch_path = Path(watch_dir)
    watch_path.mkdir(parents=True, exist_ok=True)

    uploader = S3Uploader(s3_bucket, s3_prefix, region)
    notifier = TelegramNotifier(tg_key, tg_chat)

    handler = _OutputFolderHandler(
        base_dir=watch_path,
        uploader=uploader,
        notifier=notifier,
        cloudfront_base_url=cf_base,
        enable_pii_redaction=enable_redaction,
    )

    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=True)
    observer.start()

    log.info("Monitoring: %s", watch_path.resolve())
    log.info("S3 destination: s3://%s/%s", s3_bucket, s3_prefix or "(root)")
    log.info("CloudFront base: %s", cf_base or "(not configured)")
    log.info("PII redaction: %s", "enabled" if enable_redaction else "disabled")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
