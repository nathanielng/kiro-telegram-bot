#!/usr/bin/env python3
"""
kiro_interactive.py — PTY-based interactive Kiro CLI runner.

When kiro-cli pauses mid-execution and displays a prompt or question, the
accumulated output is forwarded to the user via Telegram and the subprocess
waits for a reply before continuing.

If Kiro never asks a question the function behaves like a normal blocking
subprocess call and simply returns the full output when Kiro exits.

--------------------------------------------------------------------------
Integration with telegram_bot.py (minimal diff)
--------------------------------------------------------------------------

1. Import this module at the top of telegram_bot.py:

       from kiro_interactive import run_kiro_interactive

2. Replace the invoke_kiro() call inside the main loop with:

       reply, new_files = invoke_kiro(...)   # existing non-interactive call
       # — or —
       reply, offset = run_kiro_interactive(
           prompt          = user_text,
           api_key         = api_key,
           chat_id         = chat_id,
           last_update_id  = offset - 1,
       )
       # offset is now updated to skip replies consumed inside the call

   Note: run_kiro_interactive() does not return a new_files list; wire up
   the folder monitor (folder_monitor.py) for file-change detection instead.

3. The `offset` returned is the highest Telegram update_id consumed during
   interactive prompts.  Feed it back into the main polling loop so those
   messages are not re-processed:

       reply, offset = run_kiro_interactive(...)
       offset += 1   # next getUpdates call will start after this id
--------------------------------------------------------------------------
"""

import os
import pty
import re
import select
import subprocess
import time

import requests


# ---------------------------------------------------------------------------
# Tuneable constants
# ---------------------------------------------------------------------------

# Seconds of output silence before we inspect the buffer for a prompt.
SILENCE_THRESHOLD: float = 0.5

# How long (seconds) to wait for the Telegram user to reply before giving up
# and terminating the subprocess.
USER_REPLY_TIMEOUT: int = 300

# Overall cap on a single Kiro session (matches telegram_bot.py default).
DEFAULT_TIMEOUT: int = 300


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHFJA-Za-z]')

# Patterns on the *last non-empty line* that suggest a prompt waiting for
# user input.  The primary signal is a missing trailing newline (see
# _looks_like_prompt), but the regex catches question-style lines too.
_PROMPT_RE = re.compile(
    r'(\?\s*$'          # ends with ?
    r'|\(y[/|]n\)'      # (y/n) or (y|n)
    r'|yes/no'          # yes/no anywhere on the line
    r'|>\s*$'           # bare > shell-style prompt
    r'|Enter\s+\S'      # "Enter something:"
    r'|Choose\s+\S'     # "Choose an option:"
    r'|Please\s+\S'     # "Please provide:"
    r'|Input\s+\S'      # "Input value:"
    r'|:\s*$)',         # ends with colon — very common prompt ending
    re.IGNORECASE,
)


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from *text*."""
    return _ANSI_RE.sub('', text)


def _looks_like_prompt(text: str) -> bool:
    """Return True when *text* looks like the process is waiting for input.

    Two complementary signals are checked:

    1. **No trailing newline** — interactive prompts almost always leave the
       cursor mid-line (e.g. ``"Continue? (y/n) "``).  Normal output lines
       are terminated with ``\\n``.
    2. **Prompt keyword** on the last non-empty line (``?``, ``(y/n)``,
       ``Enter``, ``:``, …).
    """
    clean = _strip_ansi(text)
    if not clean.strip():
        return False

    # Primary signal: output does not end with a newline.
    if not clean.rstrip('\r').endswith('\n'):
        return True

    # Fallback: last meaningful line matches a known prompt pattern.
    lines = clean.split('\n')
    last = next((l.rstrip('\r') for l in reversed(lines) if l.strip()), '')
    return bool(_PROMPT_RE.search(last))


def _send_telegram(api_key: str, chat_id: str, text: str) -> None:
    """Send *text* to *chat_id*, truncating to Telegram's 4 096-char limit."""
    try:
        requests.post(
            f'https://api.telegram.org/bot{api_key}/sendMessage',
            json={'chat_id': chat_id, 'text': _strip_ansi(text)[:4096]},
            timeout=10,
        )
    except Exception as exc:
        print(f'[kiro_interactive] Telegram send error: {exc}')


