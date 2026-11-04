"""Prepare an immutable-Region migration review from an exported metadata inventory.
No AWS calls and no live writes; ambiguous provenance is preserved for review.
"""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from cloudhub.regions import record_region
from cloudhub.errors import HubError
def review(rows):
    by_id={r['environment_id']:r for r in rows if r.get('kind')=='environment'}
    candidates=[];blocked=[];existing=0
    for row in rows:
        if row.get('kind') not in {'environment','recovery','operation'}:continue
        try:
            value=row
            if not row.get('region') and row.get('kind') in {'recovery','operation'}:
                parent=by_id.get(row.get('environment_id'))
                if parent and parent.get('owner_id')==row.get('owner_id'):value={**row,'region':record_region(parent,{})}
            region=record_region(value,{})
            if row.get('region'):existing+=1;continue
            candidates.append({'pk':row['pk'],'owner_id':row['owner_id'],'expected_version':row.get('version'),
                'region':region,'condition':'version and owner unchanged; attribute_not_exists(region)',
                'region_provenance':'verified_persisted_metadata'})
        except HubError as error:blocked.append({'pk':row.get('pk'),'reason':error.code})
    return {'mode':'OFFLINE_REVIEW_ONLY','aws_writes':0,'existing_unchanged':existing,'candidates':candidates,'blocked':blocked}
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',required=True,type=Path);parser.add_argument('--out',required=True,type=Path);args=parser.parse_args()
    data=json.loads(args.input.read_text(encoding='utf-8'));result=review(data.get('items',[]) if isinstance(data,dict) else data)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'candidates':len(result['candidates']),'blocked':len(result['blocked']),'aws_writes':0}))
