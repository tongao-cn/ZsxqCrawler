from pathlib import Path
lines = Path(r'docs/xmind/光模块.txt').read_text(encoding='utf-8').splitlines()
companies=[]
for i,line in enumerate(lines):
    if not line.strip():
        continue
    if i+1 < len(lines) and lines[i+1].strip().startswith('一句话总结'):
        companies.append(line.strip())
print(len(companies))
for c in companies:
    print(c)
