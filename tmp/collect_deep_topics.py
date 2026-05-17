from pathlib import Path
import sys, json
repo = Path(r'C:\Dev\ZsxqCrawler')
sys.path.insert(0, str(repo))
from backend.services.stock_topic_analysis_service import search_stock_topics
companies = [
    '中际旭创','新易盛','联特科技','华工科技','东山精密','光迅科技','博创科技','天孚通信','罗博特科','炬光科技','致尚科技','太辰光','长盈通','源杰科技','长光华芯','仕佳光子','高塔半导体','华为','天通股份','济南晶正','福建晶安','安孚科技','易缆微','云南锗业','博杰股份','珠海鼎泰','福晶科技','光电股份','新华光','东田微','日月大化','株冶集团','腾晖光纤','蓝特光学','宇瞳光学','光库科技','大互光','勇创科技','永鼎光纤','裕太微','思瑞浦','艾为电子','圣邦股份','杰华特','南芯科技','鼎阳科技','普源精电','联讯仪器','胜宏科技','迅捷兴','沪电股份','景旺电子','方正科技','鹏鼎控股','崇达技术','臻鼎-KY','华正新材','FiconTEC','科隆威','英唐智控','赛微电子','泰晶科技'
]
result = {}
for gid, gname in [('15552822451452','调研鹅纪要'), ('51111112855254','纪要又要')]:
    g = {}
    for c in companies:
        try:
            r = search_stock_topics(gid, c, limit=8)
        except Exception as e:
            g[c] = {'error': str(e)}
            continue
        g[c] = {
            'topic_count': r.get('topic_count', 0),
            'recommendation_count': r.get('recommendation_count', 0),
            'concepts': r.get('concepts', []),
            'topics': [
                {
                    'title': t.get('title', ''),
                    'create_time': t.get('create_time', ''),
                    'preview': t.get('content_preview', ''),
                    'likes_count': t.get('likes_count', 0),
                    'comments_count': t.get('comments_count', 0),
                    'reading_count': t.get('reading_count', 0),
                }
                for t in r.get('topics', [])
            ],
        }
    result[gname] = g
Path('tmp/deep_topics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print('saved', len(result))
