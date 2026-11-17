"""Непрочитанная почта по IMAP (только чтение)."""
import email
import re
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


def first_sentences(text: str, n: int = 2, limit: int = 300) -> str:
    """Первые n предложений письма без цитат, ссылок и подписей — грубая выжимка, а не пересказ смысла."""
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.lstrip().startswith((">", "--", "On ", "Sent from"))]
    flat = re.sub(r"https?://\S+", "", " ".join(lines))
    flat = re.sub(r"\s+", " ", flat).strip()
    sentences = re.split(r"(?<=[.!?])\s+", flat)
    return " ".join(sentences[:n])[:limit].strip()


def _body_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    return (msg.get_payload(decode=True) or b"").decode(msg.get_content_charset() or "utf-8", "replace")


def important(cfg, imap_factory=None, limit: int = 20) -> str:
    """Самое важное из непрочитанного: сначала письма важных отправителей (JARVIS_MAIL_VIP), затем новейшее.

    Читает без пометки «прочитано». Без ИИ: отправитель, тема и первые предложения.
    """
    if not (cfg.mail_user and cfg.mail_password):
        return "Почта не настроена: задайте JARVIS_MAIL_USER и JARVIS_MAIL_PASSWORD."
    factory = imap_factory or (lambda: imaplib.IMAP4_SSL(cfg.imap_host))
    m = factory()
    try:
        m.login(cfg.mail_user, cfg.mail_password)
        m.select("INBOX", readonly=True)
        _, data = m.search(None, "UNSEEN")
        ids = data[0].split()[-limit:][::-1]          # новейшие первыми
        if not ids:
            return "Непрочитанных писем нет."
        heads = []
        for i in ids:
            _, d = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
            h = email.message_from_bytes(d[0][1])
            heads.append((i, _dh(h["From"]), _dh(h["Subject"])))
        vip = [v.lower() for v in cfg.mail_vip]
        is_vip = lambda sender: any(v in sender.lower() for v in vip)
        heads.sort(key=lambda x: not is_vip(x[1]))     # sort стабилен: порядок «новейшие первыми» сохраняется
        i, sender, subject = heads[0]
        _, d = m.fetch(i, "(BODY.PEEK[])")
        body = first_sentences(_body_text(email.message_from_bytes(d[0][1])))
        name = sender.split("<")[0].strip().strip('"') or sender
        parts = [f"{'Важное письмо' if is_vip(sender) else 'Письмо'} от {name}.", f"Тема: {subject}."]
        parts.append(body if body else "Текста в письме нет.")
        if len(ids) > 1:
            parts.append(f"Ещё непрочитанных: {len(ids) - 1}.")
        return " ".join(parts)
    except (imaplib.IMAP4.error, OSError) as e:
        return f"Не удалось прочитать почту: {e}"
    finally:
        try:
            m.logout()
        except Exception:
            pass
