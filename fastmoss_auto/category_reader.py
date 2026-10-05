"""Read actual category catalogs with an owned BrowserSkill session."""
import json
from datetime import datetime, timezone
from threading import Event
from .bridge import Bridge
from .domain import Cancelled, load_sections
from .schema import canonical_country, taxonomy_paths
from .categories import CATEGORY_TREE_JS, CATEGORY_BRANCH_JS

EXPAND_CATEGORY_JS = r"""(() => {
 const visible = e => e.getClientRects().length;
 const widgets = Array.from(document.querySelectorAll('.ant-cascader,.ant-cascader-picker,[role=combobox]'));
 const category = widgets.find(e => visible(e) && !e.closest('table,nav,aside') &&
   /品类|类目|商品分类/.test((e.closest('.ant-form-item') || e.parentElement).textContent || ''));
 if(category) category.click();
 for(const e of document.querySelectorAll('button,span,a')) {
   if(visible(e) && !e.closest('table,nav,aside') && (e.innerText || e.textContent || '').trim() === '展开') e.click();
 }
 return JSON.stringify({opened:!!category});
})()"""


def catalog_paths(data):
    """Prefer localized UI paths; the vocabulary API can use another locale."""
    ui_paths = {tuple(path) for path in data.get('ui_paths', [])
                if isinstance(path, (list, tuple)) and path}
    ui_paths.update(tuple(path) for tree in data.get('ui_trees', []) for path in taxonomy_paths(tree))
    if ui_paths:
        ui_roots = set(data.get('ui_root_labels', []))
        if ui_roots:
            ui_paths = {path for path in ui_paths if path and path[0] in ui_roots}
        else:
            descendants = {name for path in ui_paths for name in path[1:]}
            ui_paths = {path for path in ui_paths if len(path) > 1 or path[0] not in descendants}
        return [list(path[:3]) for path in sorted(ui_paths)]
    paths = {tuple(path) for tree in data.get('trees', []) for path in taxonomy_paths(tree)}
    roots = set(data.get('root_labels', []))
    if roots:
        paths = {path for path in paths if path and path[0] in roots}
    else:
        # A separately exposed child-options list is not a new root category.
        descendants = {name for path in paths for name in path[1:]}
        paths = {path for path in paths if len(path) > 1 or path[0] not in descendants}
    return [list(path[:3]) for path in sorted(paths)]


def _has_chinese(value):
    return any('\u4e00' <= char <= '\u9fff' for char in str(value))


