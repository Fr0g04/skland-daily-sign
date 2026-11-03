"""Skip the 01:07 China-time retry after a successful scheduled run today."""
import json
import os
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CHINA = timezone(timedelta(hours=8))
RETRY_CRON = "7 17 * * *"


def should_run(event, schedule, runs, current_id, now):
    if event != "schedule" or schedule != RETRY_CRON:
        return True
    today = now.astimezone(CHINA).date()
    for run in runs:
        if str(run.get("id")) == str(current_id):
            continue
        if run.get("event") != "schedule" or run.get("conclusion") != "success":
            continue
        created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        if created.astimezone(CHINA).date() == today and created <= now:
            return False
    return True


def main():
    event = os.getenv("GITHUB_EVENT_NAME", "")
    schedule = os.getenv("SCHEDULE", "")
    execute = True
    if event == "schedule" and schedule == RETRY_CRON:
        now = datetime.now(timezone.utc)
        midnight = datetime.combine(now.astimezone(CHINA).date(), time.min, CHINA)
        query = {"event": "schedule", "status": "success", "per_page": 100,
                 "branch": os.environ["GITHUB_REF_NAME"],
                 "created": ">=" + midnight.astimezone(timezone.utc).isoformat()}
        try:
            runs = []
            for page in range(1, 11):
                query["page"] = page
                url = ("https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"]
                       + "/actions/workflows/daily.yml/runs?" + urlencode(query))
                req = Request(url, headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                    "Accept": "application/vnd.github+json", "User-Agent": "skland-retry-gate"})
                with urlopen(req, timeout=20) as response:
                    batch = json.load(response)["workflow_runs"]
                runs.extend(batch)
                if len(batch) < 100:
                    break
            execute = should_run(event, schedule, runs, os.environ["GITHUB_RUN_ID"], now)
        except Exception:
            print("无法查询首次运行结果，继续补签以免漏签。")
    print("继续执行签到。" if execute else "当天首次定时签到已成功，跳过凌晨一点补签。")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("run=" + str(execute).lower() + "\n")


if __name__ == "__main__":
    main()
