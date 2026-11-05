"""Offline, isolated-platform deployment packet. Never deploy or move production.

Reuse the existing SAM/network generators; keep proofs and feature gates closed.
This packet is NOT the native production template or a data/identity migration.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from cloudhub.regions import REGIONS
from cloudhub.catalog import ACTIVE_TEMPLATES
from cloudhub.cost import RATE_REQUIREMENTS
from generate_infra import build_template
from generate_network import generate as network_template
from public_assets import ASSETS

FIELDS = {'schema', 'account_id', 'region', 'profile', 'stack_name', 'regional_inputs',
          'prices_file', 'budget_usd', 'cash_budget_usd', 'approval_reference'}
INPUTS = {'VpcId', 'PublicSubnetId', 'PublicSubnet2Id', 'DbSubnet1Id', 'DbSubnet2Id',
          'AvailabilityZone', 'AmiId', 'SshCidr', 'PostgresVersion', 'ApprovedImage'}
CLOSED = ('ContinuousEnabled', 'DirectUploadEnabled', 'RecommendationsEnabled',
          'ApplicationBootstrapPermissionsEnabled', 'EnableRegionalT07')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def plan(config, prices=None):
    if not isinstance(config, dict) or set(config) - FIELDS or config.get('schema') != 1:
        raise ValueError('Only platform-target schema 1 fields are accepted; no credentials or feature overrides')
    region = config.get('region')
    if region not in REGIONS:
        raise ValueError('Target Region is outside the current backend allowlist; add and verify support first')
    stack = config.get('stack_name', '')
    # Cognito domain also appends account ID; leave room within its hostname label.
    if not isinstance(stack, str) or not re.fullmatch(r'[a-z][a-z0-9-]{2,39}', stack):
        raise ValueError('Use a distinct lowercase stack name, 3-40 characters')
    profile = config.get('profile', '')
    if not isinstance(profile, str) or not re.fullmatch(r'[A-Za-z0-9_.@-]{1,128}', profile):
        raise ValueError('An explicit AWS profile name is required')
    inputs = config.get('regional_inputs', {})
    if not isinstance(inputs, dict) or set(inputs) - INPUTS:
        raise ValueError('Unknown regional input; never copy arbitrary live parameters')
    blockers = []
    if profile.startswith('REQUIRED'):
        blockers.append('Set the target AWS profile; the example profile is not a session')
    account = str(config.get('account_id', ''))
    if not re.fullmatch(r'\d{12}', account):
        blockers.append('Set and verify target account_id with STS')
    patterns = {'VpcId': r'vpc-[a-f0-9]{8,17}', 'AmiId': r'ami-[a-f0-9]{8,17}',
                'PostgresVersion': r'\d+\.\d+(?:\.\d+)?',
                'AvailabilityZone': re.escape(region) + r'[a-z]'}
    patterns.update({k: r'subnet-[a-f0-9]{8,17}' for k in INPUTS if 'Subnet' in k})
    for key, pattern in patterns.items():
        if not isinstance(inputs.get(key), str) or not re.fullmatch(pattern, inputs[key]):
            blockers.append('Missing/invalid target ' + key)
    subnets = [inputs.get(k) for k in ('PublicSubnetId', 'PublicSubnet2Id', 'DbSubnet1Id', 'DbSubnet2Id')]
    if len(set(subnets)) != 4:
        blockers.append('Four distinct target subnets are required; inspect VPC and two AZ pairs on AWS')
    try:
        cidr = ipaddress.ip_network(inputs.get('SshCidr', ''), strict=True)
        if cidr.version != 4 or cidr.prefixlen < 24:
            raise ValueError()
    except (ValueError, TypeError):
        blockers.append('Set approved IPv4 SSH CIDR /24 or narrower')
    image_pattern = re.escape(account) + r'\.dkr\.ecr\.' + re.escape(region) + r'\.amazonaws\.com/[a-z0-9/_-]+@sha256:[a-f0-9]{64}'
    if not isinstance(inputs.get('ApprovedImage'), str) or not re.fullmatch(image_pattern, inputs['ApprovedImage']):
        blockers.append('Set reviewed own-account same-Region ECR image pinned by digest')
    amounts = {}
    for key in ('budget_usd', 'cash_budget_usd'):
        try:
            value = Decimal(str(config.get(key)))
            if not value.is_finite() or value < 0 or key == 'budget_usd' and value <= 0:
                raise ValueError()
            if value * 1000 != (value * 1000).to_integral_value():
                raise ValueError()
            amounts[key] = value
        except (InvalidOperation, ValueError):
            blockers.append('Set reviewed ' + key + ' (USD, at most 3 decimal places)')
    if not isinstance(config.get('approval_reference'), str) or not config['approval_reference'].strip():
        blockers.append('Record the new platform cost/cleanup approval reference')
    price_ready = (isinstance(prices, dict) and prices.get('approved') is True
                   and prices.get('region') == region and prices.get('updated_at')
                   and prices.get('source_urls') and isinstance(prices.get('units'), dict) and prices['units'])
    if price_ready:
        required_rates = set().union(*(RATE_REQUIREMENTS[tid] for tid in ACTIVE_TEMPLATES))
        price_ready = required_rates <= set(prices['units'])
    if price_ready:
        try:
            price_ready = all(Decimal(str(v)).is_finite() and Decimal(str(v)) >= 0 for v in prices['units'].values())
        except InvalidOperation:
            price_ready = False
    if not price_ready:
        blockers.append('Supply a reviewed, finite, sourced target-Region price file; missing prices are unknown')
    parameters = {k: v for k, v in inputs.items() if isinstance(v, str)}
    parameters.update({key: 'false' for key in CLOSED})
    parameters.update(VerifiedTemplates='', ValidationTemplates='', RegionsJson='{"regions":{}}',
                      DriverRegionsJson='{}', BudgetMilliusd=str(int(amounts.get('budget_usd', Decimal(0)) * 1000)),
                      PricesJson=json.dumps({k: prices[k] for k in ('approved', 'region', 'updated_at', 'units')},
                                            separators=(',', ':')) if price_ready else '{"approved":false}')
    return {'mode': 'NEW_ISOLATED_PLATFORM_REVIEW_ONLY', 'account_id': account, 'region': region,
            'profile': profile, 'stack_name': stack, 'configuration_blockers': blockers,
            'local_inputs_complete': not blockers, 'aws_mutations': 0, 'aws_verified': False,
            'production_cutover_allowed': False, 'customer_environments_moved': 0,
            'source_proofs_reused': False, 'private_parameters_required': ['UiEdgeSecret'],
            'parameters_for_review': [{'ParameterKey': k, 'ParameterValue': v} for k, v in sorted(parameters.items())],
            'mandatory_aws_checks': ['STS account/profile and target Region enabled',
                'New stack name unused; no replacement/update of production',
                'Inventory, ledger, actual Billing/credits and new platform cost approval',
                'Target VPC, two classic AZ pairs, AMI, RDS, ECR, quotas and IAM',
                'Template lint, packaged changeset and exact parameter review',
                'Private origin secret generated locally; never commit or log it',
                'Fresh runtime configuration, exact-combination AWS proofs before opening gates'],
            'limitations': ['Current backend allowlist contains only Singapore, Tokyo and Northern Virginia',
                'Application bootstrap update IAM remains Singapore-specific and disabled',
                'New Cognito pool, new data table and new edge: no existing users/data/domain are moved',
                'Isolated deployment is not high availability, failover, or Region migration',
                'Network proposal uses 10.42.0.0/16; check overlap before accepting it',
                'No numeric AWS cost total is inferred from the internal forecast cap']}


def prepare(config, destination, prices=None):
    review = plan(config, prices)
    destination = Path(destination).resolve()
    if destination == ROOT or ROOT.is_relative_to(destination) or any(
            destination.is_relative_to(ROOT / name) for name in ('backend', 'frontend', 'infra', 'scripts', 'config', 'docs', 'tests')):
        raise ValueError('Use a dedicated output directory outside product source directories')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Output must be empty: existing artifacts are never overwritten')
    template = build_template()
    unsupported = {row['ParameterKey'] for row in review['parameters_for_review']} - set(template['Parameters'])
    if unsupported:
        raise ValueError('Generated SAM parameter mismatch: ' + ', '.join(sorted(unsupported)))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'infra').mkdir()
    write_json(destination / 'infra/control-plane.json', template)
    write_json(destination / 'infra/network.json', network_template())
    (destination / 'infra/lifecycle.asl.json').write_bytes((ROOT / 'infra/lifecycle.asl.json').read_bytes())
    sources = [p for p in (ROOT / 'backend').rglob('*.py') if '__pycache__' not in p.parts]
    sources += list((ROOT / 'scripts').glob('*.py'))
    sources += [ROOT / 'frontend' / name for name in ASSETS]
    sources += [ROOT / name for name in ('docs/platform-portability-runbook.md', 'config/platform-target.example.json')]
    for source in sorted(sources):
        if source.is_symlink() or not source.resolve().is_relative_to(ROOT):
            raise ValueError('Source symlink/external file is not allowed')
        output = destination / source.relative_to(ROOT)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(source.read_bytes())
    write_json(destination / 'parameters.review.json', review['parameters_for_review'])
    review['created_at'] = datetime.now(timezone.utc).isoformat()
    review['resource_inventory'] = {k: {'type': r['Type'], 'retained': r.get('DeletionPolicy') == 'Retain',
                                      'condition': r.get('Condition')} for k, r in template['Resources'].items()}
    write_json(destination / 'review.json', review)
    files = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(destination.rglob('*')) if p.is_file()}
    write_json(destination / 'manifest.json', {'schema': 1, 'files': files,
               'source_snapshot_sha256': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
               'aws_deployed': False})
    return review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--draft', action='store_true', help='Emit incomplete review; does not authorize deployment')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    price_path = config.get('prices_file')
    if price_path:
        price_path = Path(price_path)
        if not price_path.is_absolute():
            price_path = args.config.parent / price_path
    prices = json.loads(price_path.read_text(encoding='utf-8-sig')) if price_path else None
    review = prepare(config, args.out, prices)
    print(json.dumps({'mode': review['mode'], 'region': review['region'],
                      'configuration_blockers': review['configuration_blockers'], 'aws_mutations': 0}))
    return 0 if args.draft or review['local_inputs_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
