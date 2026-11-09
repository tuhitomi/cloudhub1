"""The release checker must stay offline even with real credentials in the shell."""
import os
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_product_release import offline_environment


class OfflineValidationTests(unittest.TestCase):
    def test_real_shell_profile_and_session_are_hidden_then_restored(self):
        with patch.dict(os.environ,{'AWS_PROFILE':'production-fixture','AWS_SESSION_TOKEN':'not-a-real-token'}):
            with offline_environment() as (attempts,loopback):
                self.assertNotIn('AWS_PROFILE',os.environ)
                self.assertNotIn('AWS_SESSION_TOKEN',os.environ)
                self.assertEqual(os.environ['AWS_ACCESS_KEY_ID'],'local-test-only')
                self.assertFalse(Path(os.environ['AWS_SHARED_CREDENTIALS_FILE']).exists())
                self.assertEqual(attempts,[])
            self.assertEqual(os.environ['AWS_PROFILE'],'production-fixture')
            self.assertEqual(os.environ['AWS_SESSION_TOKEN'],'not-a-real-token')

    def test_dns_connect_and_connect_ex_cannot_reach_external_hosts(self):
        with offline_environment() as (attempts,loopback):
            with self.assertRaisesRegex(AssertionError,'prohibited'):
                socket.getaddrinfo('unapproved.example.invalid',443)
            with socket.socket() as connection:
                with self.assertRaisesRegex(AssertionError,'prohibited'):
                    connection.connect(('192.0.2.1',443))
                with self.assertRaisesRegex(AssertionError,'prohibited'):
                    connection.connect_ex(('192.0.2.1',443))
            self.assertEqual(len(attempts),3)
            self.assertEqual(loopback,[])

    def test_unstubbed_sdk_call_is_rejected_before_http_transport(self):
        import boto3
        with offline_environment() as (attempts,loopback):
            client=boto3.client('sts',region_name='us-east-1',aws_access_key_id='local',aws_secret_access_key='local')
            with self.assertRaisesRegex(AssertionError,'prohibited'):
                client.get_caller_identity()
            self.assertEqual(len(attempts),1)


if __name__=='__main__':unittest.main()
