"""Latency, edge delivery and API protection settings for the control plane.

Measured on 12/11/2026 from a client in Vietnam:
- cloudhub1.me was served by a US CloudFront edge (PriceClass_100 has no Asian
  edges): 280 ms TCP connect, ~1.2 s TTFB, every request revalidated with S3.
- /public/catalog returned 16 KB of uncompressed JSON (994 bytes gzipped),
  p95 2.25 s including Lambda cold starts.

The settings below keep every behaviour that tests rely on (no-store on
account data, CachingDisabled for config.js) and only change delivery.
"""
import json

# PriceClass_200 adds Asia, Middle East and Africa edges to PriceClass_100.
# Viewers in Vietnam/Singapore are then served from a nearby edge.
FRONTEND_PRICE_CLASS = 'PriceClass_200'
# Edge TTL for HTML and static assets. Objects keep their browser-facing
# Cache-Control (no-cache), so browsers revalidate against the nearby edge,
# and the edge only returns to S3 at most once per minute per object.
# A release can be made visible immediately with an invalidation of /*.
EDGE_MIN_TTL = 60
EDGE_DEFAULT_TTL = 60
EDGE_MAX_TTL = 300
# HTTP API stage throttling (account-wide token bucket per route).
DEFAULT_BURST, DEFAULT_RATE = 200, 100
PUBLIC_ROUTE_BURST, PUBLIC_ROUTE_RATE = 50, 25
API_P95_THRESHOLD_MS = 2000


def edge_cache_policy(name):
    return {'Type': 'AWS::CloudFront::CachePolicy', 'Properties': {'CachePolicyConfig': {
        'Name': name, 'Comment': 'CloudHub frontend: short edge TTL, gzip and brotli, no cookies/query/headers in key',
        'MinTTL': EDGE_MIN_TTL, 'DefaultTTL': EDGE_DEFAULT_TTL, 'MaxTTL': EDGE_MAX_TTL,
        'ParametersInCacheKeyAndForwardedToOrigin': {
            'EnableAcceptEncodingGzip': True, 'EnableAcceptEncodingBrotli': True,
            'CookiesConfig': {'CookieBehavior': 'none'}, 'HeadersConfig': {'HeaderBehavior': 'none'},
            'QueryStringsConfig': {'QueryStringBehavior': 'none'}}}}}


MANAGED_SECURITY_HEADERS = '67f7725c-6f97-4210-82d7-5512b31e9d03'  # AWS "SecurityHeadersPolicy"
# The frontend has no inline script/style/handlers and loads everything from
# its own origin; it only connects to the API, Cognito, S3 (signed upload and
# download URLs) and Session Manager WebSockets.
CSP_BASE = ["default-src 'self'", "script-src 'self'", "style-src 'self'", "img-src 'self' data:", "font-src 'self'",
            "object-src 'none'", "base-uri 'self'", "frame-ancestors 'self'", "form-action 'self' https://*.amazonaws.com"]
PERMISSIONS_POLICY = 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()'


def content_security_policy(api_origin=None, enforce=False):
    connect = ["'self'", 'https://*.amazonaws.com', 'https://*.amazoncognito.com', 'wss://*.amazonaws.com']
    if api_origin:
        connect.insert(1, api_origin.rstrip('/'))
    # Browsers ignore upgrade-insecure-requests in a Report-Only policy and log a warning.
    return '; '.join(CSP_BASE[:5] + ['connect-src ' + ' '.join(connect)] + CSP_BASE[5:] + (['upgrade-insecure-requests'] if enforce else []))


def security_headers_policy(name, api_origin=None, enforce_csp=False):
    """Replaces the managed SecurityHeadersPolicy: same protections plus CSP,
    Permissions-Policy, HSTS preload and Server-Timing. The CSP starts in
    Report-Only mode; switch enforce_csp once the browser console stays clean."""
    csp_header = 'Content-Security-Policy' if enforce_csp else 'Content-Security-Policy-Report-Only'
    return {'Type': 'AWS::CloudFront::ResponseHeadersPolicy', 'Properties': {'ResponseHeadersPolicyConfig': {
        'Name': name, 'Comment': 'CloudHub frontend security headers, CSP and Server-Timing',
        'SecurityHeadersConfig': {
            'StrictTransportSecurity': {'AccessControlMaxAgeSec': 63072000, 'IncludeSubdomains': True, 'Preload': True, 'Override': True},
            'ContentTypeOptions': {'Override': True},
            'FrameOptions': {'FrameOption': 'SAMEORIGIN', 'Override': True},
            'ReferrerPolicy': {'ReferrerPolicy': 'strict-origin-when-cross-origin', 'Override': True},
            'XSSProtection': {'Protection': True, 'ModeBlock': True, 'Override': True}},
        'CustomHeadersConfig': {'Items': [
            {'Header': csp_header, 'Value': content_security_policy(api_origin, enforce_csp), 'Override': True},
            {'Header': 'Permissions-Policy', 'Value': PERMISSIONS_POLICY, 'Override': True},
            {'Header': 'Cross-Origin-Opener-Policy', 'Value': 'same-origin', 'Override': True}]},
        'ServerTimingHeadersConfig': {'Enabled': True, 'SamplingRate': 100}}}}


