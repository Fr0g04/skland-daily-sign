"""Gate: 判定「今天是否已经成功签到过」，并把判定结果显式交出去。

三个触发源（GitHub cron、云端定时任务、手动）都先过这道门：
今天已成功就跳过，重复触发因此是安全的。

相对上一版的关键改动：
- already 无论 force 与否都会计算一次并输出。force 只改变「要不要签到」，
  不改变「今天是否已有成功」这个事实，而邮件去重要用后者。
- 「今天有没有成功过」从此只查一次（本文件），邮件步骤直接复用这里的裁决，
  不再各自实现一份查询——两份实现悄悄不一致是上一版最难查的地方。
- 判定结果写进 GITHUB_OUTPUT（run / already），同时写进 Step Summary，
  运行页面上一眼可见，不需要下载日志。
"""

import json
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CHINA = timezone(timedelta(hours=8))
TRUE = "true"
FALSE = "false"
UNKNOWN = "unknown"


def already_done(runs, current_id, now):
    """今天（UTC+8）是否已有一次成功运行（排除自己）。"""
    today = now.astimezone(CHINA).date()
    for run in runs:
        if str(run.get("id")) == str(current_id):
            continue
        if run.get("conclusion") != "success":
            continue
        created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        if created.astimezone(CHINA).date() == today and created <= now:
            return True
    return False


def fetch_today_success_runs(now):
    midnight = datetime.combine(now.astimezone(CHINA).date(), datetime.min.time(), CHINA)
    query = {
        "status": "success",
        "per_page": 100,
        "branch": os.environ["GITHUB_REF_NAME"],
        "created": ">=" + midnight.astimezone(timezone.utc).isoformat(),
    }
    runs = []
    for page in range(1, 11):
        query["page"] = page
        url = (
            "https://api.github.com/repos/"
            + os.environ["GITHUB_REPOSITORY"]
            + "/actions/workflows/daily.yml/runs?"
            + urlencode(query)
        )
        req = Request(
            url,
            headers={
                "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                "Accept": "application/vnd.github+json",
                "User-Agent": "skland-gate",
            },
        )
        with urlopen(req, timeout=20) as response:
            batch = json.load(response)["workflow_runs"]
        runs.extend(batch)
        if len(batch) < 100:
            break
    return runs


def decide(already, force):
    """是否需要执行签到。

    already=unknown（查询失败）时 fail-open：宁可重复签到，也不漏签。
    force 只影响签到，不影响 already 的事实判定（邮件去重要用后者）。
    """
    if force:
        return True
    return already != TRUE


def write_output(name, value):
    """写 GITHUB_OUTPUT；本地运行没有该变量时只打印。"""
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        print("（本地运行，无 GITHUB_OUTPUT）%s=%s" % (name, value))
        return
    with open(path, "a", encoding="utf-8") as output:
        output.write("%s=%s\n" % (name, value))


def write_summary(lines):
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as summary:
            summary.write("\n".join(lines) + "\n")
    except Exception as exc:  # 摘要写失败不影响主流程
        print("写入 Step Summary 失败（%s）。" % exc)


def main():
    now = datetime.now(timezone.utc)
    force = str(os.getenv("FORCE_RUN", "")).strip().lower() == "true"
    checked = ""
    already = UNKNOWN

    try:
        runs = fetch_today_success_runs(now)
        already = TRUE if already_done(runs, os.environ.get("GITHUB_RUN_ID", ""), now) else FALSE
        checked = "今日成功记录 %d 条" % len(runs)
    except Exception as exc:
        checked = "查询失败：%s" % exc
        print("无法查询当天运行结果（%s），already=unknown，按未签到处理以免漏签。" % exc)

    if force:
        print("force=true，忽略当天是否已成功。")
    execute = decide(already, force)

    print("GATE run=%s already=%s 依据=%s" % (str(execute).lower(), already, checked or "-"))
    print("继续执行签到。" if execute else "今天已签到成功，本次跳过。")

    write_output("run", str(execute).lower())
    write_output("already", already)
    write_summary(
        [
            "### 门禁判定",
            "",
            "| 项 | 值 |",
            "| --- | --- |",
            "| 今天是否已有成功运行 | `%s` |" % already,
            "| 本次是否执行签到 | `%s` |" % str(execute).lower(),
            "| force | `%s` |" % str(force).lower(),
            "| 依据 | %s |" % (checked or "-"),
        ]
    )


if __name__ == "__main__":
    main()
