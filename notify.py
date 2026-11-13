"""Send attendance receipts over authenticated TLS SMTP.

改动：新增"当天首次成功才发回执"的判断。
签到本身是幂等的，重复执行无害；但重复执行会产生重复邮件，所以在这里做去重。
判断放在发信之前而不是 workflow 的 if 里，是为了让"只发一封"不依赖门禁是否可靠：
即使门禁因为查询失败而 fail-open 放行了第二次执行，这里仍然只会发一封。
失败告警不受影响，一律发送。
"""

import json
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CHINA = timezone(timedelta(hours=8))


def is_first_success_today():
    """今天（UTC+8）本次是否为第一个成功运行。

    返回 True 表示应当发送。查询不到时返回 True（fail-open）：
    宁可偶尔多发一封，也不要漏掉告警。
    """
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    run_id = os.getenv("GITHUB_RUN_ID", "").strip()
    branch = os.getenv("GITHUB_REF_NAME", "").strip()
    # 本地运行（含单元测试）直接放行，不做网络请求，保证测试是封闭的。
    if os.getenv("GITHUB_ACTIONS") != "true":
        return True
    if not (token and repo and run_id):
        return True  # 缺少上下文，不拦截

    now = datetime.now(timezone.utc)
    midnight = datetime.combine(now.astimezone(CHINA).date(), datetime.min.time(), CHINA)
    query = {
        "status": "success",
        "per_page": 100,
        "created": ">=" + midnight.astimezone(timezone.utc).isoformat(),
    }
    if branch:
        query["branch"] = branch

    try:
        for page in range(1, 6):
            query["page"] = page
            url = (
                "https://api.github.com/repos/"
                + repo
                + "/actions/workflows/daily.yml/runs?"
                + urlencode(query)
            )
            req = Request(
                url,
                headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "skland-notify",
                },
            )
            with urlopen(req, timeout=20) as response:
                batch = json.load(response)["workflow_runs"]
            for run in batch:
                if str(run.get("id")) == run_id:
                    continue
                if run.get("conclusion") != "success":
                    continue
                created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
                if created.astimezone(CHINA).date() == now.astimezone(CHINA).date():
                    return False
            if len(batch) < 100:
                break
    except Exception as exc:
        print("无法查询当天运行记录（%s），按首次成功处理。" % exc)
        return True
    return True


def send_receipt():
    names = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_TO")
    values = {name: os.getenv(name, "").strip() for name in names}
    if not any(values.values()):
        print("邮件未配置：请添加 SMTP_HOST、SMTP_USER、SMTP_PASSWORD、MAIL_TO Secrets。")
        return 0
    if not all(values.values()):
        print("邮件配置不完整：请检查四项必填 Secrets。")
        return 1

    success = os.getenv("SIGN_OUTCOME") == "success"
    # 只有"成功回执"需要去重；失败告警一律发送。
    if success and not is_first_success_today():
        print("今天已有更早的成功运行，本次不再重复发送回执。")
        return 0

    try:
        port = int(os.getenv("SMTP_PORT", "").strip() or "465")
        if port not in (465, 587):
            raise ValueError("仅支持 465 TLS 或 587 STARTTLS")
        recipients = [x.strip() for x in values["MAIL_TO"].split(",") if x.strip()]
        if not recipients:
            raise ValueError("收件人为空")
        status = "签到成功／今日已签到" if success else "执行失败或未完成，请检查"
        now = datetime.now(CHINA).strftime("%Y-%m-%d %H:%M:%S")
        report_path = Path("sign-result.txt")
        report = report_path.read_text(encoding="utf-8")[:16000] if report_path.exists() else "没有签到结果，可能在准备或测试步骤失败。"
        # 不允许把已知凭据放进回执。
        sensitive = [values["SMTP_PASSWORD"], values["SMTP_USER"],
                     os.getenv("SKLAND_DID", "")]
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
