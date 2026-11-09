import sys,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from hosting_upload_cors import merge_origins,apply

def config():
    return dict(ACCOUNT_ID='123456789012',PRIMARY_REGION='ap-southeast-1',SHARED_STACK_REGION='ap-southeast-1',COGNITO_REGION='ap-southeast-1',
        ROOT_DOMAIN='example.com',FRONTEND_DOMAIN='example.com',API_DOMAIN='api.example.com',DNS_PROVIDER='external',ROUTE53_HOSTED_ZONE_ID='',
        IPV6_ENABLED=True,API_STAGE='$default',API_MAPPING_KEY='',TRANSITION_ORIGINS=['https://old.cloudfront.net'])

class UploadCorsTests(unittest.TestCase):
    def test_origin_merge_preserves_other_rules_headers_and_methods(self):
        rules=[{'ID':'Post','AllowedOrigins':['https://old.cloudfront.net'],'AllowedMethods':['POST'],'AllowedHeaders':['content-type']},
            {'ID':'Other','AllowedOrigins':['https://tools.example.com'],'AllowedMethods':['GET']}]
        merged=merge_origins(rules,config())
        self.assertEqual(merged[0]['AllowedOrigins'],['https://old.cloudfront.net','https://example.com'])
        self.assertEqual(merged[1],rules[1]);self.assertEqual(rules[0]['AllowedOrigins'],['https://old.cloudfront.net'])
        self.assertEqual(merge_origins(merged,config()),merged)

    def test_replay_no_write_and_concurrent_change_rejected(self):
        before=[{'AllowedOrigins':['https://old.cloudfront.net'],'AllowedMethods':['POST']}]
        plan={'bucket':'shared','expected_owner':'123456789012','before':before,'rules':merge_origins(before,config())}
        session=Mock();sts=Mock();s3=Mock();session.client.side_effect=lambda name,**kw:{'sts':sts,'s3':s3}[name]
        sts.get_caller_identity.return_value={'Account':'123456789012'}
        s3.get_bucket_cors.return_value={'CORSRules':plan['rules']}
        self.assertEqual(apply(session,config(),plan)['status'],'NO_CHANGES');s3.put_bucket_cors.assert_not_called()
        s3.get_bucket_cors.return_value={'CORSRules':[]}
        with self.assertRaises(ValueError):apply(session,config(),plan)
        s3.put_bucket_cors.assert_not_called()

    def test_wildcard_and_wrong_owner_fail_without_mutations(self):
        with self.assertRaises(ValueError):merge_origins([{'AllowedOrigins':['*'],'AllowedMethods':['POST']}],config())
        session=Mock();session.client.return_value.get_caller_identity.return_value={'Account':'000000000000'}
        with self.assertRaises(ValueError):apply(session,config(),{'expected_owner':'123456789012'})
