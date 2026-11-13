"""Gate: 当天已有成功运行则跳过。

让 GitHub cron、云端定时任务、手动触发这三个来源互相幂等：
任何一个先把今天的签到跑成功，其余触发都会自动跳过，不会重复签到。

与原版差异：
- 原版只在 event=schedule 且 schedule=RETRY_CRON 时才去重，而且只认 event=schedule 的成功记录。
  现在无论哪种触发，都检查"今天是否已有成功运行"，多触发源从此安全叠加。
- 手动触发可通过 force 输入强制运行，方便调试。
- 查询失败时 fail-open（继续签到），宁可重复也不漏签。
"""

import json
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CHINA = timezone(timedelta(hours=8))


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


def main():
    now = datetime.now(timezone.utc)
    force = str(os.getenv("FORCE_RUN", "")).strip().lower() == "true"

    if force:
        execute = True
        print("force=true，忽略当天是否已成功。")
    else:
        execute = True
        try:
            execute = not already_done(fetch_today_success_runs(now), os.environ["GITHUB_RUN_ID"], now)
        except Exception as exc:
            print("无法查询当天运行结果（%s），继续签到以免漏签。" % exc)

    print("继续执行签到。" if execute else "今天已签到成功，本次跳过。")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("run=" + str(execute).lower() + "\n")


if __name__ == "__main__":
    main()
