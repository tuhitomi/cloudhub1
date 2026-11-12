"""CloudFront web ACL for the frontend. CLOUDFRONT-scope WAF must be created in us-east-1.

Deploy this template in us-east-1, then pass its WebAclArn output to the edge
stack parameter FrontendWebAclArn. An empty value detaches it again.
"""
from resilience_infra import managed_rule, rate_rule, visibility

EDGE_RATE_LIMIT = 2000  # requests per IP in any 5-minute window


def template():
    return {'AWSTemplateFormatVersion': '2010-09-09',
        'Description': 'CloudHub frontend web ACL (CLOUDFRONT scope, us-east-1 only)',
        'Rules': {'UsEast1Only': {'Assertions': [{'Assert': {'Fn::Equals': [{'Ref': 'AWS::Region'}, 'us-east-1']},
            'AssertDescription': 'CloudFront web ACLs must be created in us-east-1'}]}},
        'Resources': {'FrontendWebAcl': {'Type': 'AWS::WAFv2::WebACL', 'Properties': {
            'Name': {'Fn::Sub': '${AWS::StackName}-frontend'}, 'Scope': 'CLOUDFRONT', 'DefaultAction': {'Allow': {}},
            'Description': 'CloudHub frontend: AWS managed rules and per-IP rate limit',
            'Rules': [managed_rule('AWSManagedRulesAmazonIpReputationList', 0),
                      managed_rule('AWSManagedRulesKnownBadInputsRuleSet', 1),
                      managed_rule('AWSManagedRulesCommonRuleSet', 2),
                      rate_rule(EDGE_RATE_LIMIT, 3)],
            'VisibilityConfig': visibility('CloudHubFrontend')}}},
        'Outputs': {'WebAclArn': {'Value': {'Fn::GetAtt': ['FrontendWebAcl', 'Arn']}}}}


def attach(result):
    """Optional WebACLId on the edge distribution; idempotent."""
    params, conditions = result['Parameters'], result.setdefault('Conditions', {})
    params['FrontendWebAclArn'] = {'Type': 'String', 'Default': '',
        'AllowedPattern': '(|arn:aws:wafv2:us-east-1:[0-9]{12}:global/webacl/.+)',
        'Description': 'WebAclArn output of the us-east-1 edge WAF stack; empty for none'}
    conditions['HasFrontendWebAcl'] = {'Fn::Not': [{'Fn::Equals': [{'Ref': 'FrontendWebAclArn'}, '']}]}
    config = result['Resources']['FrontendDistribution']['Properties']['DistributionConfig']
    config['WebACLId'] = {'Fn::If': ['HasFrontendWebAcl', {'Ref': 'FrontendWebAclArn'}, {'Ref': 'AWS::NoValue'}]}
    return result


if __name__ == '__main__':
    import json
    from pathlib import Path
    out = Path(__file__).resolve().parents[1] / 'infra/hosting/edge-waf.example.json'
    out.write_text(json.dumps(template(), indent=2) + '\n', encoding='utf-8')
    print('Generated ' + str(out))
