"""Validate ownership of present files and report pending integration."""
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]

def verify():
    doc=json.loads((ROOT/'team/file-ownership.json').read_text(encoding='utf-8'))
    rows=doc['files'];names=[row['path'] for row in rows]
    assert len(names)==len(set(names)), 'Duplicate ownership assignment'
    members=json.loads((ROOT/'team/members.json').read_text(encoding='utf-8'))
    for row in rows:
        assert row['owner'] in members and row['reason'],row['path']
    raw=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT)
    current={value.decode() for value in raw.split(bytes([0])) if value}
    assert current<=set(names), 'Unassigned files: '+str(sorted(current-set(names)))
    assert all((ROOT/name).is_file() for name in current), 'Tracked file missing'
    pending=[row for row in rows if row['path'] not in current]
    if not doc.get('allow_pending_files'):
        assert not pending, 'Required files are absent'
    return {'present':len(current),'planned':len(names),'pending':len(pending),
            'exactly_one_owner_per_present_file':True,'unassigned':0}

if __name__=='__main__':
    print(json.dumps(verify(),ensure_ascii=False))
