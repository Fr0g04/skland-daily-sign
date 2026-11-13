"""Send attendance receipts over authenticated TLS SMTP.

去重规则：**每天只发一封成功回执**；失败告警一律发送。

判定不再由本文件去查 Actions API（那会形成第二份实现，与门禁悄悄不一致），
而是看两件事，任一成立就跳过：

1. 门禁给出的裁决 ALREADY_TODAY=true —— 今天已有成功运行；
2. 状态文件 .state/last-receipt.txt 记录的就是今天 —— 上一封已经发过了。

第 2 条不依赖网络、不依赖权限，由本脚本写入、由心跳步骤提交进仓库，
所以即使门禁查询失败（fail-open 放行），也不会发出第二封。
无法判定时不拦截：宁可多发一封，也不要漏掉告警。
"""

import os
import re
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

CHINA = timezone(timedelta(hours=8))

# 可用 NOTIFY_STATE_FILE 覆盖；单元测试指向临时文件，避免污染仓库。
STATE_FILE = Path(os.getenv("NOTIFY_STATE_FILE", ".state/last-receipt.txt"))


def write_output(name, value):
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as output:
            output.write("%s=%s\n" % (name, value))
    except Exception:
        pass


def read_state():
    try:
        return STATE_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def mark_sent(stamp):
    """记录「今天已发过回执」。心跳步骤会把这个文件提交进仓库。"""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(stamp + "\n", encoding="utf-8")
    except Exception as exc:
        print("无法写入回执状态文件（%s），下次可能重复发信。" % exc)


def dedup_enabled():
    """去重是否启用。

    只有 workflow 显式注入 ALREADY_TODAY 时才启用。这样即使升级过程中
    旧版测试文件还没换掉（它不会设这个变量），离线测试也不会在仓库里
    写出 .state/last-receipt.txt 而把当天回执静音。
    """
    return os.getenv("ALREADY_TODAY") is not None


def skip_reason(now):
    """非空字符串表示今天已经发过成功回执，应当跳过本次发送。"""
    if not dedup_enabled():
        return ""
    verdict = os.getenv("ALREADY_TODAY", "").strip().lower()
    if verdict == "true":
        return "gate:今天已有成功运行"
    today = now.astimezone(CHINA).date().isoformat()
    state = read_state()
    if state:
        first = state.split()[0]
        if first == today:
            return "state:回执状态文件=%s" % first
    return ""


def send_receipt():
    names = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_TO")
    values = {name: os.getenv(name, "").strip() for name in names}
    if not any(values.values()):
        print("邮件未配置：请添加 SMTP_HOST、SMTP_USER、SMTP_PASSWORD、MAIL_TO Secrets。")
        return 0
    if not all(values.values()):
        print("邮件配置不完整：请检查四项必填 Secrets。")
        return 1

    now = datetime.now(timezone.utc)
    success = os.getenv("SIGN_OUTCOME") == "success"
    # 只有成功回执做去重；失败告警一律发送。
    if success:
        reason = skip_reason(now)
        if reason:
            print("DEDUP=skipped reason=%s" % reason)
            write_output("mail", "skipped")
            return 0

    try:
        port = int(os.getenv("SMTP_PORT", "").strip() or "465")
        if port not in (465, 587):
            raise ValueError("仅支持 465 TLS 或 587 STARTTLS")
        recipients = [x.strip() for x in values["MAIL_TO"].split(",") if x.strip()]
        if not recipients:
            raise ValueError("收件人为空")
        status = "签到成功／今日已签到" if success else "执行失败或未完成，请检查"
        stamp = now.astimezone(CHINA).strftime("%Y-%m-%d %H:%M:%S")
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
        message["Subject"] = f"【森空岛】{status} · {stamp[:10]}"
        message["From"] = values["SMTP_USER"]
        message["To"] = ", ".join(recipients)
        message.set_content(f"北京时间：{stamp}\n结果：{status}\n\n{report}\n\n运行详情：{link}\n")
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
        if success:
            if dedup_enabled():
                mark_sent(now.astimezone(CHINA).date().isoformat())
                print("DEDUP=sent 已记录今日回执状态")
            else:
                print("DEDUP=sent 未启用去重（无 ALREADY_TODAY）")
            write_output("mail", "sent")
        else:
            print("DEDUP=sent 失败告警不参与去重")
            write_output("mail", "alert")
        return 0
    except Exception:
        # SMTP 异常可能含账号、收件人或服务器响应，不直接打印。
        print("邮件发送失败：请检查 SMTP 地址、端口、授权码及邮箱的 SMTP 开关。")
        return 1


if __name__ == "__main__":
    sys.exit(send_receipt())
