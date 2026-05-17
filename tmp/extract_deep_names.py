import json
from pathlib import Path
j = json.loads(Path(r'tmp/deep_topics.json').read_text(encoding='utf-8'))
all_names = sorted(set(j['调研鹅纪要']) | set(j['纪要又要']))
print(len(all_names))
for n in all_names:
    print(n)
