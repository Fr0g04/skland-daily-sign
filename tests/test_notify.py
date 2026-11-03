import os
import smtplib
import unittest
from pathlib import Path
from unittest.mock import patch

import notify


class MailTests(unittest.TestCase):
    def setUp(self):
        self.env = {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465",
                    "SMTP_USER": "sender@example.com", "SMTP_PASSWORD": "secret-password",
                    "MAIL_TO": "receiver@example.com", "SIGN_OUTCOME": "success"}

    def test_receipt_tls_and_redaction(self):
        with patch.dict(os.environ, {**self.env, "SKLAND_TOKENS": "sensitive-token"}), patch("notify.Path") as path, patch("notify.smtplib.SMTP_SSL") as connect:
            path.return_value.exists.return_value = True
            path.return_value.read_text.return_value = "签到成功 secret-password sensitive-token"
            self.assertEqual(notify.send_receipt(), 0)
        smtp = connect.return_value.__enter__.return_value
        message = smtp.send_message.call_args.args[0]
        self.assertNotIn("secret-password", message.get_content())
        self.assertNotIn("sensitive-token", message.get_content())
        self.assertIn("签到成功", message["Subject"])
        smtp.login.assert_called_once_with("sender@example.com", "secret-password")

    def test_failure_receipt_and_starttls(self):
        with patch.dict(os.environ, {**self.env, "SMTP_PORT": "587", "SIGN_OUTCOME": "failure"}), patch("notify.smtplib.SMTP") as connect:
            self.assertEqual(notify.send_receipt(), 0)
        smtp = connect.return_value.__enter__.return_value
        smtp.starttls.assert_called_once()
        message = smtp.send_message.call_args.args[0]
        self.assertIn("执行失败", message["Subject"])

    def test_delivery_failure_fails_workflow(self):
        with patch.dict(os.environ, self.env), patch("notify.smtplib.SMTP_SSL", side_effect=smtplib.SMTPException("private response")):
            self.assertEqual(notify.send_receipt(), 1)

    def test_partial_configuration_fails(self):
        with patch.dict(os.environ, {"SMTP_HOST": "example.com"}, clear=True):
            self.assertEqual(notify.send_receipt(), 1)

    def test_unconfigured_skips(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(notify.send_receipt(), 0)
