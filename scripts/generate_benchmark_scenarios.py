"""Version executable benchmark sources; never creates measurement results."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    paths={'agent':'backend/cloudhub/benchmark_agent.py','runner':'scripts/benchmark_workloads.py','http':'benchmarks/http.js'}
    sources={k:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for k,p in paths.items()}
    (ROOT/'backend/cloudhub/benchmark-scenarios.json').write_text(json.dumps(sources,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
