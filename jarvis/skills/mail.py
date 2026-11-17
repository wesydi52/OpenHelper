"""Непрочитанная почта по IMAP (только чтение)."""
import email
import imaplib
from email.header import decode_header, make_header


def _dh(v) -> str:
    return str(make_header(decode_header(v or "")))


def unread(cfg, limit: int = 5) -> str:
    if not (cfg.mail_user and cfg.mail_password):
        return "Почта не настроена: задайте JARVIS_MAIL_USER и JARVIS_MAIL_PASSWORD."
    m = imaplib.IMAP4_SSL(cfg.imap_host)
    try:
        m.login(cfg.mail_user, cfg.mail_password)
        m.select("INBOX", readonly=True)
        _, data = m.search(None, "UNSEEN")
        ids = data[0].split()
        if not ids:
            return "Непрочитанных писем нет."
        lines = []
        for i in ids[-limit:][::-1]:
            _, d = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
            h = email.message_from_bytes(d[0][1])
            sender = _dh(h["From"]).split("<")[0].strip().strip('"')
            lines.append(f"от {sender}: {_dh(h['Subject'])}")
        return f"Непрочитанных писем: {len(ids)}. " + "; ".join(lines) + "."
    except (imaplib.IMAP4.error, OSError) as e:
        return f"Не удалось проверить почту: {e}"
    finally:
        try:
            m.logout()
        except Exception:
            pass
