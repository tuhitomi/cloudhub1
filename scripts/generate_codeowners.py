"""Generate real CODEOWNERS only after all four GitHub identities are supplied."""
import argparse,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');a=p.parse_args()
members=json.loads((ROOT/'team/members.json').read_text(encoding='utf-8'))
for label,member in members.items():
    handle=member.get('github')
    if not isinstance(handle,str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?',handle):raise SystemExit('Cần GitHub handle đã xác minh cho '+label+'; không tạo CODEOWNERS giả.')
doc=json.loads((ROOT/'team/file-ownership.json').read_text(encoding='utf-8'))
lines=['# Generated from team/file-ownership.json and verified team/members.json.']
lines+=['/'+r['path']+' @'+members[r['owner']]['github'] for r in doc['files']]
text=chr(10).join(lines)+chr(10)
if a.write:
    (ROOT/'.github/CODEOWNERS').write_text(text,encoding='utf-8')
    print('Created CODEOWNERS. Add this new file to the ownership manifest; GitHub owners also need separately authorized write access.')
else:print(text)
