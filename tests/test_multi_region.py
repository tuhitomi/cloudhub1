"""LOCAL only: edge API cache, multi-Region failover, user-experience monitoring and chaos templates."""
import copy, json, sys, types, unittest
from pathlib import Path
from unittest import mock
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import chaos_infra, dr_infra, experience_infra, performance_infra


def edge_template():
    behavior = lambda path, origin: {'PathPattern': path, 'TargetOriginId': origin, 'ViewerProtocolPolicy': 'redirect-to-https',
                                     'AllowedMethods': ['GET', 'HEAD'], 'CachedMethods': ['GET', 'HEAD']}
    return {'Parameters': {}, 'Resources': {
        'FrontendSecurityHeaders': {'Type': 'AWS::CloudFront::ResponseHeadersPolicy'},
        'FrontendDistribution': {'Type': 'AWS::CloudFront::Distribution', 'Properties': {'DistributionConfig': {
            'Origins': [{'Id': 'private-s3', 'DomainName': 'front.s3.ap-southeast-1.amazonaws.com',
                         'OriginAccessControlId': {'Ref': 'OriginAccess'}, 'S3OriginConfig': {'OriginAccessIdentity': ''}},
                        {'Id': 'ui-context-api', 'DomainName': 'abc.execute-api.ap-southeast-1.amazonaws.com'}],
            'DefaultCacheBehavior': {'TargetOriginId': 'private-s3', 'AllowedMethods': ['GET', 'HEAD']},
            'CacheBehaviors': [behavior('index.html', 'private-s3'), behavior('config.js', 'private-s3'),
                               behavior('/ui-context', 'ui-context-api')]}}}}}


def config(template):
    return template['Resources']['FrontendDistribution']['Properties']['DistributionConfig']


class EdgeApiCacheTests(unittest.TestCase):
    def test_public_catalog_is_cached_at_the_edge_by_query_string(self):
        t = edge_template()
        self.assertTrue(performance_infra.edge_api_cache(t['Resources']))
        policy = t['Resources']['PublicApiCachePolicy']['Properties']['CachePolicyConfig']
        self.assertEqual((policy['MinTTL'], policy['DefaultTTL'], policy['MaxTTL']), (60, 60, 300))
        key = policy['ParametersInCacheKeyAndForwardedToOrigin']
        self.assertEqual(key['QueryStringsConfig'], {'QueryStringBehavior': 'all'})
        self.assertEqual(key['HeadersConfig'], {'HeaderBehavior': 'none'})
        self.assertEqual(key['CookiesConfig'], {'CookieBehavior': 'none'})
        catalog = [b for b in config(t)['CacheBehaviors'] if b['PathPattern'] == '/public/catalog']
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]['TargetOriginId'], 'ui-context-api')
        self.assertEqual(catalog[0]['AllowedMethods'], ['GET', 'HEAD'])
        self.assertEqual(catalog[0]['ViewerProtocolPolicy'], 'https-only')
        self.assertEqual(catalog[0]['ResponseHeadersPolicyId'], {'Ref': 'FrontendSecurityHeaders'})

    def test_applying_twice_keeps_one_behavior(self):
        t = edge_template()
        performance_infra.edge_api_cache(t['Resources']); performance_infra.edge_api_cache(t['Resources'])
        self.assertEqual([b['PathPattern'] for b in config(t)['CacheBehaviors']].count('/public/catalog'), 1)

    def test_requires_the_api_origin_and_ignores_templates_without_distribution(self):
        t = edge_template(); config(t)['Origins'].pop()
        with self.assertRaises(ValueError):
            performance_infra.edge_api_cache(t['Resources'])
        self.assertFalse(performance_infra.edge_api_cache({}))


