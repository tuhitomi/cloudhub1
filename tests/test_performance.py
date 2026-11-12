"""LOCAL only: catalog cache, gzip responses and latency-related infrastructure."""
import base64, gzip, json, os, sys, unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
from test_regions import setup
from cloudhub import api


def get(path, query=None, encoding=None):
    event = {'rawPath': path, 'requestContext': {'http': {'method': 'GET'}}}
    if query: event['queryStringParameters'] = query
    if encoding: event['headers'] = {'Accept-Encoding': encoding}
    return api.handler(event)


def body(response):
    raw = response['body']
    if response.get('isBase64Encoded'):
        raw = gzip.decompress(base64.b64decode(raw)).decode('utf-8')
    return json.loads(raw)


class CatalogCacheTests(unittest.TestCase):
    def setUp(self):
        api.PUBLIC_CACHE.clear()
        self.addCleanup(api.PUBLIC_CACHE.clear)

    def test_second_request_is_served_from_warm_cache_without_recomputing(self):
        with patch.object(api, 'SERVICE', setup()), patch('cloudhub.public_catalog.read', wraps=__import__('cloudhub.public_catalog', fromlist=['read']).read) as reader:
            first, second = get('/public/catalog'), get('/public/catalog')
        self.assertEqual(reader.call_count, 1)
        self.assertEqual((first['headers']['x-cloudhub-cache'], second['headers']['x-cloudhub-cache']), ('MISS', 'HIT'))
        self.assertEqual(body(first), body(second))
        self.assertEqual(first['headers']['cache-control'], 'public, max-age=60')

    def test_cache_expires_and_previews_are_keyed_by_query(self):
        with patch.object(api, 'SERVICE', setup()):
            api.public_catalog_response(None, now=1000.0)
            api.public_catalog_response({'template_id': 'T07', 'region': 'ap-northeast-1', 'profile_id': 'standard'}, now=1000.0)
            self.assertEqual(len(api.PUBLIC_CACHE), 2)
            self.assertEqual(api.public_catalog_response(None, now=1059.0)['headers']['x-cloudhub-cache'], 'HIT')
            self.assertEqual(api.public_catalog_response(None, now=1061.0)['headers']['x-cloudhub-cache'], 'MISS')

    def test_errors_are_not_cached_and_keep_no_store(self):
        with patch.object(api, 'SERVICE', setup()):
            response = get('/public/catalog', {'template_id': 'T10', 'region': 'ap-southeast-1', 'profile_id': 'standard'})
        self.assertEqual(response['statusCode'], 400)
        self.assertEqual(response['headers']['cache-control'], 'no-store')
        self.assertEqual(api.PUBLIC_CACHE, {})

    def test_cache_can_be_disabled(self):
        with patch.object(api, 'SERVICE', setup()), patch.dict(os.environ, {'PUBLIC_CATALOG_CACHE_SECONDS': '0'}):
            response = get('/public/catalog')
        self.assertEqual(response['headers']['cache-control'], 'no-store')
        self.assertEqual(api.PUBLIC_CACHE, {})


class CompressionTests(unittest.TestCase):
    def setUp(self):
        api.PUBLIC_CACHE.clear()

    def test_large_json_is_gzipped_only_when_accepted(self):
        with patch.object(api, 'SERVICE', setup()):
            plain = get('/public/catalog')
            packed = get('/public/catalog', encoding='br, gzip;q=0.8')
        self.assertNotIn('isBase64Encoded', plain)
        self.assertTrue(packed['isBase64Encoded'])
        self.assertEqual(packed['headers']['content-encoding'], 'gzip')
        self.assertIn('Accept-Encoding', packed['headers']['vary'])
        self.assertEqual(body(packed), json.loads(plain['body']))
        self.assertLess(len(base64.b64decode(packed['body'])), len(plain['body'].encode()) / 4)

    def test_small_or_protected_responses_are_untouched(self):
        with patch.object(api, 'SERVICE', setup()):
            result = get('/environments', encoding='gzip')
        self.assertEqual(result['statusCode'], 401)
        self.assertNotIn('content-encoding', result['headers'])
        self.assertEqual(result['headers']['cache-control'], 'no-store')

    def test_non_json_and_already_encoded_bodies_are_left_alone(self):
        event = {'headers': {'accept-encoding': 'gzip'}}
        binary = {'statusCode': 200, 'isBase64Encoded': True, 'body': 'AAAA', 'headers': {'content-type': 'application/json'}}
        html = {'statusCode': 200, 'body': 'x' * 5000, 'headers': {'content-type': 'text/html'}}
        self.assertIs(api.compress(event, binary), binary)
        self.assertIs(api.compress(event, html), html)


