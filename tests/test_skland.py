import hashlib
import hmac
import json
import unittest
from unittest.mock import patch

import skland


class AttendanceTests(unittest.TestCase):
    def test_token_formats(self):
        self.assertEqual(skland.load_tokens('{"code":0,"data":{"content":"sample"}}'), ["sample"])
        self.assertEqual(skland.load_tokens('one\ntwo;three'), ["one", "two", "three"])
        self.assertEqual(skland.load_tokens('["one","two"]'), ["one", "two"])
        with self.assertRaises(skland.ApiError):
            skland.load_tokens('{"wrong":"format"}')

    def test_signature_wire_contract(self):
        body = '{"uid":"123","gameId":"1"}'
        headers = skland.signature("test-key", "/api/v1/game/attendance", body, timestamp=1700000000)
        signed = '/api/v1/game/attendance' + body + '1700000000' + '{"platform":"1","timestamp":"1700000000","dId":"","vName":"1.5.1"}'
        expected = hashlib.md5(hmac.new(b"test-key", signed.encode(), hashlib.sha256).hexdigest().encode()).hexdigest()
        self.assertEqual(headers["sign"], expected)

    def test_endfield_empty_body_and_role_header(self):
        client = skland.Client.__new__(skland.Client)
        client.cred, client.secret, client.did = "cred", "key", ""
        with patch("skland.request", return_value={"code": 0}) as send:
            client.call("/api/v1/game/endfield/attendance", game="endfield", role="3_12_0")
        args = send.call_args.args
        self.assertEqual(args[1:3], ("POST", ""))
        self.assertEqual(args[3]["sk-game-role"], "3_12_0")
        self.assertEqual(args[3]["platform"], "3")

    def test_all_roles_deduplicate_and_zero_server(self):
        role = {"roleId": "12", "serverId": 0}
        games = [{"appCode": "endfield", "bindingList": [{"roles": [role, role]}, {"defaultRole": role}]},
                 {"appCode": "arknights", "bindingList": [{"uid": "99", "channelMasterId": 1}]}]
        self.assertEqual(list(skland.roles_from(games)), [("endfield", "12", "0"), ("arknights", "99", "1")])

    def test_error_10001_is_not_success(self):
        with self.assertRaises(skland.ApiError):
            skland.attendance_ok({"code": 10001, "message": "设备信息无效"})
        self.assertEqual(skland.attendance_ok({"code": 10001, "message": "请勿重复签到"}), "今日已签到")

    def test_missing_secret_fails(self):
        with patch.dict("os.environ", {"SKLAND_TOKENS": ""}):
            self.assertEqual(skland.main(), 1)

    def test_failure_does_not_skip_other_game(self):
        fake = unittest.mock.Mock()
        fake.call.side_effect = [
            {"code": 0, "data": {"list": [
                {"appCode": "arknights", "bindingList": [{"uid": "1", "channelMasterId": 1}]},
                {"appCode": "endfield", "bindingList": [{"roles": [{"roleId": "2", "serverId": "3"}]}]}]}},
            {"code": 10001, "message": "设备信息无效"}, {"code": 0}]
        with patch.dict("os.environ", {"SKLAND_TOKENS": "dummy"}), patch("skland.Client", return_value=fake), patch("skland.time.sleep"):
            self.assertEqual(skland.main(), 1)
        self.assertEqual(fake.call.call_count, 3)


if __name__ == "__main__":
    unittest.main()