def tune_distribution(resources, policy_name, api_origin=None, headers_name=None):
    """Apply the edge settings to FrontendDistribution if this template owns it."""
    dist = resources.get('FrontendDistribution')
    if not dist:
        return False
    config = dist['Properties']['DistributionConfig']
    resources['FrontendEdgeCachePolicy'] = edge_cache_policy(policy_name)
    resources['FrontendSecurityHeaders'] = security_headers_policy(headers_name or {'Fn::Sub': '${AWS::StackName}-frontend-headers'}, api_origin)
    config['PriceClass'] = FRONTEND_PRICE_CLASS
    # HTTP/3 (QUIC): faster connection setup on lossy mobile networks; HTTP/2 stays as fallback.
    config['HttpVersion'] = 'http2and3'
    config['DefaultCacheBehavior']['CachePolicyId'] = {'Ref': 'FrontendEdgeCachePolicy'}
    config['DefaultCacheBehavior']['Compress'] = True
    behaviors = [config['DefaultCacheBehavior']]
    for behavior in config.get('CacheBehaviors', []):
        body = behavior['Fn::If'][1] if 'Fn::If' in behavior else behavior
        behaviors.append(body)
        if body.get('PathPattern') == 'index.html':
            body['CachePolicyId'] = {'Ref': 'FrontendEdgeCachePolicy'}
            body['Compress'] = True
    for body in behaviors:
        if body.get('ResponseHeadersPolicyId') in (None, MANAGED_SECURITY_HEADERS):
            body['ResponseHeadersPolicyId'] = {'Ref': 'FrontendSecurityHeaders'}
    return True


PUBLIC_API_PATH = '/public/catalog'
PUBLIC_API_TTL = (60, 60, 300)


def public_api_cache_policy(name):
    """The catalog depends only on its query string (see cloudhub.api.public_catalog_response),
    so the edge may share one cached copy per query between all viewers."""
    low, default, high = PUBLIC_API_TTL
    return {'Type': 'AWS::CloudFront::CachePolicy', 'Properties': {'CachePolicyConfig': {
        'Name': name, 'Comment': 'CloudHub public catalog: 60 s shared edge cache keyed by query string',
        'MinTTL': low, 'DefaultTTL': default, 'MaxTTL': high,
        'ParametersInCacheKeyAndForwardedToOrigin': {
            'EnableAcceptEncodingGzip': True, 'EnableAcceptEncodingBrotli': True,
            'CookiesConfig': {'CookieBehavior': 'none'}, 'HeadersConfig': {'HeaderBehavior': 'none'},
            'QueryStringsConfig': {'QueryStringBehavior': 'all'}}}}}


def edge_api_cache(resources, origin_id='ui-context-api'):
    """Serve GET /public/catalog from the frontend distribution with a 60 s edge TTL.

    Load test (13/11/2026): the route throttle of 5 rps answered 813 of 1,279 catalog
    requests with 429 at 100 users. With the edge cache each POP asks the API about
    once a minute per distinct query, so viewers no longer reach the throttle.
    The API origin and its secret header are the ones /ui-context already uses."""
    dist = resources.get('FrontendDistribution')
    if not dist:
        return False
    config = dist['Properties']['DistributionConfig']
    origins = [o['Fn::If'][1] if 'Fn::If' in o else o for o in config['Origins']]
    if origin_id not in {o['Id'] for o in origins}:
        raise ValueError(f'Distribution has no {origin_id} origin')
    resources['PublicApiCachePolicy'] = public_api_cache_policy({'Fn::Sub': '${AWS::StackName}-public-api'})
    behavior = {'PathPattern': PUBLIC_API_PATH, 'TargetOriginId': origin_id, 'ViewerProtocolPolicy': 'https-only',
                'AllowedMethods': ['GET', 'HEAD'], 'CachedMethods': ['GET', 'HEAD'], 'Compress': True,
                'CachePolicyId': {'Ref': 'PublicApiCachePolicy'}}
    if 'FrontendSecurityHeaders' in resources:
        behavior['ResponseHeadersPolicyId'] = {'Ref': 'FrontendSecurityHeaders'}
    config['CacheBehaviors'] = [b for b in config.get('CacheBehaviors', []) if b.get('PathPattern') != PUBLIC_API_PATH] + [behavior]
    return True


