"""Operator-reviewed content-site renderer. No code, templates or SQL from clients."""
from html import escape
from urllib.parse import urlsplit,parse_qs,quote
import json

def render(config,records,path):
    parsed=urlsplit(path);query=parse_qs(parsed.query).get('q',[''])[0][:100]
    if parsed.path not in {'/','/posts'} and not parsed.path.startswith('/posts/'):return None
    values=records
    if parsed.path.startswith('/posts/'):
        values=[r for r in records if r['record_id']==parsed.path[len('/posts/'):]]
        if not values:return None
    if query:values=[r for r in values if query.casefold() in (r['text']+' '+r['record_id']).casefold()]
    colors={'indigo':'#4f46e5','forest':'#166534','slate':'#334155'};color=colors.get(config.get('theme'),'#334155')
    cards=''.join('<article><h2><a href="/posts/'+quote(r['record_id'],safe='')+'">'+escape(r['record_id'])+'</a></h2><p>'+escape(r['text'])+'</p></article>' for r in values)
    return '<!doctype html><html lang="'+escape(config.get('language','en'),quote=True)+'"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(config['title'])+'</title><style>body{font:18px system-ui;max-width:900px;margin:40px auto;padding:20px;color:#172033}a{color:'+color+'}article{border:1px solid #cbd5e1;border-radius:12px;padding:20px;margin:20px 0}input,button{font:inherit;padding:10px}p{white-space:pre-wrap}</style><header><h1>'+escape(config['title'])+'</h1><p>'+escape(config['subtitle'])+'</p></header><form action="/"><label>Search <input name="q" maxlength="100" value="'+escape(query,quote=True)+'"></label><button>Search</button></form><main>'+cards+'</main></html>'

def load(path):
    with open(path,encoding='utf-8') as source:return json.load(source)
