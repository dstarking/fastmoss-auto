"""Read actual category catalogs with an owned BrowserSkill session."""
import json
from datetime import datetime, timezone
from threading import Event
from .bridge import Bridge
from .domain import Cancelled, load_sections
from .schema import canonical_country, category_path, taxonomy_paths
from .categories import CATEGORY_TREE_JS

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
    paths = {tuple(path) for tree in data.get('trees', []) for path in taxonomy_paths(tree)}
    roots = set(data.get('root_labels', []))
    if roots:
        paths = {path for path in paths if path and path[0] in roots}
    else:
        # A separately exposed child-options list is not a new root category.
        descendants = {name for path in paths for name in path[1:]}
        paths = {path for path in paths if len(path) > 1 or path[0] not in descendants}
    return [list(path) for path in sorted(paths)]


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
            # Selecting a real visible parent can load lazy child options. A missing
            # preference is harmless; the catalog never invents that category.
            labels = [label.strip() for label in str(preferred).split('/') if label.strip()]
            for label in labels:
                state = bridge.evaluate(FILTER_JS % (json.dumps(label, ensure_ascii=False), '"click"'))
                if not state.get('found'):
                    break
                pause()
            progress(60, '读取页面类目树和类目词典')
            data = bridge.evaluate(CATEGORY_TREE_JS % json.dumps(labels[0] if labels else '', ensure_ascii=False))
            paths = catalog_paths(data)
            if not paths:
                raise RuntimeError('页面未返回可识别类目；请展开分类控件、检查账号权限后重试。原缓存不会被覆盖。')
            if cancel.is_set():
                raise Cancelled('类目读取已取消')
            warnings = []
            if max(map(len, paths)) == 1:
                warnings.append('当前页面只提供一级类目，可直接选择父类目采集；选择父类后再次点击读取类目可尝试加载下级。未返回的层级不会补造。')
            return {'schema_version': 1, 'country': country, 'source_url': sales['url'],
                    'read_at': datetime.now(timezone.utc).isoformat(), 'paths': paths, 'warnings': warnings}
        finally:
            try:
                bridge.close()
            except Exception as exc:
                progress(90, f'清理类目读取会话失败：{exc}')
