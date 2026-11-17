"""Почта через IMAP/SMTP (для Gmail — пароль приложения)."""
import email
import imaplib
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage

from .registry import S


def _dh(v) -> str:
    return str(make_header(decode_header(v or "")))


def _body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", "replace")


def register(reg, cfg, store):
    def need_cfg():
        if not (cfg.mail_user and cfg.mail_password):
            return "Почта не настроена: задайте JARVIS_MAIL_USER и JARVIS_MAIL_PASSWORD."

    def connect():
        m = imaplib.IMAP4_SSL(cfg.imap_host)
        m.login(cfg.mail_user, cfg.mail_password)
        m.select("INBOX", readonly=True)
        return m

    @reg.add("list_unread_mail", "Список непрочитанных писем (отправитель, тема).",
             {"limit": S("Сколько показать", "integer")})
    def list_unread(limit: int = 5):
        if err := need_cfg():
            return err
        m = connect()
        try:
            _, data = m.search(None, "UNSEEN")
            ids = data[0].split()[-limit:][::-1]
            out = []
            for i in ids:
                _, d = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                h = email.message_from_bytes(d[0][1])
                out.append(f"[{i.decode()}] {_dh(h['From'])} — {_dh(h['Subject'])} ({h['Date']})")
            return "\n".join(out) or "Непрочитанных писем нет."
        finally:
            m.logout()

    @reg.add("read_mail", "Прочитать письмо по id из списка.", {"id": S("id письма")}, ["id"])
    def read_mail(id: str):
        if err := need_cfg():
            return err
        m = connect()
        try:
            _, d = m.fetch(id.encode(), "(BODY.PEEK[])")
            msg = email.message_from_bytes(d[0][1])
            return f"От: {_dh(msg['From'])}\nТема: {_dh(msg['Subject'])}\n\n{_body(msg)[:3000]}"
        finally:
            m.logout()

    @reg.add("send_mail", "Отправить письмо. Требует подтверждения пользователя.",
             {"to": S("Адрес получателя"), "subject": S("Тема"), "body": S("Текст")},
             ["to", "subject", "body"], confirm=True)
    def send_mail(to: str, subject: str, body: str):
        if err := need_cfg():
            return err
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = cfg.mail_user, to, subject
        msg.set_content(body)
        with smtplib.SMTP_SSL(cfg.smtp_host, 465) as s:
            s.login(cfg.mail_user, cfg.mail_password)
            s.send_message(msg)
        return f"Письмо отправлено на {to}."
