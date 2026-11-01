"""Validate pack coverage/placeholders and optionally sync embedded fallback bundles."""
import argparse,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def validate(sync=False):
    codes=['en','vi','ja','ko','zh-Hans','fr','de','es'];packs={c:json.loads((ROOT/'frontend/locales'/f'{c}.json').read_text(encoding='utf-8')) for c in codes};base=packs['en']
    for code,pack in packs.items():
        assert set(pack)==set(base),(code,'coverage')
        for key,text in pack.items():
            assert isinstance(text,str) and text.strip(),(code,key,'empty')
            assert sorted(re.findall(r'\{p\d+\}',text))==sorted(re.findall(r'\{p\d+\}',base[key])),(code,key,'placeholders')
    for code,name in [('en','locale-en.js'),('vi','locale-source.js')]:
        path=ROOT/'frontend'/name
        if sync:path.write_text('export default '+json.dumps(packs[code],ensure_ascii=False)+';\n',encoding='utf-8')
        actual=json.loads(path.read_text(encoding='utf-8').removeprefix('export default ').strip().removesuffix(';'))
        assert actual==packs[code],(name,'stale embedded bundle')
    return {'languages':len(packs),'messages_per_language':len(base),'passed':True}
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sync',action='store_true');args=parser.parse_args();print(json.dumps(validate(args.sync)))