class FailoverTests(unittest.TestCase):
    def failover(self):
        t = edge_template(); performance_infra.edge_api_cache(t['Resources'])
        return dr_infra.attach_failover(t)

    def test_static_files_and_catalog_fail_over_to_the_recovery_bucket(self):
        t = self.failover(); c = config(t)
        dr = next(o for o in c['Origins'] if o['Id'] == 'dr-s3')
        self.assertEqual(dr['DomainName'], {'Ref': 'DrBucketDomain'})
        self.assertEqual(dr['OriginAccessControlId'], {'Ref': 'OriginAccess'})
        groups = {g['Id']: g for g in c['OriginGroups']['Items']}
        self.assertEqual(c['OriginGroups']['Quantity'], 2)
        self.assertEqual([m['OriginId'] for m in groups['frontend-failover']['Members']['Items']], ['private-s3', 'dr-s3'])
        self.assertEqual([m['OriginId'] for m in groups['catalog-failover']['Members']['Items']], ['ui-context-api', 'dr-s3'])
        self.assertEqual(groups['frontend-failover']['FailoverCriteria']['StatusCodes']['Items'], [403, 404, 500, 502, 503, 504])
        # A 4xx from the API (bad query, throttling) must reach the viewer, not the snapshot.
        self.assertEqual(groups['catalog-failover']['FailoverCriteria']['StatusCodes']['Items'], [500, 502, 503, 504])
        targets = {b.get('PathPattern', 'default'): b['TargetOriginId'] for b in [c['DefaultCacheBehavior']] + c['CacheBehaviors']}
        self.assertEqual(targets, {'default': 'frontend-failover', 'index.html': 'frontend-failover', 'config.js': 'frontend-failover',
                                   '/ui-context': 'ui-context-api', '/public/catalog': 'catalog-failover'})
        self.assertIn('ap-northeast-1', t['Parameters']['DrBucketDomain']['AllowedPattern'])

    def test_idempotent(self):
        t = self.failover(); again = dr_infra.attach_failover(copy.deepcopy(t))
        self.assertEqual(config(again)['Origins'], config(t)['Origins'])
        self.assertEqual(config(again)['OriginGroups'], config(t)['OriginGroups'])

    def test_refuses_write_methods_on_origin_groups(self):
        t = edge_template(); config(t)['DefaultCacheBehavior']['AllowedMethods'] = ['GET', 'HEAD', 'OPTIONS', 'PUT', 'POST', 'PATCH', 'DELETE']
        with self.assertRaises(ValueError):
            dr_infra.attach_failover(t)

    def test_without_catalog_behavior_only_the_frontend_group_exists(self):
        c = config(dr_infra.attach_failover(edge_template()))
        self.assertEqual([g['Id'] for g in c['OriginGroups']['Items']], ['frontend-failover'])

    def test_known_bucket_domain(self):
        self.assertEqual(dr_infra.bucket_domain('123456789012'),
                         'cloudhub-dr-frontend-123456789012-ap-northeast-1.s3.ap-northeast-1.amazonaws.com')