class CategoryReader:
    def __init__(self, bridge=None, sections=None):
        self.bridge = bridge
        self.sections = sections

    def read(self, country, source, bsk, preferred='宠物用品', wait=5, cancel=None, progress=lambda *args: None):
        from .collector import FILTER_JS, GUARD_JS, SALES_BOARD_JS
        cancel = cancel or Event()
        country = canonical_country(country) or country.strip()
        if not country:
            raise ValueError('请先选择国家')
        sections = self.sections or load_sections(source)
        bridge = self.bridge or Bridge(bsk, cancel)
        def pause():
            if cancel.wait(wait):
                raise Cancelled('类目读取已取消')
        def settle():
            if cancel.wait(min(wait, 1.2)):
                raise Cancelled('类目读取已取消')
        try:
            progress(0, f'连接 BrowserSkill，读取{country}类目')
            bridge.start()
            bridge.navigate(sections['products']['url'])
            pause()
            sales = bridge.evaluate(SALES_BOARD_JS)
            if not sales.get('url'):
                raise RuntimeError('未找到商品销量榜入口，无法读取对应页面的分类')
            bridge.navigate(sales['url'])
            pause()
            guard = bridge.evaluate(GUARD_JS)
            if guard.get('blocked'):
                raise RuntimeError('FastMoss 需要登录或验证，请在已连接的浏览器中处理')
            state = bridge.evaluate(FILTER_JS % (json.dumps(country, ensure_ascii=False), '"click"'))
            if not state.get('found'):
                raise RuntimeError(f'未找到国家筛选：{country}')
            pause()
            state = bridge.evaluate(FILTER_JS % (json.dumps(country, ensure_ascii=False), '"check"'))
            if not state.get('selected'):
                raise RuntimeError(f'无法确认国家筛选：{country}')
            bridge.evaluate(EXPAND_CATEGORY_JS)
            pause()
            progress(15, '读取中文一级类目')
            preferred_root = str(preferred).split('/')[0].strip()
            probe = preferred_root if _has_chinese(preferred_root) else '宠物用品'
            data = bridge.evaluate(CATEGORY_TREE_JS % json.dumps(probe, ensure_ascii=False))
            paths = {tuple(path) for path in catalog_paths(data)}
            # UI roots are localized labels from the current /zh page. Never use the
            # API's English root_labels to drive clicks on the Chinese control.
            roots = [label for label in data.get('ui_root_labels', []) if _has_chinese(label)]
            if not roots:
                roots = sorted({path[0] for path in paths if path and _has_chinese(path[0])})
            if roots:
                for index, root in enumerate(roots):
                    if cancel.is_set():
                        raise Cancelled('类目读取已取消')
                    progress(15 + int((index + 1) / len(roots) * 70),
                             f'读取中文类目 {index + 1}/{len(roots)}：{root}')
                    branch = bridge.evaluate(CATEGORY_BRANCH_JS % json.dumps(root, ensure_ascii=False))
                    for path in branch.get('paths', []):
                        if isinstance(path, list) and path and all(isinstance(part, str) and part.strip() for part in path):
                            paths.add(tuple(path[:3]))
                    # Some FastMoss revisions render inline tags instead of an Ant
                    # cascader. Fall back to the same exact-label click used by the
                    # collector, then rescan component props after each lazy level.
                    root_paths = {path for path in paths if path[:1] == (root,)}
                    if not branch.get('found') or max((len(path) for path in root_paths), default=1) < 3:
                        state = bridge.evaluate(FILTER_JS % (json.dumps(root, ensure_ascii=False), '"click"'))
                        if state.get('found'):
                            settle()
                            snapshot = bridge.evaluate(CATEGORY_TREE_JS % json.dumps(root, ensure_ascii=False))
                            discovered = {tuple(path[:3]) for path in catalog_paths(snapshot) if path and path[0] == root}
                            paths.update(discovered)
                            seconds = sorted({path[1] for path in discovered if len(path) > 1})
                            for second in seconds:
                                state = bridge.evaluate(FILTER_JS % (json.dumps(second, ensure_ascii=False), '"click"'))
                                if not state.get('found'):
                                    continue
                                settle()
                                snapshot = bridge.evaluate(CATEGORY_TREE_JS % json.dumps(second, ensure_ascii=False))
                                paths.update(tuple(path[:3]) for path in catalog_paths(snapshot)
                                             if path and path[0] == root)
            paths = [list(path) for path in sorted(paths)]
            if not paths:
                raise RuntimeError('页面未返回可识别类目；请展开分类控件、检查账号权限后重试。原缓存不会被覆盖。')
            if not any(_has_chinese(part) for path in paths for part in path):
                raise RuntimeError('只读取到英文API词表，未读取到中文页面类目。请确认FastMoss已切换中文页面后重试；原缓存不会被覆盖。')
            if cancel.is_set():
                raise Cancelled('类目读取已取消')
            warnings = []
            depth = max(map(len, paths))
            if depth < 3:
                level = '一级类目' if depth == 1 else '二级类目'
                warnings.append(f'当前账号页面最深只返回{level}；已保存页面真实返回内容，未补造下级。')
            return {'schema_version': 2, 'country': country, 'source_url': sales['url'],
                    'read_at': datetime.now(timezone.utc).isoformat(), 'paths': paths, 'warnings': warnings}
        finally:
            try:
                bridge.close()
            except Exception as exc:
                progress(90, f'清理类目读取会话失败：{exc}')
