from pathlib import Path
lines = Path(r'docs/xmind/光模块.txt').read_text(encoding='utf-8').splitlines()
for i,l in enumerate(lines[:120],1):
    if l.strip():
        print(f'{i:03d} {len(l)-len(l.lstrip("\t"))} {l.strip()}')
