"""国服森空岛每日签到，Python 3.11+，仅使用标准库。"""
import hashlib
import hmac
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://zonai.skland.com"
UA = "Skland/1.5.1 (com.hypergryph.skland; Android 34)"


class ApiError(Exception):
    pass


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def request(url, method="POST", body=None, headers=None):
    payload = None if body is None else body.encode("utf-8")
    req = Request(url, data=payload, method=method, headers={
        "User-Agent": UA, "Content-Type": "application/json", **(headers or {})})
    try:
        with urlopen(req, timeout=30) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise ApiError(f"HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ApiError("网络连接失败或超时") from None
    except (ValueError, UnicodeError):
        raise ApiError("服务返回非 JSON 数据") from None
    if not isinstance(result, dict):
        raise ApiError("服务返回格式异常")
    return result


def data_or_error(result, key="code"):
    if result.get(key) != 0:
        # 不输出原始响应，避免服务器回显凭据。
        raise ApiError(f"接口错误 {key}={result.get(key)}；请检查凭据、设备信息或接口变更")
    data = result.get("data")
    if not isinstance(data, dict):
        raise ApiError("接口缺少 data")
    return data


def signature(secret, path, body, game="arknights", did="", timestamp=None):
    ts = str(int(time.time()) if timestamp is None else timestamp)
    headers = {"platform": "3" if game == "endfield" else "1",
               "timestamp": ts, "dId": did,
               "vName": "1.0.0" if game == "endfield" else "1.5.1"}
    message = path + body + ts + encode(headers)
    digest = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return {**headers, "sign": hashlib.md5(digest.encode()).hexdigest()}


class Client:
    def __init__(self, token, did=""):
        self.did = did
        grant = data_or_error(request("https://as.hypergryph.com/user/oauth2/v2/grant",
            body=encode({"appCode": "4ca99fa6b56cc2ba", "token": token, "type": 0})), "status")
        auth_headers = {"platform": "3", "timestamp": str(int(time.time())),
                        "vName": "1.0.0", "dId": did}
        # 原生 API 与网页 API 使用不同设备校验。提供真实 dId 时走网页端。
        prefix = "/web/v1" if did else "/api/v1"
        auth = data_or_error(request(BASE + prefix + "/user/auth/generate_cred_by_code",
            body=encode({"code": grant["code"], "kind": 1}), headers=auth_headers))
        self.cred, self.secret = auth["cred"], auth["token"]
        if os.getenv("GITHUB_ACTIONS") == "true":
            for value in (self.cred, self.secret):
                print("::add-mask::" + value)

    def call(self, path, body=None, game="arknights", role=None):
        wire = "" if body is None else encode(body)
        headers = {"cred": self.cred, **signature(self.secret, path, wire, game, self.did)}
        if role:
            headers["sk-game-role"] = role
        return request(BASE + path, "GET" if path.endswith("/binding") else "POST",
                       None if path.endswith("/binding") else wire, headers)


def roles_from(games):
    seen = set()
    for game in games:
        kind = game.get("appCode")
        if kind not in ("arknights", "endfield"):
            continue
        for binding in game.get("bindingList") or []:
            if kind == "arknights":
                uid, gid = binding.get("uid"), binding.get("channelMasterId")
                if uid is None or gid is None:
                    raise ApiError("明日方舟绑定数据缺少 uid/channelMasterId")
                items = [(str(uid), str(gid))]
            else:
                roles = binding.get("roles") or [binding.get("defaultRole")]
                items = []
                for role in roles:
                    if not role or role.get("roleId") is None or role.get("serverId") is None:
                        raise ApiError("终末地绑定数据缺少 roleId/serverId")
                    items.append((str(role["roleId"]), str(role["serverId"])))
            for a, b in items:
                key = (kind, a, b)
                if key not in seen:
                    seen.add(key)
                    yield key


def attendance_ok(result):
    if result.get("code") == 0:
        return "签到成功"
    message = str(result.get("message", ""))
    if any(text in message for text in ("请勿重复签到", "今日已签到", "今天已签到", "已经签到")) or "please do not sign in again" in message.lower():
        return "今日已签到"
    # 10001 同时可能表示设备等其他错误，不能仅凭错误码当作成功。
    raise ApiError(f"签到失败，code={result.get('code')}；请检查凭据、设备信息或接口变更")


def main():
    tokens = [x.strip() for x in re.split(r"[\n,;]+", os.getenv("SKLAND_TOKENS", "")) if x.strip()]
    if not tokens:
        print("失败：请设置仓库 Secret SKLAND_TOKENS（鹰角通行证 Token）")
        return 1
    failed = False
    for i, token in enumerate(tokens, 1):
        try:
            client = Client(token, os.getenv("SKLAND_DID", "").strip())
            games = data_or_error(client.call("/api/v1/game/player/binding"))["list"]
            roles = list(roles_from(games))
            if not roles:
                raise ApiError("没有找到两个游戏的绑定角色，请先在森空岛绑定")
            for j, (kind, a, b) in enumerate(roles, 1):
                label = f"账号 {i} / {kind} / 角色 {j}"
                try:
                    if kind == "endfield":
                        result = client.call("/api/v1/game/endfield/attendance", game=kind, role=f"3_{a}_{b}")
                    else:
                        result = client.call("/api/v1/game/attendance", {"uid": a, "gameId": b})
                    print(f"{label}：{attendance_ok(result)}")
                except (ApiError, KeyError, TypeError):
                    print(f"{label}：签到失败，请检查接口或凭据")
                    failed = True
                time.sleep(2)
        except (ApiError, KeyError, TypeError) as exc:
            print(f"账号 {i}：{exc if isinstance(exc, ApiError) else '接口数据格式异常'}")
            failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
