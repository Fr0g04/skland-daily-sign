import os
import smtplib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import notify

CHINA = timezone(timedelta(hours=8))
TODAY = datetime.now(CHINA).date().isoformat()
YESTERDAY = (datetime.now(CHINA).date() - timedelta(days=1)).isoformat()


class MailTests(unittest.TestCase):
    def setUp(self):
        self.env = {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465",
                    "SMTP_USER": "sender@example.com", "SMTP_PASSWORD": "secret-password",
                    "MAIL_TO": "receiver@example.com", "SIGN_OUTCOME": "success",
                    "ALREADY_TODAY": "false"}
        # 状态文件必须是临时文件：否则单测会往仓库里写 .state/last-receipt.txt，
        # 导致当天的真实回执被误判为"已发过"而永久静音。
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "last-receipt.txt"
        self._original_state = notify.STATE_FILE
        notify.STATE_FILE = self.state

    def tearDown(self):
        notify.STATE_FILE = self._original_state
        self.tmp.cleanup()

    def test_receipt_tls_and_redaction(self):
        with patch.dict(os.environ, {**self.env, "SKLAND_TOKENS": "sensitive-token"}, clear=True), patch("notify.Path") as path, patch("notify.smtplib.SMTP_SSL") as connect:
            path.return_value.exists.return_value = True
            path.return_value.read_text.return_value = "签到成功 secret-password sensitive-token"
            self.assertEqual(notify.send_receipt(), 0)
        smtp = connect.return_value.__enter__.return_value
        message = smtp.send_message.call_args.args[0]
        self.assertNotIn("secret-password", message.get_content())
        self.assertNotIn("sensitive-token", message.get_content())
        self.assertIn("签到成功", message["Subject"])
        smtp.login.assert_called_once_with("sender@example.com", "secret-password")
        # 成功回执必须落状态，供后续触发据此去重。
        self.assertEqual(self.state.read_text(encoding="utf-8").strip(), TODAY)

    def test_failure_receipt_and_starttls(self):
        with patch.dict(os.environ, {**self.env, "SMTP_PORT": "587", "SIGN_OUTCOME": "failure"}, clear=True), patch("notify.smtplib.SMTP") as connect:
            self.assertEqual(notify.send_receipt(), 0)
        smtp = connect.return_value.__enter__.return_value
        smtp.starttls.assert_called_once()
        message = smtp.send_message.call_args.args[0]
        self.assertIn("执行失败", message["Subject"])

    def test_delivery_failure_fails_workflow(self):
        with patch.dict(os.environ, self.env, clear=True), patch("notify.smtplib.SMTP_SSL", side_effect=smtplib.SMTPException("private response")):
            self.assertEqual(notify.send_receipt(), 1)

    def test_partial_configuration_fails(self):
        with patch.dict(os.environ, {"SMTP_HOST": "example.com"}, clear=True):
            self.assertEqual(notify.send_receipt(), 1)

    def test_unconfigured_skips(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(notify.send_receipt(), 0)


class DedupTests(unittest.TestCase):
    """每天只发一封成功回执；失败告警不受去重影响。"""

    def setUp(self):
        self.env = {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465",
                    "SMTP_USER": "sender@example.com", "SMTP_PASSWORD": "secret-password",
                    "MAIL_TO": "receiver@example.com", "SIGN_OUTCOME": "success",
                    "ALREADY_TODAY": "false"}
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "last-receipt.txt"
        self._original_state = notify.STATE_FILE
        notify.STATE_FILE = self.state

    def tearDown(self):
        notify.STATE_FILE = self._original_state
        self.tmp.cleanup()

    def send(self, extra=None):
        with patch.dict(os.environ, {**self.env, **(extra or {})}, clear=True), \
                patch("notify.Path") as path, patch("notify.smtplib.SMTP_SSL") as connect:
            path.return_value.exists.return_value = False
            code = notify.send_receipt()
        return code, connect

    def test_skip_when_gate_reports_already(self):
        code, connect = self.send({"ALREADY_TODAY": "true"})
        self.assertEqual(code, 0)
        connect.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_skip_when_state_file_is_today(self):
        # 门禁不可靠（比如查询失败 fail-open）时，状态文件仍然挡住第二封。
        self.state.write_text(TODAY + "\n", encoding="utf-8")
        code, connect = self.send({"ALREADY_TODAY": "unknown"})
        self.assertEqual(code, 0)
        connect.assert_not_called()

    def test_send_when_state_file_is_yesterday(self):
        self.state.write_text(YESTERDAY + "\n", encoding="utf-8")
        code, connect = self.send({"ALREADY_TODAY": "false"})
        self.assertEqual(code, 0)
        connect.return_value.__enter__.return_value.send_message.assert_called_once()
        self.assertEqual(self.state.read_text(encoding="utf-8").strip(), TODAY)

    def test_second_run_same_day_skips(self):
        # 同一天第二次成功运行：第一次已写状态，第二次必须不再发。
        self.send({"ALREADY_TODAY": "false"})
        code, connect = self.send({"ALREADY_TODAY": "false"})
        self.assertEqual(code, 0)
        connect.assert_not_called()

    def test_failure_alert_ignores_dedup(self):
        self.state.write_text(TODAY + "\n", encoding="utf-8")
        code, connect = self.send({"SIGN_OUTCOME": "failure", "ALREADY_TODAY": "true"})
        self.assertEqual(code, 0)
        connect.return_value.__enter__.return_value.send_message.assert_called_once()


class DeploySafetyTests(unittest.TestCase):
    """升级过程中旧版测试文件不会污染仓库的 .state。"""

    def test_dedup_disabled_without_workflow_verdict(self):
        env = {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465",
               "SMTP_USER": "sender@example.com", "SMTP_PASSWORD": "secret-password",
               "MAIL_TO": "receiver@example.com", "SIGN_OUTCOME": "success"}
        tmp = tempfile.TemporaryDirectory()
        state = Path(tmp.name) / "last-receipt.txt"
        original = notify.STATE_FILE
        notify.STATE_FILE = state
        try:
            with patch.dict(os.environ, env, clear=True), patch("notify.Path") as path, patch("notify.smtplib.SMTP_SSL") as connect:
                path.return_value.exists.return_value = False
                self.assertEqual(notify.send_receipt(), 0)
            connect.return_value.__enter__.return_value.send_message.assert_called_once()
            # 没有 ALREADY_TODAY 时不得写状态文件，否则旧测试会把当天回执静音。
            self.assertFalse(state.exists())
        finally:
            notify.STATE_FILE = original
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
