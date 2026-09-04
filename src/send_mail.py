"""Gmail SMTP로 리포트 이메일을 발송한다.

발신: 개인 Gmail 계정 (2단계 인증 + 앱 비밀번호)
수신: RECIPIENT_EMAIL 환경변수. 쉼표(,) 또는 세미콜론(;)으로 구분해서
     여러 명을 적으면 전원에게 동시 발송된다 (예: "a@x.com, b@y.com").
     수신처를 바꿀 때는 코드 수정 없이 이 secret 값만 갱신하면 된다.
"""
from __future__ import annotations

import os
import re
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_RECIPIENT_SEP = re.compile(r"[;,]")


def _parse_recipients(raw: str) -> list[str]:
    """쉼표/세미콜론으로 구분된 수신자 목록을 파싱한다. 앞뒤 공백은 제거한다."""
    return [addr.strip() for addr in _RECIPIENT_SEP.split(raw) if addr.strip()]


def send_report(
    subject: str, html_body: str, attachment_bytes: bytes, attachment_name: str
) -> None:
    # GitHub secrets/로컬 .env에 복사 과정에서 앞뒤 공백/줄바꿈이 섞여 들어오는 경우가
    # 있어서(예: RFC 5321 invalid address 오류), 방어적으로 strip 한다.
    sender = os.environ["GMAIL_ADDRESS"].strip()
    app_password = os.environ["GMAIL_APP_PASSWORD"].strip()
    recipients = _parse_recipients(os.environ["RECIPIENT_EMAIL"])

    if not recipients:
        raise RuntimeError("RECIPIENT_EMAIL에서 유효한 수신자를 찾지 못했습니다.")

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    part = MIMEApplication(attachment_bytes, Name=attachment_name)
    part["Content-Disposition"] = f'attachment; filename="{attachment_name}"'
    msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, app_password)
        server.sendmail(sender, recipients, msg.as_string())
