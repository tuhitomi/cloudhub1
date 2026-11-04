import io,unittest,zipfile
from copy import deepcopy
from prepare_recommendations_release import prepare

class SelectiveReleaseTests(unittest.TestCase):
    def inputs(self):
        resources={n:{'Type':'AWS::Lambda::Function','Properties':{'Code':{'S3Bucket':'old','S3Key':'old'},'Environment':{'Variables':{'EXISTING_FLAG':'unchanged'}}}} for n in ['ApiFunction','WorkerFunction','SweepFunction','ExpiryFunction']}
        resources.update(HttpApi={'Properties':{'Body':{'paths':{'/templates':{'get':{'security':[{'JWT':['scope']}],'responses':{},'x-amazon-apigateway-integration':{'uri':'existing','payloadFormatVersion':'2.0'}}}}}}},HttpApiApiGatewayDefaultStage={'Properties':{'RouteSettings':{'GET /existing':{'ThrottlingRateLimit':5}}}},ApiFunctionRoute0Permission={'Type':'AWS::Lambda::Permission','Properties':{'SourceArn':{'Fn::Sub':['old',{'__ApiId__':'existing','__Stage__':'*'}]},'Principal':'apigateway.amazonaws.com','Action':'lambda:InvokeFunction','FunctionName':{'Ref':'ApiFunction'}}},KeepRole={'Type':'AWS::IAM::Role','Properties':{'Policies':['do-not-expand']}},KeepSchedule={'Type':'AWS::Scheduler::Schedule','Properties':{'ScheduleExpression':'rate(5 minutes)'}})
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('unrelated.txt',b'preserve bytes')
        return {'Parameters':{'OldParameter':{'Type':'String','Default':'keep'}},'Resources':resources},b.getvalue()
    def test_native_resources_and_zip_members_preserved_and_default_gate_closed(self):
        before,code=self.inputs();snapshot=deepcopy(before);template,blob,review=prepare(before,code,'existing-private-deploy',{})
        self.assertEqual(before,snapshot);self.assertEqual(template['Resources']['KeepRole'],before['Resources']['KeepRole']);self.assertEqual(template['Resources']['KeepSchedule'],before['Resources']['KeepSchedule'])
        self.assertEqual(template['Parameters']['RecommendationsEnabled']['Default'],'false');self.assertEqual(zipfile.ZipFile(io.BytesIO(blob)).read('unrelated.txt'),b'preserve bytes')
        self.assertEqual(review['new_iam_privileges'],[])
    def test_already_integrated_template_fails_safely_without_duplicate_resources(self):
        before,code=self.inputs();before['Parameters']['RecommendationsEnabled']={'Type':'String'}
        with self.assertRaises(ValueError):prepare(before,code,'private',{})
