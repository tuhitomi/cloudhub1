import hashlib,io,sys,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from publish_hosting_config import content,publish,restore_content

class ConfigPublishTests(unittest.TestCase):
    def setUp(self):
        self.c=dict(ACCOUNT_ID='123456789012',PRIMARY_REGION='ap-southeast-1',SHARED_STACK_REGION='ap-southeast-1',COGNITO_REGION='ap-southeast-1',
            ROOT_DOMAIN='example.com',FRONTEND_DOMAIN='example.com',API_DOMAIN='api.example.com',DNS_PROVIDER='external',
            IPV6_ENABLED=True,API_STAGE='$default',API_MAPPING_KEY='',TRANSITION_ORIGINS=[])
        self.i={'frontend':{'bucket':'private','distribution_id':'EDGE','distribution_domain':'demo.cloudfront.net'},'api':{'endpoint':'https://abc123.execute-api.ap-southeast-1.amazonaws.com'},
            'cognito':{'region':'ap-southeast-1','client_id':'abc123','hosted_domain':'https://demo.auth.ap-southeast-1.amazoncognito.com'}}
        self.session=Mock();self.sts=Mock();self.s3=Mock();self.cf=Mock()
        self.session.client.side_effect=lambda name,**kw:{'sts':self.sts,'s3':self.s3,'cloudfront':self.cf}[name]
        self.sts.get_caller_identity.return_value={'Account':'123456789012'}
        self.s3.get_public_access_block.return_value={'PublicAccessBlockConfiguration':{k:True for k in ('BlockPublicAcls','IgnorePublicAcls','BlockPublicPolicy','RestrictPublicBuckets')}}
        self.cf.get_distribution.return_value={'Distribution':{'DomainName':'demo.cloudfront.net','DistributionConfig':{'Origins':{'Items':[{'DomainName':'private.s3.ap-southeast-1.amazonaws.com','OriginAccessControlId':'OAC'}]}}}}
        self.cf.create_invalidation.return_value={'Invalidation':{'Id':'INV','Status':'InProgress'}}

    def test_changed_config_is_conditionally_written_and_only_config_invalidated(self):
        old=b'old';new=content(self.c,self.i)
        self.s3.get_object.side_effect=[{'Body':io.BytesIO(old),'ETag':'"before"'},{'Body':io.BytesIO(new)}]
        r=publish(self.session,self.c,self.i,hashlib.sha256(old).hexdigest())
        self.assertTrue(r['changed']);self.assertEqual(self.s3.put_object.call_args.kwargs['IfMatch'],'"before"')
        self.assertEqual(self.s3.put_object.call_args.kwargs['Key'],'config.js')
        self.assertEqual(self.cf.create_invalidation.call_args.kwargs['InvalidationBatch']['Paths'],{'Quantity':1,'Items':['/config.js']})

    def test_retry_after_write_uses_same_invalidation_identity_without_rewriting(self):
        new=content(self.c,self.i)
        self.s3.get_object.side_effect=lambda **kw:{'Body':io.BytesIO(new),'ETag':'"after"'}
        for _ in range(2):self.assertFalse(publish(self.session,self.c,self.i,'reviewed-before')['changed'])
        self.s3.put_object.assert_not_called()
        calls=self.cf.create_invalidation.call_args_list
        self.assertEqual(calls[0],calls[1])

    def test_other_members_config_change_is_not_overwritten(self):
        self.s3.get_object.return_value={'Body':io.BytesIO(b'changed by teammate'),'ETag':'"new"'}
        with self.assertRaises(ValueError):publish(self.session,self.c,self.i,'reviewed-before')
        self.s3.put_object.assert_not_called();self.cf.create_invalidation.assert_not_called()

    def test_rollback_allows_original_endpoint_without_changing_identity(self):
        import json
        v={'configured':True,'apiBase':self.i['api']['endpoint'],'clientId':'abc123','region':'ap-southeast-1',
            'cognitoDomain':self.i['cognito']['hosted_domain'],'redirectUri':'https://demo.cloudfront.net/'}
        body=lambda v:('window.CLOUDHUB = Object.freeze('+json.dumps(v)+');\n').encode()
        self.assertEqual(restore_content(body(v),self.c,self.i),body(v))
        for changed in ({**v,'apiBase':'https://foreign.execute-api.ap-southeast-1.amazonaws.com'},
                        {**v,'clientId':'foreign'},{**v,'secret':'forbidden'}):
            with self.assertRaises(ValueError):restore_content(body(changed),self.c,self.i)
        with self.assertRaises(ValueError):restore_content(body(v)+b'evil();',self.c,self.i)
