"""Synthetic MIME bytes only; no filesystem or production fingerprint logic."""

from email.message import EmailMessage
from email.policy import SMTP


def message(
    *,
    rfc_id: str | None = "<synthetic@example.invalid>",
    date: str | None = "Thu, 01 Jan 2026 10:00:00 +0000",
    html: bool = False,
    attachment: bool = False,
    inline: bool = False,
    reply_to_id: str | None = None,
    conflicting_auth: bool = False,
) -> bytes:
    mail = EmailMessage(policy=SMTP)
    mail["From"] = "Synthetic Sender <sender@example.invalid>"
    mail["To"] = "receiver@example.invalid"
    mail["Subject"] = "Synthetic café 例"
    if rfc_id is not None:
        mail["Message-ID"] = rfc_id
    if date is not None:
        # Construct invalid dates explicitly too; SMTP policy may normalize valid ones.
        mail._headers.append(("Date", date))
    if reply_to_id is not None:
        mail["In-Reply-To"] = reply_to_id
        mail["References"] = reply_to_id
    if conflicting_auth:
        mail["Authentication-Results"] = "untrusted.invalid; dkim=pass"
        mail["Authentication-Results"] = "synthetic.invalid; dkim=fail"
    mail.set_content("Synthetic body only.\n")
    if html or inline:
        mail.add_alternative("<p>Synthetic HTML only.</p>", subtype="html")
    if inline:
        mail.get_payload()[-1].add_related(
            b"synthetic image bytes",
            maintype="image",
            subtype="png",
            cid="<synthetic-image>",
            filename="synthetic-inline.png",
        )
    if attachment:
        mail.add_attachment(
            b"synthetic attachment bytes",
            maintype="application",
            subtype="octet-stream",
            filename="synthetic-file.bin",
        )
    for index, part in enumerate(mail.walk()):
        if part.is_multipart():
            part.set_boundary("facet-synthetic-boundary-" + str(index))
    return mail.as_bytes()