def extend(template):
    resources = template['Resources']
    params = template['Parameters']
    conditions = template.setdefault('Conditions', {})
    api = resources['ApiFunction']['Properties']

    # 1. Cold start: import the SDK during init; optionally snapshot it.
    api['Handler'] = 'cloudhub.api_entry.handler'
    api['AutoPublishAlias'] = 'live'
    params['ApiSnapStart'] = {'Type': 'String', 'AllowedValues': ['Disabled', 'Enabled'], 'Default': 'Disabled',
        'Description': 'Lambda SnapStart for the API function. Enabled removes most cold start time; '
                       'Python SnapStart bills snapshot cache and restores (~6 USD/month at 1536 MB).'}
    conditions['ApiSnapStartEnabled'] = {'Fn::Equals': [{'Ref': 'ApiSnapStart'}, 'Enabled']}
    api['SnapStart'] = {'ApplyOn': {'Fn::If': ['ApiSnapStartEnabled', 'PublishedVersions', 'None']}}

    # 2. Public catalog: warm-container cache, browser max-age (see cloudhub.api).
    api['Environment']['Variables']['PUBLIC_CATALOG_CACHE_SECONDS'] = '60'

    # 3. Throttling: protect Lambda concurrency and DynamoDB from floods.
    http = resources['HttpApi']['Properties']
    http['DefaultRouteSettings'] = {'ThrottlingBurstLimit': DEFAULT_BURST, 'ThrottlingRateLimit': DEFAULT_RATE}
    http['RouteSettings'] = {'GET /public/catalog': {'ThrottlingBurstLimit': PUBLIC_ROUTE_BURST,
                                                     'ThrottlingRateLimit': PUBLIC_ROUTE_RATE}}

    # 4. Latency alarms and dashboard, tied to the 2 s acceptance target.
    alarm = {'ExtendedStatistic': 'p95', 'Period': 300, 'EvaluationPeriods': 3,
             'DatapointsToAlarm': 2, 'ComparisonOperator': 'GreaterThanThreshold',
             'TreatMissingData': 'notBreaching', 'AlarmActions': [{'Ref': 'AlertTopic'}]}
    resources['ApiLatencyP95Alarm'] = {'Type': 'AWS::CloudWatch::Alarm', 'Properties': {**alarm,
        'AlarmDescription': 'HTTP API p95 latency above 2 s in 2 of 3 five-minute periods',
        'Namespace': 'AWS/ApiGateway', 'MetricName': 'Latency',
        'Dimensions': [{'Name': 'ApiId', 'Value': {'Ref': 'HttpApi'}}], 'Threshold': API_P95_THRESHOLD_MS}}
    resources['ApiFunctionDurationP95Alarm'] = {'Type': 'AWS::CloudWatch::Alarm', 'Properties': {**alarm,
        'AlarmDescription': 'API Lambda p95 duration above 2 s (cold starts or slow dependencies)',
        'Namespace': 'AWS/Lambda', 'MetricName': 'Duration',
        'Dimensions': [{'Name': 'FunctionName', 'Value': {'Ref': 'ApiFunction'}}], 'Threshold': API_P95_THRESHOLD_MS}}
    dashboard = resources.get('OperationsDashboard')
    if dashboard:
        body = json.loads(dashboard['Properties']['DashboardBody']['Fn::Sub'])
        body['widgets'].append({'type': 'metric', 'x': 0, 'y': 6, 'width': 24, 'height': 6, 'properties': {
            'title': 'API Lambda duration and concurrency', 'region': '${AWS::Region}', 'period': 60,
            'metrics': [['AWS/Lambda', 'Duration', 'FunctionName', '${ApiFunction}', {'stat': 'p50'}],
                        ['...', {'stat': 'p95'}],
                        ['AWS/Lambda', 'ConcurrentExecutions', 'FunctionName', '${ApiFunction}', {'stat': 'Maximum', 'yAxis': 'right'}],
                        ['AWS/Lambda', 'Throttles', 'FunctionName', '${ApiFunction}', {'stat': 'Sum', 'yAxis': 'right'}]]}})
        dashboard['Properties']['DashboardBody'] = {'Fn::Sub': json.dumps(body)}

    # The frontend distribution itself is tuned in hosting.configure_edge, the
    # edge stack that serves cloudhub1.me. The source template is left
    # unchanged so hosting.split_edge can still IMPORT it without drift.
    return template
