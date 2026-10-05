import json
import pytest
from fastmoss_auto.category_reader import CategoryReader, catalog_paths
from fastmoss_auto.categories import CATEGORY_TREE_JS
from fastmoss_auto.domain import Cancelled
from test_core import FakeBridge, ImmediateEvent, SECTIONS

TREE = [{'label':'宠物用品','value':1,'children':[{'label':'猫用品','value':2,'children':[{'label':'猫砂盆、猫厕所','value':3}]}]}, {'label':'美妆','value':4}]


class ReaderBridge(FakeBridge):
    def __init__(self, data=None, **kwargs):
        super().__init__(**kwargs)
        self.data = data if data is not None else {'trees':[TREE], 'root_labels':['宠物用品','美妆']}
    def evaluate(self, js):
        if 'root_labels:rootLabels' in js: return self.data
        return super().evaluate(js)


def test_reader_real_paths_country_and_cleanup():
    bridge = ReaderBridge()
    result = CategoryReader(bridge, SECTIONS).read('SG', '', 'bsk', cancel=ImmediateEvent())
    assert result['country'] == '新加坡'
    assert ['宠物用品','猫用品','猫砂盆、猫厕所'] in result['paths']
    assert ['美妆'] in result['paths'] and not result['warnings']
    assert bridge.closed and result['source_url'].endswith('verified-sales-board')
    assert result['schema_version'] == 2
    assert '新加坡' in ''.join(bridge.filters)


def test_one_level_catalog_is_valid_and_reported():
    bridge = ReaderBridge({'trees':[[{'c_name':'宠物用品','c_code':1}]], 'root_labels':['宠物用品']})
    result = CategoryReader(bridge, SECTIONS).read('新加坡', '', 'bsk', cancel=ImmediateEvent())
    assert result['paths'] == [['宠物用品']]
    assert '一级类目' in result['warnings'][0]


def test_children_do_not_become_false_roots():
    data = {'trees':[TREE, [{'label':'猫砂盆、猫厕所','value':3}]]}
    assert ['猫砂盆、猫厕所'] not in catalog_paths(data)
    assert ['宠物用品','猫用品','猫砂盆、猫厕所'] in catalog_paths(data)
    data['root_labels'] = ['宠物用品']
    assert ['美妆'] not in catalog_paths(data)


def test_localized_ui_catalog_wins_over_english_api_vocabulary():
    data = {
        'ui_paths': [['宠物用品'], ['宠物用品', '猫用品', '猫砂盆、猫厕所']],
        'ui_trees': [],
        'trees': [[{'label': 'Pet Supplies'}, {'label': 'Beauty'}]],
        'root_labels': ['Pet Supplies', 'Beauty'],
    }
    assert catalog_paths(data) == [['宠物用品'], ['宠物用品', '猫用品', '猫砂盆、猫厕所']]


def test_reader_crawls_every_localized_root_in_one_operation():
    class CrawlingBridge(ReaderBridge):
        def __init__(self):
            super().__init__({'ui_paths': [['宠物用品'], ['美妆个护']],
                              'ui_root_labels': ['宠物用品', '美妆个护'],
                              'ui_trees': [], 'trees': [], 'root_labels': ['Pet Supplies', 'Beauty']})
            self.roots = []
        def evaluate(self, js):
            if 'wantedRoot' in js:
                root = '宠物用品' if '宠物用品' in js else '美妆个护'
                self.roots.append(root)
                return {'found': True, 'paths': [[root], [root, root + '二级'], [root, root + '二级', root + '三级']]}
            return super().evaluate(js)
    bridge = CrawlingBridge()
    result = CategoryReader(bridge, SECTIONS).read('新加坡', '', 'bsk', cancel=ImmediateEvent())
    assert bridge.roots == ['宠物用品', '美妆个护']
    assert ['宠物用品', '宠物用品二级', '宠物用品三级'] in result['paths']
    assert ['美妆个护', '美妆个护二级', '美妆个护三级'] in result['paths']


@pytest.mark.parametrize('failure',['login','missing','unselected'])
def test_reader_failed_filters_cleanup(failure):
    bridge = ReaderBridge(failure=failure)
    with pytest.raises(RuntimeError):
        CategoryReader(bridge, SECTIONS).read('新加坡', '', 'bsk', cancel=ImmediateEvent())
    assert bridge.closed


def test_empty_tree_and_cancel_are_not_successes():
    bridge = ReaderBridge({'trees':[]})
    with pytest.raises(RuntimeError, match='原缓存不会被覆盖'):
        CategoryReader(bridge, SECTIONS).read('新加坡', '', 'bsk', cancel=ImmediateEvent())
    assert bridge.closed
    stopped = ReaderBridge()
    with pytest.raises(Cancelled):
        CategoryReader(stopped, SECTIONS).read('新加坡', '', 'bsk', cancel=ImmediateEvent(True))
    assert stopped.closed
