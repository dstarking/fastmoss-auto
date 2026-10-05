import json
from dataclasses import replace
import pytest
from fastmoss_auto.categories import CATEGORY_TREE_JS, DETAIL_CATEGORY_JS
from fastmoss_auto.schema import resolve_category, taxonomy_paths
from fastmoss_auto.domain import Job
from fastmoss_auto.collector import Collector
from test_core import FakeBridge, ImmediateEvent, SECTIONS

LEAF = '猫砂盆、猫厕所'
TREE = [{'c_code': '1', 'c_name': '宠物用品', 'children': [
    {'c_code': '2', 'c_name': '猫用品', 'children': [{'c_code': '3', 'c_name': LEAF}]}]}]


def test_leaf_resolves_through_nested_taxonomy():
    assert resolve_category('宠物用品', LEAF, trees=[TREE]) == f'宠物用品 / 猫用品 / {LEAF}'
    assert resolve_category('宠物用品 / 猫用品', LEAF, trees=[TREE])
    assert not resolve_category('宠物用品 / 狗用品', LEAF, trees=[TREE])


def test_flat_parent_ids_and_cycles():
    flat = [{'id': 3, 'name': LEAF, 'parent_id': 2}, {'id': 1, 'name': '宠物用品', 'parent_id': 0},
            {'id': 2, 'name': '猫用品', 'parent_id': 1}]
    assert resolve_category('宠物用品', LEAF, trees=[flat])
    assert not taxonomy_paths([{'id': 1, 'name': 'A', 'parent_id': 2}, {'id': 2, 'name': 'B', 'parent_id': 1}])


def test_unproven_leaf_is_not_inferred_from_keywords():
    assert not resolve_category('宠物用品', LEAF)
    assert not resolve_category('宠物用品', LEAF, trees=[[{'name': '宠物用品'}]])
    assert not resolve_category('宠物用品', LEAF, paths=['猫砂盆、猫厕所玩具 / 宠物用品'])
    assert not resolve_category('宠物用品', '美妆', paths=['宠物用品 / 猫玩具'])


def test_ambiguous_leaf_rejected_and_detail_can_disambiguate():
    trees = [TREE, [{'name': '居家日用', 'children': [{'name': LEAF}]}]]
    assert not resolve_category('宠物用品', LEAF, trees=trees)
    assert resolve_category('宠物用品', LEAF, paths=[f'宠物用品 / 猫用品 / {LEAF}'])
    assert not resolve_category('宠物用品', LEAF, paths=[f'居家日用 / {LEAF}'])


def test_full_wrong_path_cannot_be_overridden():
    assert not resolve_category('宠物用品', f'居家日用 / {LEAF}', trees=[TREE])


def config():
    return {'products': {**SECTIONS['products'], 'parse_row': lambda c: {
        'product_name': c[0], 'country': c[1], 'category': LEAF}}}


def test_collector_leaf_category_does_not_retry_when_hierarchy_proves_it(tmp_path):
    class CategoryBridge(FakeBridge):
        extraction_calls = 0
        hierarchy_calls = 0
        def evaluate(self, js):
            if js == 'extract': self.extraction_calls += 1
            if js == CATEGORY_TREE_JS % json.dumps('宠物用品', ensure_ascii=False):
                self.hierarchy_calls += 1
                return {'trees': [TREE]}
            return super().evaluate(js)
    bridge = CategoryBridge()
    rows, warnings = Collector(bridge, config()).collect(Job(output=str(tmp_path), pages=2), ImmediateEvent())
    assert bridge.extraction_calls == 2 and bridge.hierarchy_calls == 1
    assert len(rows) == 2 and not warnings
    assert all(r['category_raw'] == LEAF and r['category'] == LEAF for r in rows)
    assert all(r['category_path'] == f'宠物用品 / 猫用品 / {LEAF}' for r in rows)
    assert all(r['category_verification'] == 'source_hierarchy_and_page_filter' for r in rows)


def test_collector_uses_country_category_cache_for_leaf_rows(tmp_path):
    class CachedHierarchyBridge(FakeBridge):
        def evaluate(self, js):
            if 'root_labels:rootLabels' in js:
                raise AssertionError('cached hierarchy should avoid rereading the collapsed page control')
            return super().evaluate(js)
    bridge = CachedHierarchyBridge()
    job = Job(output=str(tmp_path), pages=1,
              category_catalog=(('宠物用品', '猫用品', LEAF),))
    rows, warnings = Collector(bridge, config()).collect(job, ImmediateEvent())
    assert len(rows) == 1 and not warnings
    assert rows[0]['category_path'] == f'宠物用品 / 猫用品 / {LEAF}'
    assert rows[0]['category_verification'] == 'source_hierarchy_and_page_filter'


def test_wrong_cached_parent_does_not_authorize_leaf(tmp_path):
    job = Job(output=str(tmp_path), pages=1,
              category_catalog=(('居家日用', '收纳', LEAF),))
    with pytest.raises(RuntimeError, match='类目不一致'):
        Collector(FakeBridge(), config()).collect(job, ImmediateEvent())


def test_detail_fallback_preserves_board_and_cleans_session(tmp_path):
    class Detail(FakeBridge):
        starts = 0
        reads = 0
        def start(self): self.starts += 1
        def evaluate(self, js):
            assert js == DETAIL_CATEGORY_JS
            self.reads += 1
            return {'url': self.url, 'paths': [f'宠物用品 / 猫用品 / {LEAF}']}
    detail = Detail()
    board = FakeBridge()
    rows, _ = Collector(board, config(), lambda: detail).collect(Job(output=str(tmp_path), pages=2), ImmediateEvent())
    assert len(rows) == 2 and detail.starts == 1 and detail.reads == 2
    assert board.url.endswith('verified-sales-board')
    assert detail.closed and board.closed


def test_wrong_detail_category_and_redirect_blocked(tmp_path):
    class Detail(FakeBridge):
        def evaluate(self, js): return {'url': self.url, 'paths': [f'美妆 / {LEAF}']}
    detail = Detail()
    with pytest.raises(RuntimeError, match='类目不一致'):
        Collector(FakeBridge(), config(), lambda: detail).collect(Job(output=str(tmp_path), pages=1), ImmediateEvent())
    assert detail.closed
    class Redirect(Detail):
        def evaluate(self, js): return {'url': 'https://www.fastmoss.com/zh/login', 'paths': [f'宠物用品 / {LEAF}']}
    redirected = Redirect()
    with pytest.raises(RuntimeError, match='详情发生跳转'):
        Collector(FakeBridge(), config(), lambda: redirected).collect(Job(output=str(tmp_path), pages=1), ImmediateEvent())
    assert redirected.closed


def test_detail_loading_evidence_retries_instead_of_caching_empty(tmp_path):
    class Detail(FakeBridge):
        calls = 0
        def evaluate(self, js):
            self.calls += 1
            return {'url': self.url, 'paths': [] if self.calls == 1 else [f'宠物用品 / 猫用品 / {LEAF}']}
    detail = Detail()
    rows, _ = Collector(FakeBridge(), config(), lambda: detail).collect(Job(output=str(tmp_path), pages=1), ImmediateEvent())
    assert len(rows) == 1 and detail.calls == 2 and detail.closed
