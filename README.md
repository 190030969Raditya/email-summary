# Gmail Summary Agent

A Python command-line agent that reads your Gmail inbox, extracts message text, and produces a Markdown digest with key facts, action items, and explicit deadlines using OpenAI. Includes an offline demo, automated tests, and GitHub Actions CI.

## Quick start

Requires Python 3.11 or newer.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
email-agent --demo
cat output/digest.md
```

The demo uses synthetic emails and deterministic excerpts. It makes no network requests and does not demonstrate AI quality.

## Connect Gmail

```sh
cp .env.example .env
chmod 600 .env
```

1. Turn on 2-Step Verification in your Google Account.
2. Open [Google App Passwords](https://myaccount.google.com/apppasswords) and create one named `Email Summary Agent`.
3. Edit `.env`: set `GMAIL_ADDRESS` to your full Gmail address and `GMAIL_APP_PASSWORD` to the generated 16-character password. Spaces in the copied app password are removed automatically. Use an app password, not your normal Google password.
4. Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` to a Responses API model available to your account; the example uses `gpt-4.1-mini`.

The agent connects to Gmail at `imap.gmail.com:993` over TLS. `GMAIL_MAILBOX` defaults to `INBOX`. Start with the default inbox; custom mailbox names must be valid IMAP mailbox arguments.

App passwords require 2-Step Verification and may be unavailable on organization accounts, accounts using security keys exclusively, or accounts with Advanced Protection. This version uses app-password authentication; Google OAuth sign-in is not implemented. See [Google's app-password instructions](https://support.google.com/accounts/answer/185833) and [Gmail IMAP documentation](https://developers.google.com/workspace/gmail/imap/imap-smtp).

```sh
email-agent --days 1 --limit 20
email-agent --unread --since 2026-09-01 --limit 50
email-agent --output output/morning.md
```

Run commands from the project folder so `.env` and relative output paths resolve consistently. `--days` is calculated from the current UTC date. `--since` takes precedence over `--days`. IMAP SINCE filters by the server's internal message date, inclusively at day granularity. The newest matching UIDs are selected, up to the limit. Repeated runs summarize matching emails again; there is no deduplication state. The default output is replaced after each successful run.

## How it works

1. Validate configuration and establish a TLS IMAP connection with a timeout.
2. Select the mailbox read-only, search by date and optionally unread status, and fetch with `BODY.PEEK[]` to preserve read flags.
3. Decode MIME headers and text, prefer plain text over HTML, omit attachments, and cap each body at 12,000 characters. Truncation is labeled.
4. Submit batches of up to 10 emails to the OpenAI Responses API. Each batch produces attention items, FYIs, and a checklist with source UIDs. Multiple batches are separated in the output, rather than globally ranked.
5. Save the complete digest atomically. A failed run returns a nonzero exit code and preserves an existing digest.

Email headers and body text are sent to OpenAI in live mode. The request sets `store=False`; this is not a guarantee of zero provider retention. Email content is treated as untrusted input and the model has no tools. The program does not send emails or modify mailbox flags. Attachments are not summarized, links are not fetched, and output may need human verification. A full raw message is fetched before parsing, so large attachments can still consume memory and bandwidth.

Secrets, local email files, and the default `output/` directory are ignored by Git. Use `output/` for sensitive generated digests; custom output locations may not be ignored.

API reference: [OpenAI Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).

## Tests

```sh
ruff check .
pytest -q
```

Tests cover MIME parsing, HTML conversion, truncation, read-only IMAP calls, model batching, empty inboxes, incomplete responses, atomic output failure, the offline CLI, and the live pipeline with mocked services. Real mailbox/API credentials are required for a live integration test.

## Push to GitHub from scratch

Git tracks the project locally; GitHub hosts the remote copy. From this folder:

```sh
# Only needed if the folder is not already a Git repository:
git init

# Only needed if you have not configured your Git identity:
git config user.name "Your Name"
git config user.email "you@example.com"

git add .
git commit -m "Build Python email summary agent"
gh auth login
gh repo create email-summary-agent --private --source=. --remote=origin --push
```

If the initial commit already exists, skip `git add` and `git commit`. The repository creation command defaults here to private; use `--public` only if you want a public repository. If you already have a remote repository instead:

```sh
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin HEAD
```

For later changes:

```sh
git add .
git commit -m "Describe your change"
git push
```

GitHub CI runs lint, tests, and the offline demo without email or API secrets.
