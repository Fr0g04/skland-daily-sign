"""Send attendance receipts over authenticated TLS SMTP."""
import os
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path


def send_receipt():
    names = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_TO")
    values = {name: os.getenv(name, "").strip() for name in names}
    if not any(values.values()):
        print("邮件未配置：请添加 SMTP_HOST、SMTP_USER、SMTP_PASSWORD、MAIL_TO Secrets。")
        return 0
    if not all(values.values()):
        print("邮件配置不完整：请检查四项必填 Secrets。")
        return 1
    try:
        port = int(os.getenv("SMTP_PORT", "").strip() or "465")
        if port not in (465, 587):
            raise ValueError("仅支持 465 TLS 或 587 STARTTLS")
        recipients = [x.strip() for x in values["MAIL_TO"].split(",") if x.strip()]
        if not recipients:
            raise ValueError("收件人为空")
        success = os.getenv("SIGN_OUTCOME") == "success"
        status = "签到成功／今日已签到" if success else "执行失败或未完成，请检查"
        now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        report_path = Path("sign-result.txt")
        report = report_path.read_text(encoding="utf-8")[:16000] if report_path.exists() else "没有签到结果，可能在准备或测试步骤失败。"
        # 不允许把已知凭据放进回执。
        sensitive = [values["SMTP_PASSWORD"], values["SMTP_USER"],
                     os.getenv("SKLAND_DID", "")]
        import re
        sensitive.extend(re.split(r"[\n,;]+", os.getenv("SKLAND_TOKENS", "")))
        for value in sensitive:
            if value:
                report = report.replace(value, "[已隐藏]")
        repo = os.getenv("GITHUB_REPOSITORY", "")
        run_id = os.getenv("GITHUB_RUN_ID", "")
        link = f"https://github.com/{repo}/actions/runs/{run_id}" if repo and run_id else "本地运行"
        message = EmailMessage()
        message["Subject"] = f"【森空岛】{status} · {now[:10]}"
        message["From"] = values["SMTP_USER"]
        message["To"] = ", ".join(recipients)
        message.set_content(f"北京时间：{now}\n结果：{status}\n\n{report}\n\n运行详情：{link}\n")
        context = ssl.create_default_context()
        if port == 465:
            connection = smtplib.SMTP_SSL(values["SMTP_HOST"], port, timeout=30, context=context)
        else:
            connection = smtplib.SMTP(values["SMTP_HOST"], port, timeout=30)
        with connection as smtp:
            if port == 587:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(values["SMTP_USER"], values["SMTP_PASSWORD"])
            smtp.send_message(message, to_addrs=recipients)
        print("邮件回执已提交到 SMTP 服务器。")
        return 0
    except Exception:
        # SMTP 异常可能含账号、收件人或服务器响应，不直接打印。
        print("邮件发送失败：请检查 SMTP 地址、端口、授权码及邮箱的 SMTP 开关。")
        return 1


if __name__ == "__main__":
    sys.exit(send_receipt())