class EntryPointTests(unittest.TestCase):
    def test_entry_imports_sdk_without_clients_and_delegates(self):
        from cloudhub import api_entry
        self.assertIs(api_entry.handler, api.handler)
        source = (ROOT / 'backend/cloudhub/api_entry.py').read_text(encoding='utf-8')
        self.assertNotIn('client(', source)
        self.assertNotIn('resource(', source)


class InfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from generate_infra import build_template
        cls.template = build_template()
        cls.r = cls.template['Resources']

    def test_api_function_uses_entry_alias_and_optional_snapstart(self):
        api_fn = self.r['ApiFunction']['Properties']
        self.assertEqual(api_fn['Handler'], 'cloudhub.api_entry.handler')
        self.assertEqual(api_fn['AutoPublishAlias'], 'live')
        self.assertEqual(self.template['Parameters']['ApiSnapStart']['Default'], 'Disabled')
        self.assertEqual(api_fn['SnapStart'], {'ApplyOn': {'Fn::If': ['ApiSnapStartEnabled', 'PublishedVersions', 'None']}})
        self.assertEqual(api_fn['Environment']['Variables']['PUBLIC_CATALOG_CACHE_SECONDS'], '60')

    def test_http_api_throttling_is_bounded_and_public_route_is_stricter(self):
        http = self.r['HttpApi']['Properties']
        default, public = http['DefaultRouteSettings'], http['RouteSettings']['GET /public/catalog']
        self.assertLess(public['ThrottlingRateLimit'], default['ThrottlingRateLimit'])
        self.assertLessEqual(default['ThrottlingRateLimit'], default['ThrottlingBurstLimit'])

    def test_latency_alarms_follow_two_second_target(self):
        for name, namespace in [('ApiLatencyP95Alarm', 'AWS/ApiGateway'), ('ApiFunctionDurationP95Alarm', 'AWS/Lambda')]:
            props = self.r[name]['Properties']
            self.assertEqual((props['Namespace'], props['ExtendedStatistic'], props['Threshold']), (namespace, 'p95', 2000))
            self.assertEqual(props['AlarmActions'], [{'Ref': 'AlertTopic'}])
        widgets = json.loads(self.r['OperationsDashboard']['Properties']['DashboardBody']['Fn::Sub'])['widgets']
        self.assertTrue(any(w['properties']['title'] == 'API Lambda duration and concurrency' for w in widgets))

    def test_source_distribution_is_unchanged_so_edge_import_has_no_drift(self):
        config = self.r['FrontendDistribution']['Properties']['DistributionConfig']
        self.assertEqual(config['PriceClass'], 'PriceClass_100')
        self.assertNotIn('FrontendEdgeCachePolicy', self.r)

    def test_edge_policy_caches_briefly_with_compression_and_no_personal_keys(self):
        from performance_infra import edge_cache_policy
        cfg = edge_cache_policy('x')['Properties']['CachePolicyConfig']
        keys = cfg['ParametersInCacheKeyAndForwardedToOrigin']
        self.assertEqual((cfg['MinTTL'], cfg['DefaultTTL'], cfg['MaxTTL']), (60, 60, 300))
        self.assertTrue(keys['EnableAcceptEncodingGzip'] and keys['EnableAcceptEncodingBrotli'])
        self.assertEqual(keys['CookiesConfig'], {'CookieBehavior': 'none'})


if __name__ == '__main__':
    unittest.main()
