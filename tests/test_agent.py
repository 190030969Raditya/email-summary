from datetime import date
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from email_agent.agent import summarize
from email_agent.cli import main, write_digest
from email_agent.mailbox import Email, parse_email, read_emails


def sample():
    return Email("1", "a@example.com", "Review", "today", "Review by Friday")


def test_mime_prefers_plain_and_ignores_attachment():
    message = EmailMessage()
    message["Subject"] = "Résumé"
    message.set_content("Actual message")
    message.add_alternative("<p>HTML alternative</p>", subtype="html")
    message.add_attachment(
        b"secret attachment", maintype="application", subtype="octet-stream", filename="secret.txt"
    )
    parsed = parse_email("4", message.as_bytes())
    assert parsed.subject == "Résumé"
    assert parsed.body == "Actual message"


def test_html_removes_script_and_decodes_entities():
    raw = b"Content-Type: text/html\r\n\r\n<script>bad()</script><p>Hello &amp; bye</p>"
    assert parse_email("1", raw).body == "Hello & bye"


def test_truncation():
    assert parse_email("1", b"\r\nabcdef", max_chars=3).body == "abc\n[Body truncated]"


def test_imap_readonly_and_peek():
    with patch("email_agent.mailbox.imaplib.IMAP4_SSL") as factory:
        client = factory.return_value.__enter__.return_value
        client.select.return_value = ("OK", [b"3"])
        client.uid.side_effect = [("OK", [b"1 2 3"]), ("OK", [(b"3", b"\r\nHello")])]
        result = read_emails("host", 993, "user", "password", "INBOX", date(2026, 9, 1), 1, True)
        assert result[0].uid == "3"
        client.select.assert_called_once_with("INBOX", readonly=True)
        assert client.uid.call_args_list[0].args == (
            "search",
            None,
            "SINCE",
            "01-Sep-2026",
            "UNSEEN",
        )
        assert client.uid.call_args_list[1].args == ("fetch", b"3", "(BODY.PEEK[])")


def test_batches_and_no_storage():
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(
        status="completed", output_text="Summary"
    )
    result = summarize([sample()] * 3, client, "test-model", batch_size=2)
    assert result.count("Summary") == 2
    assert client.responses.create.call_count == 2
    assert client.responses.create.call_args.kwargs["store"] is False


def test_empty_mailbox_does_not_call_model():
    client = MagicMock()
    assert "No matching" in summarize([], client, "test")
    client.responses.create.assert_not_called()


def test_incomplete_summary_fails():
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(
        status="incomplete", output_text="Partial"
    )
    with pytest.raises(RuntimeError):
        summarize([sample()], client, "test")


def test_demo_end_to_end(tmp_path):
    output = tmp_path / "digest.md"
    assert main(["--demo", "--output", str(output)]) == 0
    assert "Project review" in output.read_text()
    assert "AI summarization is disabled" in output.read_text()


def test_invalid_limit():
    with pytest.raises(SystemExit):
        main(["--limit", "0"])


def test_atomic_output_preserves_previous_on_failure(tmp_path):
    output = tmp_path / "digest.md"
    output.write_text("previous")
    with patch("pathlib.Path.replace", side_effect=OSError("disk error")), pytest.raises(OSError):
        write_digest(output, "new")
    assert output.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [output]


def test_live_pipeline(tmp_path, monkeypatch):
    for name in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "OPENAI_API_KEY"):
        monkeypatch.setenv(name, "test")
    output = tmp_path / "digest.md"
    with (
        patch("email_agent.cli.read_emails", return_value=[sample()]),
        patch("email_agent.cli.OpenAI") as factory,
    ):
        client = factory.return_value.__enter__.return_value
        client.responses.create.return_value = SimpleNamespace(
            status="completed", output_text="Review proposal by Friday (UID 1)."
        )
        assert main(["--output", str(output)]) == 0
    assert "Review proposal by Friday" in output.read_text()
