import json
from pathlib import Path
j = json.loads(Path(r'tmp/deep_topics.json').read_text(encoding='utf-8'))
for group in ['调研鹅纪要','纪要又要']:
    print('GROUP', group)
    top = sorted(((name, rec.get('topic_count',0)) for name, rec in j[group].items() if rec.get('topic_count')), key=lambda x: (-x[1], x[0]))[:25]
    for name, cnt in top:
        print(name, cnt)
    print()
