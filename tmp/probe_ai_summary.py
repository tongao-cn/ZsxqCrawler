from pathlib import Path
import sys
repo = Path(r'C:\Dev\ZsxqCrawler')
sys.path.insert(0, str(repo))
from backend.services.stock_topic_analysis_service import analyze_stock_topics
r = analyze_stock_topics('15552822451452', '中际旭创', limit=8)
print('status=', r.get('status'))
print('topic_count=', r.get('topic_count'))
print('summary_len=', len(r.get('summary_markdown','')))
print(r.get('summary_markdown','')[:3000])
