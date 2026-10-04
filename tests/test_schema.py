from dataclasses import replace
import pytest
from fastmoss_auto.schema import canonical_country, country_tokens, parse_product, PRODUCT_EXTRACT_JS
from fastmoss_auto.domain import Job
from fastmoss_auto.collector import Collector
from test_core import FakeBridge, ImmediateEvent, SECTIONS

@pytest.mark.parametrize('value', ['新加坡', 'SG', 'SGP', 'Singapore', 'Singapore\nSG', '🇸🇬', 'flag of Singapore'])
def test_country_aliases(value):
    assert canonical_country(value) == '新加坡'

def test_no_currency_substring_match():
    assert canonical_country('USD') is None
    assert canonical_country('SGD 20') is None
    assert country_tokens('SG\nMY') == {'新加坡', '马来西亚'}

def test_reordered_country_column():
    headers = ['', '商品', '销量', '店铺', '国家/地区', '品类']
    row = parse_product(headers, ['', 'Cat toy\n售价：S$9', '100', 'PawPals', 'Singapore', '宠物用品'], '', lambda cells: None)
    assert row['product_name'] == 'Cat toy'
    assert row['country'] == 'Singapore'
    assert row['shop'] == 'PawPals'
    assert row['sales_period'] == '100'
    assert row['price'] == 'S$9'

def test_flag_country_evidence_preserved():
    row = parse_product(['商品', '国家', '店铺'], ['Toy', '', 'Shop'], 'SG', lambda c: None)
    assert row['country_raw'] == '' and row['country_evidence'] == 'SG'

def test_unknown_header_not_fixed_index_guessed():
    with pytest.raises(RuntimeError, match='表头无法识别'):
        parse_product(['未识别字段', '销量', '店铺'], ['Toy', '10', 'Shop'], '', lambda c: {'country': '新加坡'})

@pytest.mark.parametrize('raw', ['SG', 'Singapore', '新加坡\nSG'])
def test_collector_accepts_country_alias(raw, tmp_path):
    fake = FakeBridge(pages=[[['Toy', raw]]])
    rows, _ = Collector(fake, SECTIONS).collect(Job(output=str(tmp_path), pages=1), ImmediateEvent())
    assert rows[0]['country'] == '新加坡'
    assert rows[0]['country_raw'] == raw
    assert rows[0]['country_verification'] == 'row_and_page_filter'

def test_blank_country_rejected_in_precise_mode(tmp_path):
    fake = FakeBridge(pages=[[['Toy', '']]])
    with pytest.raises(RuntimeError, match='国家缺少'):
        Collector(fake, SECTIONS).collect(Job(output=str(tmp_path), pages=1), ImmediateEvent())

def test_stale_country_retries_then_recovers(tmp_path):
    class Stale(FakeBridge):
        def __init__(self):
            super().__init__(pages=[[['Toy', '新加坡']]])
            self.calls = 0
        def evaluate(self, js):
            if js == 'extract':
                self.calls += 1
                return {'rows': [['Toy', '泰国' if self.calls == 1 else '新加坡']]}
            return super().evaluate(js)
    fake = Stale()
    rows, _ = Collector(fake, SECTIONS).collect(Job(output=str(tmp_path), pages=1), ImmediateEvent())
    assert fake.calls == 2 and rows[0]['country'] == '新加坡'

@pytest.mark.parametrize('job', [Job(output='out', period='周榜'), Job(output='out', section='shops', category='宠物用品')])
def test_unsupported_upstream_parameters_fail_before_browser(job):
    fake = FakeBridge()
    with pytest.raises(ValueError):
        Collector(fake, SECTIONS).collect(job, ImmediateEvent())
    assert not hasattr(fake, 'url')


def test_collector_header_and_flag_integration(tmp_path):
    cfg = {'products': {**SECTIONS['products'], 'parse_kind': 'fixed'}}
    class HeaderBridge(FakeBridge):
        def evaluate(self, js):
            if js == PRODUCT_EXTRACT_JS:
                return {'headers': ['', '商品', '店铺', '国家/地区', '销量', '品类'],
                        'rows': [['', 'Toy', 'Shop', '', '100', '宠物用品']], 'country_evidence': ['SG'], 'product_metadata': [{'product_url': 'https://www.fastmoss.com/zh/e-commerce/detail/1', 'main_image_url': 'https://example.com/p.png'}]}
            return super().evaluate(js)
    rows, warnings = Collector(HeaderBridge(), cfg).collect(Job(output=str(tmp_path), pages=1), ImmediateEvent())
    assert rows[0]['country'] == '新加坡'
    assert rows[0]['country_raw'] == ''
    assert rows[0]['shop'] == 'Shop'
    assert not warnings