def _poll_telegram_reply(
    api_key: str,
    chat_id: str,
    after_id: int,
    timeout: int = USER_REPLY_TIMEOUT,
) -> tuple:
    """Block until the user sends a new message in *chat_id*.

    Only messages with ``update_id > after_id`` are considered, so messages
    that were already consumed by the caller's main loop are skipped.

    Returns
    -------
    ``(reply_text, update_id)`` on success, or ``(None, after_id)`` on timeout.
    """
    offset = after_id + 1
    deadline = time.time() + timeout

    while time.time() < deadline:
        remaining = int(deadline - time.time())
        poll_secs = min(10, max(1, remaining))

        try:
            resp = requests.get(
                f'https://api.telegram.org/bot{api_key}/getUpdates',
                params={'offset': offset, 'timeout': poll_secs},
                timeout=poll_secs + 5,
            )
            data = resp.json()
        except Exception as exc:
            print(f'[kiro_interactive] getUpdates error: {exc}')
            time.sleep(2)
            continue

        for update in data.get('result', []):
            uid = update['update_id']
            offset = uid + 1
            msg = update.get('message', {})
            if str(msg.get('chat', {}).get('id', '')) == str(chat_id):
                text = msg.get('text', '').strip()
                if text:
                    return text, uid

    return None, after_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_kiro_interactive(
    prompt: str,
    api_key: str,
    chat_id: str,
    last_update_id: int = 0,
    kiro_args: list = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple:
    """Run ``kiro-cli chat <prompt>`` inside a pseudo-terminal (PTY).

    The PTY tricks kiro-cli into thinking it is connected to a real terminal,
    so interactive prompts are displayed exactly as they would be in a shell.

    Whenever kiro-cli stops producing output for ``SILENCE_THRESHOLD`` seconds
    and the buffer ends on something that looks like a question/prompt, this
    function:

    1. Forwards the prompt text to *chat_id* via Telegram.
    2. Blocks (polling Telegram) until the user replies or
       ``USER_REPLY_TIMEOUT`` seconds pass.
    3. Writes the user's reply into the subprocess stdin and resumes.

    If kiro-cli never asks a question, the function runs to completion and
    returns the full terminal output — identical behaviour to a plain
    ``subprocess.run()`` call.

    Parameters
    ----------
    prompt          : str   — the user prompt to pass to kiro-cli
    api_key         : str   — Telegram Bot API key
    chat_id         : str   — Telegram chat ID to forward prompts to
    last_update_id  : int   — highest Telegram update_id already processed by
                              the caller; consumed replies will have higher IDs
                              (pass ``offset - 1`` from your main loop)
    kiro_args       : list  — extra CLI flags inserted *before* <prompt>,
                              e.g. ``['--model', 'sonnet']`` (default: none)
    timeout         : int   — overall wall-clock timeout in seconds

    Returns
    -------
    ``(output: str, last_update_id: int)``

    *output* is the complete terminal output with ANSI codes stripped.
    *last_update_id* is the highest Telegram update_id consumed while waiting
    for user replies; add 1 and assign it to your main loop's ``offset``.
    """
    cmd = ['kiro-cli', 'chat'] + (kiro_args or []) + [prompt]

    # ------------------------------------------------------------------
    # Open a pseudo-terminal pair.
    # master_fd  — the parent reads/writes here to talk to the child.
    # slave_fd   — the child's stdin/stdout/stderr; looks like a tty.
    # ------------------------------------------------------------------
    master_fd, slave_fd = pty.openpty()

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
    except FileNotFoundError:
        os.close(master_fd)
        os.close(slave_fd)
        return 'Error: kiro-cli not found on PATH.', last_update_id
    except Exception as exc:
        os.close(master_fd)
        os.close(slave_fd)
        return f'Error starting kiro-cli: {exc}', last_update_id

    # Parent only needs the master end; close slave so EOF propagates.
    os.close(slave_fd)

    full_output = ''    # everything received from the subprocess
    pending_buf = ''    # output accumulated since the last handled prompt
    last_data_ts = time.time()
    silence_checked = False   # True after we checked and found no prompt
    deadline = time.time() + timeout

    try:
        while time.time() < deadline:
            exited = proc.poll() is not None

            # ----------------------------------------------------------
            # Drain all data currently available on the master fd.
            # ----------------------------------------------------------
            got_data = False
            while True:
                try:
                    r, _, _ = select.select([master_fd], [], [], 0.0)
                except (ValueError, OSError):
                    exited = True
                    break
                if not r:
                    break
                try:
                    chunk = os.read(master_fd, 4096).decode('utf-8', errors='replace')
                except OSError:
                    exited = True
                    break
                if not chunk:
                    exited = True
                    break
                full_output += chunk
                pending_buf += chunk
                last_data_ts = time.time()
                got_data = True
                silence_checked = False   # new data — re-arm the silence check

            if exited:
                break

            # ----------------------------------------------------------
            # Silence check: if no data for SILENCE_THRESHOLD seconds and
            # we haven't already checked this silence window, inspect
            # pending_buf for an interactive prompt.
            # ----------------------------------------------------------
            silence = time.time() - last_data_ts
            if (not got_data
                    and silence >= SILENCE_THRESHOLD
                    and pending_buf
                    and not silence_checked):

                silence_checked = True   # only act once per silence window

                if _looks_like_prompt(pending_buf):
                    # Forward the prompt to the Telegram user.
                    _send_telegram(
                        api_key, chat_id,
                        f'Kiro asks:\n\n{_strip_ansi(pending_buf).strip()}',
                    )

                    reply, last_update_id = _poll_telegram_reply(
                        api_key, chat_id, last_update_id,
                        timeout=USER_REPLY_TIMEOUT,
                    )

                    if reply is None:
                        _send_telegram(
                            api_key, chat_id,
                            'No reply received within the timeout window — '
                            'terminating Kiro session.',
                        )
                        proc.terminate()
                        break

                    # Write the user's answer into the subprocess stdin.
                    try:
                        os.write(master_fd, (reply + '\n').encode())
                    except OSError:
                        break

                    # Clear the buffer so the next prompt gets fresh context.
                    pending_buf = ''
                    last_data_ts = time.time()
                    silence_checked = False

            # Brief sleep to avoid a busy-wait spin.
            time.sleep(0.05)

    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    return _strip_ansi(full_output), last_update_id
