"""T09 embedded read API must distinguish continuous from expired/missing deadlines."""
import importlib.util
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

class DataContinuousTests(TestCase):
    def test_null_deadline_only_allows_explicit_continuous_and_preserves_owner(self):
        class Client:
            meta={'status':{'S':'READY'},'deadline':{'NULL':True},'operating_policy':{'M':{'mode':{'S':'CONTINUOUS'}}}}
            def get_item(self,**kw):return {'Item':{'enabled':{'BOOL':True}} if kw['Key']['pk']['S'].startswith('U#') else self.meta}
            def scan(self,**kw):return {'Items':[]}
        fake=Client();path=Path(__file__).resolve().parents[1]/'backend/cloudhub/data_api_app.py'
        spec=importlib.util.spec_from_file_location('read_api_local_test',path);module=importlib.util.module_from_spec(spec)
        with patch('boto3.client',return_value=fake),patch.dict(os.environ,{'OWNER':'alice','ENVIRONMENT':'env-local','DATA_TABLE':'data','MANAGEMENT':'metadata','AWS_REGION':'us-east-1'}):
            spec.loader.exec_module(module)
            event={'requestContext':{'authorizer':{'jwt':{'claims':{'sub':'alice','token_use':'access'}}}}}
            self.assertEqual(200,module.handler(event)['statusCode'])
            fake.meta={'status':{'S':'READY'}};self.assertEqual(409,module.handler(event)['statusCode'])
            fake.meta={'status':{'S':'READY'},'deadline':{'N':'1'}};self.assertEqual(409,module.handler(event)['statusCode'])
            event['requestContext']['authorizer']['jwt']['claims']['sub']='bob';self.assertEqual(404,module.handler(event)['statusCode'])
