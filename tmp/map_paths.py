from pathlib import Path
lines = Path(r'docs/xmind/光模块.txt').read_text(encoding='utf-8').splitlines()
stack=[]
companies=[]
for i,line in enumerate(lines):
    if not line.strip():
        continue
    lvl = len(line)-len(line.lstrip('\t'))
    text = line.strip()
    # summary label means company block follows
    if text.startswith('一句话总结') and stack:
        continue
    # detect company start: unindented line followed by summary label
    if lvl==0 and i+1 < len(lines) and lines[i+1].strip().startswith('一句话总结'):
        companies.append((text, [x[1] for x in stack]))
        continue
    # category or other heading
    while stack and stack[-1][0] >= lvl:
        stack.pop()
    stack.append((lvl, text))

for name, path in companies[:40]:
    print(' > '.join(path+[name]))
