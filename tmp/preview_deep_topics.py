import json
from pathlib import Path
j = json.loads(Path(r'tmp/deep_topics.json').read_text(encoding='utf-8'))
for group in ['调研鹅纪要','纪要又要']:
    print('GROUP', group)
    for name in ['中际旭创','新易盛','联特科技','天孚通信','罗博特科','太辰光','华工科技','胜宏科技','沪电股份','华正新材','福晶科技','光电股份','英唐智控','赛微电子','鼎阳科技','普源精电','联讯仪器','云南锗业','长飞光纤','长盈通','腾景科技']:
        rec = j.get(group, {}).get(name)
        if rec and rec.get('topic_count'):
            print(name, rec['topic_count'])
            for t in rec['topics'][:3]:
                print(' -', t['title'][:60], '||', t['preview'][:120])
    print()
