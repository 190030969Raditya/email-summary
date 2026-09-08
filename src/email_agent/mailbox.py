"""IMAP retrieval and MIME parsing, without changing message flags."""

import imaplib
import ssl
from dataclasses import asdict, dataclass
from datetime import date
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser

import certifi


@dataclass
class Email:
    uid: str
    sender: str
    subject: str
    date: str
    body: str

    def payload(self) -> dict:
        return asdict(self)


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "br", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def parse_email(uid: str, raw: bytes, max_chars: int = 12000) -> Email:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    part = message.get_body(preferencelist=("plain", "html"))
    body = ""
    if part is not None and part.get_content_disposition() != "attachment":
        try:
            body = part.get_content()
        except (LookupError, UnicodeError):
            body = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if part.get_content_type() == "text/html":
            parser = HTMLText()
            parser.feed(body)
            body = "".join(parser.parts)
    body = body.strip()
    if len(body) > max_chars:
        body = body[:max_chars] + "\n[Body truncated]"
    return Email(
        uid,
        str(message.get("From", "Unknown"))[:1000],
        str(message.get("Subject", "(no subject)"))[:1000],
        str(message.get("Date", "Unknown"))[:200],
        body,
    )


def read_emails(
    host: str,
    port: int,
    username: str,
    password: str,
    mailbox: str,
    since: date,
    limit: int,
    unread: bool,
) -> list[Email]:
    # English month names are required by IMAP regardless of the system locale.
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    imap_date = f"{since.day:02d}-{months[since.month - 1]}-{since.year}"
    with imaplib.IMAP4_SSL(
        host, port, ssl_context=ssl.create_default_context(cafile=certifi.where()), timeout=30
    ) as client:
        client.login(username, password)
        status, _ = client.select(mailbox, readonly=True)
        if status != "OK":
            raise RuntimeError("Cannot select the configured mailbox")
        criteria = ["SINCE", imap_date]
        if unread:
            criteria.append("UNSEEN")
        status, data = client.uid("search", None, *criteria)
        if status != "OK":
            raise RuntimeError("Email search failed")
        uids = (data[0] or b"").split()[-limit:]
        emails = []
        for uid in reversed(uids):
            status, items = client.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                raise RuntimeError("Email retrieval failed; no digest was written")
            raw = next((item[1] for item in items if isinstance(item, tuple)), None)
            if raw is None:
                raise RuntimeError("Email disappeared during retrieval; retry the run")
            emails.append(parse_email(uid.decode("ascii"), raw))
        return emails
