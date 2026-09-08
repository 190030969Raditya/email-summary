"""Command-line entry point."""

import argparse
import imaplib
import json
import os
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from email_agent.agent import demo_digest, summarize
from email_agent.mailbox import Email, read_emails


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def write_digest(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement avoids publishing a partial digest on failure.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read Gmail and save a Markdown summary")
    parser.add_argument("--demo", action="store_true", help="offline sample; no credentials needed")
    parser.add_argument("--since", type=date.fromisoformat, help="inclusive date: YYYY-MM-DD")
    parser.add_argument("--days", type=positive, default=1, help="look back N days (default: 1)")
    parser.add_argument("--limit", type=positive, default=20, help="newest N matches (default: 20)")
    parser.add_argument("--unread", action="store_true", help="only unread messages")
    parser.add_argument("--output", type=Path, default=Path("output/digest.md"))
    args = parser.parse_args(argv)
    load_dotenv()
    try:
        if args.demo:
            emails = [
                Email(
                    "demo-1",
                    "alex@example.com",
                    "Project review",
                    "2026-09-07",
                    "Please review the project proposal by September 10. Alex owns the draft.",
                ),
                Email(
                    "demo-2",
                    "team@example.com",
                    "Weekly update",
                    "2026-09-07",
                    "The migration is complete. No action is required.",
                ),
            ]
            digest = demo_digest(emails)
        else:
            required = ["GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "OPENAI_API_KEY"]
            missing = [key for key in required if not os.getenv(key)]
            if missing:
                raise ValueError("Missing configuration: " + ", ".join(missing))
            emails = read_emails(
                "imap.gmail.com",
                993,
                os.environ["GMAIL_ADDRESS"],
                os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""),
                os.getenv("GMAIL_MAILBOX", "INBOX"),
                args.since or datetime.now(UTC).date() - timedelta(days=args.days),
                args.limit,
                args.unread,
            )
            with OpenAI(timeout=60, max_retries=2) as client:
                digest = summarize(emails, client, os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
        now = datetime.now(UTC).isoformat(timespec="seconds")
        report = f"# Email digest\n\nGenerated: {now} | Emails: {len(emails)}\n\n{digest}"
        write_digest(args.output, report)
        print(f"Saved digest for {len(emails)} email(s) to {args.output}")
        return 0
    except (
        ValueError,
        OSError,
        RuntimeError,
        imaplib.IMAP4.error,
        OpenAIError,
        json.JSONDecodeError,
    ) as error:
        # Provider errors can contain sensitive request content, so do not echo them.
        detail = (
            str(error)
            if isinstance(error, (ValueError, RuntimeError))
            else (f"{type(error).__name__}: check credentials, connectivity, and provider access")
        )
        print(f"Error: {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
