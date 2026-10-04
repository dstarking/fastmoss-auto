from dataclasses import replace
import csv
import json
from io import BytesIO
import pytest
from fastmoss_auto.collector import Collector, SALES_BOARD_JS, GUARD_JS
from fastmoss_auto.domain import Job, Cancelled
from fastmoss_auto.schema import category_matches
from fastmoss_auto.export import export_run, download_image
from test_core import FakeBridge, ImmediateEvent, SECTIONS

@pytest.mark.parametrize('actual, ok', [('宠物用品', True), ('宠物用品 / 宠物玩具', True), ('宠物用品-猫玩具', True), ('宠物用品店', False), ('美妆 / 宠物用品', False), ('', False)])
def test_exact_category(actual, ok):
    assert category_matches('宠物用品', actual) == ok
    assert not category_matches('宠物用品 / 猫玩具', '宠物用品 / 狗玩具')

def test_category_mismatch_blocks_export(tmp_path):
    sections = {'products': {**SECTIONS['products'], 'parse_row': lambda c: {'product_name': c[0], 'country': c[1], 'category': '美妆'}}}
    fake = FakeBridge()
    with pytest.raises(RuntimeError, match='类目不一致'):
        Collector(fake, sections).collect(Job(output=str(tmp_path)), ImmediateEvent())
    assert fake.closed and not list(tmp_path.iterdir())

def test_stale_category_recovers(tmp_path):
    count = 0
    def parse(c):
        nonlocal count
        count += 1
        return {'product_name': c[0], 'country': c[1], 'category': '美妆' if count == 1 else '宠物用品 / 猫玩具'}
    cfg = {'products': {**SECTIONS['products'], 'parse_row': parse}}
    rows, _ = Collector(FakeBridge(), cfg).collect(Job(output=str(tmp_path), pages=1), ImmediateEvent())
    assert count == 2  # stale row rejected, then refreshed row accepted
    assert all(r['category_verification'] == 'row_and_page_filter' for r in rows)

def test_sales_board_required(tmp_path):
    class Missing(FakeBridge):
        def evaluate(self, js):
            if js == SALES_BOARD_JS: return {'url': ''}
            return super().evaluate(js)
    with pytest.raises(RuntimeError, match='销量榜入口'):
        Collector(Missing(), SECTIONS).collect(Job(output=str(tmp_path)), ImmediateEvent())

def test_redirect_away_from_sales_rejected(tmp_path):
    class Redirect(FakeBridge):
        def evaluate(self, js):
            if js == GUARD_JS: return {'table': True, 'url': 'https://www.fastmoss.com/zh/e-commerce/newProducts'}
            return super().evaluate(js)
    with pytest.raises(RuntimeError, match='离开商品销量榜'):
        Collector(Redirect(), SECTIONS).collect(Job(output=str(tmp_path)), ImmediateEvent())

def test_metadata_and_identity_dedup(tmp_path):
    class Duplicate(FakeBridge):
        def evaluate(self, js):
            result = super().evaluate(js)
            if js == 'extract':
                result['product_metadata'] = [{'product_id': '99', 'product_title': 'Full title', 'product_url': 'https://www.fastmoss.com/zh/e-commerce/detail/99', 'main_image_url': 'https://example.com/p.png'}]
            return result
    rows, warnings = Collector(Duplicate(), SECTIONS).collect(Job(output=str(tmp_path), pages=2), ImmediateEvent())
    assert len(rows) == 1 and not warnings
    assert rows[0]['product_title'] == 'Full title' and rows[0]['ranking'] == 'sales'
    assert rows[0]['source_url'].endswith('verified-sales-board')

def test_required_category(tmp_path):
    with pytest.raises(ValueError, match='指定品类'):
        Job(output=str(tmp_path), category='').validate()

def test_image_export_and_bestsellers(tmp_path, monkeypatch):
    import fastmoss_auto.export as module
    calls = []
    class Image(BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    def fetch(request, timeout):
        calls.append(request.full_url)
        return Image(b'\x89PNG\r\n\x1a\nfixture')
    monkeypatch.setattr(module, 'urlopen', fetch)
    rows = [{'product_name': 'A', 'sales_period': '100', 'main_image_url': 'https://example.com/p.png'},
            {'product_name': 'B', 'sales_period': '2k', 'main_image_url': 'https://example.com/p.png'},
            {'product_name': 'C', 'sales_period': '10-200'}, {'product_name': 'D', 'total_sales': '90000'}]
    run = export_run(Job(output=str(tmp_path)), rows)
    data = json.loads((run / 'data.json').read_text(encoding='utf-8'))
    assert len(calls) == 1
    assert (run / data['rows'][0]['main_image_file']).read_bytes().startswith(b'\x89PNG')
    with (run / 'bestsellers.csv').open(encoding='utf-8-sig', newline='') as f:
        ranked = list(csv.DictReader(f))
    assert [r['product_title'] for r in ranked] == ['B', 'A']
    assert [r['candidate_rank'] for r in ranked] == ['1', '2']
    assert 'main_image_url' in ranked[0] and 'product_url' in ranked[0]

def test_image_failure_is_explicit(tmp_path, monkeypatch):
    def fail(*args): raise OSError('expired')
    monkeypatch.setattr('fastmoss_auto.export.download_image', fail)
    run = export_run(Job(output=str(tmp_path)), [{'product_name': 'A', 'main_image_url': 'https://example.com/p.png'}])
    data = json.loads((run / 'data.json').read_text(encoding='utf-8'))
    assert data['rows'][0]['main_image_file'] == ''
    assert '下载失败' in data['warnings'][0]
    assert data['rows'][0]['main_image_url'] == 'https://example.com/p.png'

def test_cancel_export_removes_partial_files(tmp_path):
    with pytest.raises(Cancelled):
        export_run(Job(output=str(tmp_path)), [{'product_name': 'A'}], cancel=ImmediateEvent(True))
    assert not list(tmp_path.iterdir())
