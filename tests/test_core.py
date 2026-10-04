import csv
import json
from dataclasses import replace
from threading import Event
from types import SimpleNamespace
import pytest
from fastmoss_auto.bridge import Bridge
from fastmoss_auto.collector import Collector, GUARD_JS, NEXT_JS, PAGE_JS
from fastmoss_auto.domain import Job, Cancelled, load_sections
from fastmoss_auto.export import export_run, numeric_sales

@pytest.fixture
def job(tmp_path):
    return Job(output=str(tmp_path / '中文 输出'), wait=1, pages=2)

class ImmediateEvent:
    def __init__(self, stopped=False): self.stopped = stopped
    def is_set(self): return self.stopped
    def wait(self, seconds): return self.stopped

class FakeBridge:
    def __init__(self, pages=None, failure=None):
        self.pages = pages if pages is not None else [[['A', '新加坡']], [['B', '新加坡']]]
        self.failure, self.index, self.closed, self.filters = failure, 0, False, []
    def start(self): pass
    def navigate(self, url): self.url = url
    def evaluate(self, js):
        if js == 'extract': return {'rows': self.pages[self.index], 'headers': ['商品', '国家']}
        if js == GUARD_JS: return {'table': True, 'blocked': self.failure == 'login'}
        if js == NEXT_JS:
            if self.index + 1 >= len(self.pages): return {'clicked': False}
            self.index += 1
            return {'clicked': True}
        if js == PAGE_JS: return {'page': str(self.index + 1)}
        if js.endswith(', "click")\n'): self.filters.append(js)
        return {'found': self.failure != 'missing', 'selected': self.failure != 'unselected'}
    def close(self): self.closed = True

SECTIONS = {'products': {'url': 'https://www.fastmoss.com/zh/e-commerce/newProducts',
    'extract_js': 'extract', 'parse_row': lambda c: {'product_name': c[0], 'country': c[1]}},
    'shops': {'rankings': {'sales': 'https://www.fastmoss.com/zh/shop-marketing/tiktok'},
    'extract_js': 'extract', 'parse_row': lambda headers, c: {'shop_name': c[0]}}}

def collect(job, fake):
    return Collector(fake, SECTIONS).collect(job, ImmediateEvent())

def test_combined_filter_and_pagination(job):
    fake = FakeBridge()
    rows, warnings = collect(job, fake)
    assert [r['product_name'] for r in rows] == ['A', 'B']
    assert rows[1]['page'] == 2
    assert all(r['filter_shop_type'] == '跨境店' for r in rows)
    assert len(fake.filters) == 3
    assert all(label in ''.join(fake.filters) for label in ['新加坡', '跨境店', '宠物用品'])
    assert fake.closed and not warnings

@pytest.mark.parametrize('failure', ['missing', 'unselected', 'login'])
def test_filter_or_login_failure(job, failure):
    fake = FakeBridge(failure=failure)
    with pytest.raises(RuntimeError): collect(job, fake)
    assert fake.closed

def test_duplicate_page_rejected(job):
    fake = FakeBridge(pages=[[['A', '新加坡']], [['A', '新加坡']]])
    with pytest.raises(RuntimeError, match='重复'): collect(job, fake)
    assert fake.closed

def test_last_page_stops(job):
    rows, warnings = collect(job, FakeBridge(pages=[[['A', '新加坡']]]))
    assert len(rows) == 1 and warnings

def test_wrong_country_rejected(job):
    with pytest.raises(RuntimeError, match='国家'): collect(job, FakeBridge(pages=[[['A', '泰国']]]))

def test_empty_page_rejected(job):
    with pytest.raises(RuntimeError, match='没有可解析'): collect(job, FakeBridge(pages=[[]]))

def test_cancellation_cleans_up(job):
    fake = FakeBridge()
    with pytest.raises(Cancelled): Collector(fake, SECTIONS).collect(job, ImmediateEvent(True))
    assert fake.closed

def test_shop_ranking(job):
    fake = FakeBridge()
    rows, _ = collect(replace(job, section='shops', category='', pages=1), fake)
    assert 'shop-marketing' in fake.url and rows[0]['shop_name'] == 'A'

def test_export_unicode_and_unique_runs(job):
    rows = [{'product_name': '宠物猫玩具', 'sales_period': '1.2k'}]
    first, second = export_run(job, rows), export_run(job, rows)
    assert first != second and first.parent == second.parent
    assert (first / 'data.csv').read_bytes().startswith(b'\xef\xbb\xbf')
    with (first / 'data.csv').open(encoding='utf-8-sig', newline='') as f:
        assert list(csv.DictReader(f))[0]['product_name'] == '宠物猫玩具'
    data = json.loads((first / 'data.json').read_text(encoding='utf-8'))
    assert data['filters']['shop_type'] == '跨境店' and data['row_count'] == 1
    assert (first / 'report.md').exists() and 'source' not in data['filters']

def test_failed_export_removed(job, monkeypatch):
    import pandas as pd
    def fail(*args, **kwargs): raise OSError('disk full')
    monkeypatch.setattr(pd.DataFrame, 'to_csv', fail)
    with pytest.raises(OSError): export_run(job, [{'name': 'A'}])
    from pathlib import Path
    assert list(Path(job.output).iterdir()) == []

@pytest.mark.parametrize('value, expected', [('1.2k', 1200), ('2万', 20000), ('1,234', 1234), ('0', 0), ('S$20', None), ('1-20', None), ('--', None)])
def test_numeric_sales(value, expected): assert numeric_sales(value) == expected

@pytest.mark.parametrize('kwargs', [{'country': ''}, {'pages': 0}, {'wait': 0}, {'output': ''}, {'section': 'ads'}])
def test_validation(job, kwargs):
    with pytest.raises(ValueError): replace(job, **kwargs).validate()

def test_missing_upstream(tmp_path):
    with pytest.raises(ValueError, match='sections.py'): load_sections(tmp_path)

def test_bridge_argument_safety(monkeypatch):
    seen = []
    def run(command, **kwargs):
        seen.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr='')
    monkeypatch.setattr('subprocess.run', run)
    bridge = Bridge('C:/工具/bsk.exe'); bridge.session = 'test'
    assert bridge.evaluate('console.log("$HOME");') == {'ok': True}
    assert seen[0][0][0] == 'C:/工具/bsk.exe'
    assert seen[0][0][2] == 'console.log("$HOME");'
    assert not seen[0][1].get('shell')

def test_cancelled_session_retained_for_cleanup(monkeypatch):
    event = Event()
    def run(*args, **kwargs):
        event.set()
        return SimpleNamespace(returncode=0, stdout='{"session_id":"abcd"}', stderr='')
    monkeypatch.setattr('subprocess.run', run)
    bridge = Bridge(cancel=event)
    with pytest.raises(Cancelled): bridge.start()
    assert bridge.session == 'abcd'
    bridge.close()
    assert bridge.session is None
