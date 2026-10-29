"""Offline checks for the partial TV1 import; never imports AWS runtime or calls AWS."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'team/handoff-validation.json'
SUITES = ('tests/i18n.test.mjs', 'tests/cockpit.test.mjs', 'tests/shell-view.test.mjs', 'tests/template-view.test.mjs')

def check():
    owner_doc = json.loads((ROOT / 'team/file-ownership.json').read_text(encoding='utf-8'))
    owners = {row['path']: row['owner'] for row in owner_doc['files']}
    selected = [ROOT / name for name, owner in owners.items() if owner == 'TV1' and (ROOT / name).is_file()]
    counts = {'python_syntax': 0, 'javascript_syntax': 0, 'json': 0}
    node = shutil.which('node')
    assert node, 'Node.js required'
    for path in selected:
        text = path.read_text(encoding='utf-8-sig')
        assert '\0' not in text, 'Binary file in handoff'
        if path.suffix == '.py':
            ast.parse(text, filename=path.name); counts['python_syntax'] += 1
        elif path.suffix in {'.js', '.mjs'}:
            subprocess.run([node, '--check', str(path)], check=True, capture_output=True)
            counts['javascript_syntax'] += 1
        elif path.suffix == '.json':
            json.loads(text); counts['json'] += 1
    packs = {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in (ROOT / 'frontend/locales').glob('*.json')}
    assert set(packs) == {'en', 'vi', 'ja', 'ko', 'zh-Hans', 'fr', 'de', 'es'}
    keys = set(packs['en'])
    for code, pack in packs.items():
        assert set(pack) == keys and all(isinstance(v, str) and v.strip() for v in pack.values()), code
        for key in keys:
            assert sorted(re.findall(r'\{[A-Za-z0-9_]+\}', pack[key])) == sorted(re.findall(r'\{[A-Za-z0-9_]+\}', packs['en'][key])), (code, key)
    result = subprocess.run([node, '--test', '--test-reporter=tap', *SUITES], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
    match = re.search(r'# pass (\d+)', result.stdout)
    assert match, result.stdout
    observed = {'scope': 'LOCAL_PARTIAL_TV1_ONLY', 'checks': counts, 'locales': len(packs), 'locale_keys': len(keys),
                'node_suites': list(SUITES), 'frontend_passed': int(match.group(1)),
                'aws_calls': 0, 'full_application_integration_verified': False}
    print(json.dumps(observed, ensure_ascii=False))
    return observed

if __name__ == '__main__':
    check()
