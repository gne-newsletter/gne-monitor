"""Email notifier for scheduler events."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        self._email_cfg = cfg["notifications"]["email"]
        self._sched_cfg = cfg["scheduler"]
        self._notify_on = self._sched_cfg["notify_on"]
        self._enabled = self._email_cfg["enabled"]
        self._password: Optional[str] = None

    def set_password(self, password: str):
        """Set SMTP password (App Password for Gmail)."""
        self._password = password

    def _send(self, subject: str, body_text: str, body_html: Optional[str] = None,
              attachment: Optional[Path] = None):
        if not self._enabled:
            logger.debug("Email disabled — skipping: %s", subject)
            return
        if not self._password:
            logger.warning("SMTP 비밀번호 미설정 — 이메일 전송 생략: %s", subject)
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[GNE모니터] {subject}"
        msg["From"] = self._email_cfg["from"]
        msg["To"] = ", ".join(self._email_cfg["recipients"])

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        if attachment and attachment.exists():
            with open(attachment, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{attachment.name}"')
            msg.attach(part)

        try:
            with smtplib.SMTP(self._email_cfg["smtp_host"], self._email_cfg["smtp_port"]) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self._email_cfg["from"], self._password)
                smtp.sendmail(
                    self._email_cfg["from"],
                    self._email_cfg["recipients"],
                    msg.as_bytes(),
                )
            logger.info("이메일 전송 완료: %s", subject)
        except Exception as e:
            logger.error("이메일 전송 실패: %s — %s", subject, e)

    # ------------------------------------------------------------------
    # Notification types
    # ------------------------------------------------------------------

    def notify_new_findings(self, pubmed_new: int, ct_new: int,
                            pubmed_details: list[dict], ct_details: list[dict]):
        if not self._notify_on.get("new_pubmed_articles") and not self._notify_on.get("new_ct_trials"):
            return
        if pubmed_new == 0 and ct_new == 0:
            return

        lines = ["GNE 근병증 모니터링 시스템 — 신규 데이터 알림\n"]
        if pubmed_new:
            lines.append(f"■ 신규 PubMed 논문: {pubmed_new}건")
            for p in pubmed_details[:5]:
                authors = ", ".join(p.get("authors", [])[:2])
                lines.append(f"  • [{p.get('pub_date','')}] {p.get('title','')[:70]}")
                lines.append(f"    {authors}  |  {p.get('journal','')}")
                if p.get("doi"):
                    lines.append(f"    https://doi.org/{p['doi']}")
            if pubmed_new > 5:
                lines.append(f"  ... 외 {pubmed_new - 5}건")

        if ct_new:
            lines.append(f"\n■ 신규 임상시험: {ct_new}건")
            for t in ct_details[:5]:
                phases = "/".join(t.get("phases", [])) or "N/A"
                lines.append(f"  • {t.get('nct_id','')} [{t.get('overall_status','')}] Phase {phases}")
                lines.append(f"    {t.get('brief_title','')[:70]}")
                lines.append(f"    https://clinicaltrials.gov/study/{t.get('nct_id','')}")

        body_text = "\n".join(lines)
        html_items_pm = "".join(
            f"<li><b>{p.get('pub_date','')}</b> {p.get('title','')[:70]}<br>"
            f"<small>{', '.join(p.get('authors',[])[:2])} | {p.get('journal','')}</small></li>"
            for p in pubmed_details[:5]
        )
        html_items_ct = "".join(
            f"<li><b>{t.get('nct_id','')}</b> {t.get('brief_title','')[:70]}<br>"
            f"<small>{t.get('lead_sponsor','')} | Phase {'/ '.join(t.get('phases',[]))}</small></li>"
            for t in ct_details[:5]
        )
        body_html = f"""
        <html><body style="font-family:sans-serif;color:#1e293b">
        <h2 style="color:#1e40af">GNE 근병증 — 신규 데이터 알림</h2>
        {"<h3>📄 신규 논문 " + str(pubmed_new) + "건</h3><ul>" + html_items_pm + "</ul>" if pubmed_new else ""}
        {"<h3>🧪 신규 임상시험 " + str(ct_new) + "건</h3><ul>" + html_items_ct + "</ul>" if ct_new else ""}
        <hr><small>GNE 모니터링 시스템 자동 발송</small>
        </body></html>"""

        subject = f"신규 {'논문 ' + str(pubmed_new) + '건' if pubmed_new else ''}" \
                  f"{'  임상시험 ' + str(ct_new) + '건' if ct_new else ''} 발견"
        self._send(subject.strip(), body_text, body_html)

    def notify_monthly_report(self, report_html: Optional[Path] = None):
        if not self._notify_on.get("monthly_report"):
            return
        from datetime import date
        month = date.today().strftime("%Y년 %m월")
        body = f"{month} GNE 근병증 연구 동향 월간 리포트가 첨부되어 있습니다."
        self._send(f"{month} 월간 리포트", body, attachment=report_html)

    def notify_job_failure(self, job_name: str, error: str):
        if not self._notify_on.get("job_failure"):
            return
        body = f"스케줄 잡 실패\n\n잡: {job_name}\n오류: {error}"
        self._send(f"[오류] {job_name} 실패", body)