class TokyoStackTests(unittest.TestCase):
    def setUp(self):
        self.t = dr_infra.tokyo(); self.r = self.t['Resources']

    def test_only_deploys_in_the_recovery_region(self):
        assertion = self.t['Rules']['RecoveryRegion']['Assertions'][0]['Assert']
        self.assertEqual(assertion, {'Fn::Equals': [{'Ref': 'AWS::Region'}, 'ap-northeast-1']})

    def test_bucket_is_private_versioned_encrypted_and_retained(self):
        b = self.r['DrFrontendBucket']; p = b['Properties']
        self.assertEqual(b['DeletionPolicy'], 'Retain')
        self.assertEqual(p['VersioningConfiguration'], {'Status': 'Enabled'})
        self.assertTrue(all(p['PublicAccessBlockConfiguration'].values()))
        statements = self.r['DrFrontendBucketPolicy']['Properties']['PolicyDocument']['Statement']
        allow = next(s for s in statements if s['Effect'] == 'Allow')
        self.assertEqual(allow['Principal'], {'Service': 'cloudfront.amazonaws.com'})
        self.assertIn('AWS:SourceArn', allow['Condition']['StringEquals'])
        self.assertTrue(any(s['Effect'] == 'Deny' and s['Condition'] == {'Bool': {'aws:SecureTransport': 'false'}} for s in statements))

    def test_snapshot_function_may_only_write_its_key(self):
        statements = self.r['SnapshotRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        s3 = [s for s in statements if s['Action'] == 's3:PutObject']
        self.assertEqual(len(s3), 1)
        self.assertEqual(s3[0]['Resource'], {'Fn::Sub': '${DrFrontendBucket.Arn}/public/catalog'})
        self.assertEqual(self.r['SnapshotSchedule']['Properties']['ScheduleExpression'], 'rate(15 minutes)')

    def test_replication_role_reads_source_and_writes_only_the_recovery_bucket(self):
        statements = self.r['ReplicationRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        writes = next(s for s in statements if 's3:ReplicateObject' in s['Action'])
        self.assertEqual(writes['Resource'], {'Fn::Sub': '${DrFrontendBucket.Arn}/*'})

    def run_snapshot(self, body, status=200):
        puts = []
        boto3 = types.ModuleType('boto3'); boto3.client = lambda name: types.SimpleNamespace(put_object=lambda **kw: puts.append(kw))
        response = mock.MagicMock(status=status); response.read.return_value = json.dumps(body).encode()
        response.__enter__.return_value = response
        with mock.patch.dict(sys.modules, {'boto3': boto3}), \
             mock.patch.dict('os.environ', {'CATALOG_URL': 'https://api.example/public/catalog', 'BUCKET': 'dr', 'KEY': 'public/catalog'}), \
             mock.patch('urllib.request.urlopen', return_value=response):
            namespace = {}
            exec(dr_infra.SNAPSHOT_CODE, namespace)
            return namespace['handler']({}, None), puts

    def test_snapshot_stores_a_valid_catalog_with_its_time(self):
        result, puts = self.run_snapshot({'items': [{'template_id': 'a'}], 'signup_policy': {}})
        self.assertEqual(result['items'], 1)
        self.assertEqual(puts[0]['Key'], 'public/catalog')
        self.assertEqual(puts[0]['ContentType'], 'application/json')
        self.assertIn('snapshot-at', puts[0]['Metadata'])

    def test_snapshot_keeps_the_last_good_copy_on_unexpected_content(self):
        for body in ({'items': []}, {'message': 'Service Unavailable'}, {'items': [1]}):
            with self.assertRaises(ValueError):
                self.run_snapshot(body)

    def test_out_of_band_commands(self):
        commands = dr_infra.replica_commands('table', 'front', 'arn:aws:s3:::dr', 'arn:aws:iam::1:role/r')
        self.assertIn('StreamViewType=NEW_AND_OLD_IMAGES', commands[0])
        self.assertIn('"RegionName":"ap-northeast-1"', commands[1])
        self.assertIn('PointInTimeRecoveryEnabled=true', commands[2])
        rule = json.loads(commands[4].split("--replication-configuration '")[1].rstrip("'"))
        self.assertEqual(rule['Rules'][0]['Destination'], {'Bucket': 'arn:aws:s3:::dr'})
        self.assertIn('--exclude "public/catalog"', commands[5])


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.r = experience_infra.regional()['Resources']

    def test_canary_runs_the_journey_every_ten_minutes(self):
        p = self.r['JourneyCanary']['Properties']
        self.assertEqual(p['Schedule'], {'Expression': 'rate(10 minutes)'})
        self.assertEqual(p['RuntimeVersion'], 'syn-nodejs-puppeteer-9.1')
        self.assertLessEqual(len(p['Name']), 21)
        for step in ('open-home', 'templates-rendered', 'edge-catalog', 'ui-context'):
            self.assertIn(f"'{step}'", p['Code']['Script'])
        alarm = self.r['JourneyAlarm']['Properties']
        self.assertEqual((alarm['MetricName'], alarm['Threshold'], alarm['ComparisonOperator']), ('SuccessPercent', 90, 'LessThanThreshold'))

    def test_anonymous_browsers_may_only_send_rum_events(self):
        role = self.r['RumGuestRole']['Properties']
        trust = role['AssumeRolePolicyDocument']['Statement'][0]
        self.assertEqual(trust['Condition']['ForAnyValue:StringLike'], {'cognito-identity.amazonaws.com:amr': 'unauthenticated'})
        statements = role['Policies'][0]['PolicyDocument']['Statement']
        self.assertEqual([s['Action'] for s in statements], ['rum:PutRumEvents'])
        self.assertTrue(statements[0]['Resource']['Fn::Sub'].endswith(':appmonitor/cloudhub-web'))
        monitor = self.r['RumMonitor']['Properties']['AppMonitorConfiguration']
        self.assertFalse(monitor['AllowCookies'])

    def test_rum_config_output_matches_the_browser_loader(self):
        output = json.loads(experience_infra.regional()['Outputs']['RumConfig']['Value']['Fn::Sub'])
        loader = (ROOT / 'frontend/rum.js').read_text(encoding='utf-8')
        for key in ('appMonitorId', 'identityPoolId', 'guestRoleArn', 'region'):
            self.assertIn(key, output); self.assertIn(f"'{key}'", loader)


class ChaosTests(unittest.TestCase):
    def setUp(self):
        self.d = chaos_infra.experiment_definition(); self.s = self.d['States']

    def successors(self, name):
        state = self.s[name]
        nxt = [state[k] for k in ('Next', 'Default') if k in state]
        nxt += [c['Next'] for c in state.get('Choices', [])] + [c['Next'] for c in state.get('Catch', [])]
        return nxt

    def test_every_path_after_injection_removes_the_fault(self):
        # Walk the graph from InjectFault; no terminal state may be reached without RemoveFault.
        stack, seen = [('InjectFault', False)], set()
        while stack:
            name, removed = stack.pop()
            if (name, removed) in seen:
                continue
            seen.add((name, removed))
            removed = removed or name == 'RemoveFault'
            if self.s[name]['Type'] in ('Succeed', 'Fail'):
                self.assertTrue(removed, f'{name} reachable with the fault still injected')
            for nxt in self.successors(name):
                stack.append((nxt, removed))
        for name in ('InjectFault', 'CheckGuards'):
            self.assertEqual(self.s[name]['Catch'][0]['Next'], 'RemoveFault')

    def test_preconditions_bounds_and_rollback(self):
        bounds = self.s['ValidateInput']['Choices'][0]['And']
        self.assertIn({'Variable': '$.duration_seconds', 'NumericLessThanEquals': 600}, bounds)
        self.assertIn({'Variable': '$.duration_seconds', 'NumericGreaterThanEquals': 30}, bounds)
        self.assertGreater(self.d['TimeoutSeconds'], 600)
        self.assertEqual(self.s['InjectFault']['Parameters']['ReservedConcurrentExecutions'], 0)
        self.assertEqual(self.s['BaselineFree']['Choices'][0]['Next'], 'BaselineHasReserved')
        self.assertTrue(self.s['RemoveFault']['Retry'])
        self.assertEqual(self.s['VerifyRestored']['Next'], 'Restored')

    def test_safety_net_and_least_privilege(self):
        r = chaos_infra.regional()['Resources']
        pattern = r['SafetyNet']['Properties']['EventPattern']
        self.assertEqual(pattern['detail']['status'], ['ABORTED', 'TIMED_OUT'])
        statements = r['ExperimentRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        lam = next(s for s in statements if 'lambda:PutFunctionConcurrency' in s['Action'])
        self.assertIn(':function:${TargetFunction}', lam['Resource']['Fn::Sub'])
        restore = r['RestoreRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        self.assertEqual([s['Action'] for s in restore], ['lambda:DeleteFunctionConcurrency'])
        self.assertEqual(json.loads(r['Restore']['Properties']['DefinitionString'])['States']['RemoveFault']['Resource'],
                         'arn:aws:states:::aws-sdk:lambda:deleteFunctionConcurrency')


class GeneratedFilesTests(unittest.TestCase):
    def test_committed_templates_match_generators(self):
        for path, build in (('infra/dr/tokyo.json', dr_infra.tokyo), ('infra/experience/regional.json', experience_infra.regional),
                            ('infra/chaos/regional.json', chaos_infra.regional)):
            self.assertEqual(json.loads((ROOT / path).read_text(encoding='utf-8')), build(), path)


if __name__ == '__main__':
    unittest.main()
