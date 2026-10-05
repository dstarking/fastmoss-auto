"""Read the localized FastMoss category hierarchy from the logged-in page."""

# Snapshot both the visible (localized) category control and component props. The
# market API is a fallback, but stays separate because it may return English labels
# while the /zh page renders Chinese labels.
CATEGORY_TREE_JS = r"""
(async (selected) => {
 const uiTrees = [], apiTrees = [], uiPaths = [], seenUi = new Set(), seenApi = new Set();
 const keys = ['category','categories','categoryList','category_list','categoryTree','category_tree','treeData'];
 const visible = e => !!(e && e.getClientRects().length);
 const labelOf = e => {
   const node = e && (e.querySelector('.ant-cascader-menu-item-content,[class*=label],[class*=title]') || e);
   return ((node && (node.innerText || node.textContent)) || (e && e.getAttribute('title')) || '')
     .replace(/\s+/g, ' ').trim();
 };
 const usable = value => value && !/^(全部|all|请选择|加载中)/i.test(value);
 const clean = (items, depth=0) => {
   if (!Array.isArray(items) || depth > 12) return [];
   return items.slice(0,10000).filter(n => n && typeof n === 'object').map(n => {
     const out = {};
     for (const key of ['c_name','category_name','label','name','title','c_code','category_id','id','value','key',
                        'parent_id','parentId','parent_code','c_parent_code','p_code','pid']) {
       if (['string','number'].includes(typeof n[key])) out[key] = n[key];
     }
     for (const key of ['children','child','sub_categories','categories','options']) {
       if (Array.isArray(n[key])) out[key === 'options' ? 'children' : key] = clean(n[key], depth+1);
     }
     return out;
   });
 };
 const inspect = (props, target, seen, options=false) => {
   if (!props || typeof props !== 'object') return;
   for (const key of [...keys, ...(options ? ['options'] : [])]) {
     if (Array.isArray(props[key])) {
       const tree = clean(props[key]);
       const signature = JSON.stringify(tree);
       if(tree.length && !seen.has(signature)) { seen.add(signature); target.push(tree); }
     }
   }
 };
 const categoryNodes = Array.from(document.querySelectorAll(
   '.ant-cascader,.ant-cascader-picker,.ant-cascader-menus,[role=tree],[role=listbox],[data-category-tree],input,[role=combobox],span,button'))
   .filter(e => !e.closest('table,nav,aside') && (visible(e) || e.matches('input,[role=combobox]')));
 for (const node of categoryNodes) {
   const context = node.closest('.ant-form-item,[class*=filter],[class*=search]') || node.parentElement;
   if (!node.matches('.ant-cascader-menus,[data-category-tree],[role=tree]') &&
       !/品类|类目|商品分类|category/i.test((context && context.textContent) || node.getAttribute('placeholder') || '') &&
       !(selected && labelOf(node) === selected)) continue;
   for(let el=node, depth=0; el && depth<7; el=el.parentElement, depth++) {
     const propKey = Object.keys(el).find(k => k.startsWith('__reactProps$'));
     if(propKey) inspect(el[propKey], uiTrees, seenUi, true);
     const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
     if(fiberKey) for(let f=el[fiberKey], d=0; f && d<20; f=f.return, d++) {
       inspect(f.memoizedProps, uiTrees, seenUi, true); inspect(f.pendingProps, uiTrees, seenUi, true);
     }
   }
 }
 const menus = Array.from(document.querySelectorAll('.ant-cascader-menu,[role=menu]'))
   .filter(e => visible(e) && !e.closest('table,nav,aside') &&
     (e.matches('.ant-cascader-menu') || !!e.closest('.ant-cascader-menus,.ant-cascader-dropdown,[class*=cascader]')));
 const activeLabel = menu => {
   const item = menu && menu.querySelector('.ant-cascader-menu-item-active,.ant-cascader-menu-item-selected,[aria-expanded=true],[aria-selected=true]');
   const label = labelOf(item);
   return usable(label) ? label : '';
 };
 for (let level=0; level<Math.min(3, menus.length); level++) {
   const labels = Array.from(menus[level].querySelectorAll('.ant-cascader-menu-item,[role=menuitem],li'))
     .filter(visible).map(labelOf).filter(usable);
   const prefix = [];
   for (let p=0; p<level; p++) {
     const value = activeLabel(menus[p]);
     if (!value) break;
     prefix.push(value);
   }
   if (prefix.length === level) for (const value of labels) uiPaths.push([...prefix, value]);
 }
 let apiStatus = null, rootLabels = [];
 const controller = new AbortController();
 const timer = setTimeout(() => controller.abort(), 8000);
 try {
   const now = Date.now();
   const response = await fetch('/api/analysis/GoodCategory/filterInfo?_time=' + Math.floor(now/1000) + '&cnonce=' + (now %% 100000000),
     {credentials:'include', signal:controller.signal});
   apiStatus = response.status;
   if(response.ok) {
     const data = await response.json();
     const payload = (data.data && data.data.data) || data.data || data;
     inspect(payload, apiTrees, seenApi);
     if(Array.isArray(payload.category)) rootLabels = clean(payload.category).map(n => n.c_name || n.category_name || n.label || n.name || n.title).filter(Boolean);
   }
 } catch(e) { apiStatus = 'unavailable'; }
 finally { clearTimeout(timer); }
 const uiRootLabels = [...new Set(uiPaths.filter(p => p.length === 1).map(p => p[0]))];
 return JSON.stringify({trees:[...uiTrees,...apiTrees], ui_trees:uiTrees, api_trees:apiTrees,
   ui_paths:uiPaths, ui_root_labels:uiRootLabels, root_labels:rootLabels,
   api_status:apiStatus, selected:selected || ''});
})(%s)
"""


# Crawl one root per BrowserSkill call. This keeps calls bounded while loading
# lazy Ant Design cascader branches through level three.
CATEGORY_BRANCH_JS = r"""
(async (wantedRoot) => {
 const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
 const visible = e => !!(e && e.getClientRects().length);
 const labelOf = e => {
   const node = e && (e.querySelector('.ant-cascader-menu-item-content,[class*=label],[class*=title]') || e);
   return ((node && (node.innerText || node.textContent)) || (e && e.getAttribute('title')) || '')
     .replace(/\s+/g, ' ').trim();
 };
 const usable = value => value && !/^(全部|all|请选择|加载中)/i.test(value);
 const menus = () => Array.from(document.querySelectorAll('.ant-cascader-menu,[role=menu]'))
   .filter(e => visible(e) && !e.closest('table,nav,aside') &&
     (e.matches('.ant-cascader-menu') || !!e.closest('.ant-cascader-menus,.ant-cascader-dropdown,[class*=cascader]')));
 const items = menu => menu ? Array.from(menu.querySelectorAll('.ant-cascader-menu-item,[role=menuitem],li')).filter(visible) : [];
 const findItem = (menu, label) => items(menu).find(e => labelOf(e) === label);
 const open = async () => {
   if (menus().length) return true;
   const candidates = Array.from(document.querySelectorAll('.ant-form-item,[class*=filter],[class*=search],label'))
     .filter(e => visible(e) && /品类|类目|商品分类|category/i.test(e.textContent || ''));
   let control = null;
   for (const box of candidates) {
     control = box.querySelector('.ant-cascader,.ant-cascader-picker,[role=combobox],input');
     if (control && !control.closest('table,nav,aside')) break;
     control = null;
   }
   control = control || Array.from(document.querySelectorAll('.ant-cascader,.ant-cascader-picker,[role=combobox],input'))
     .find(e => visible(e) && !e.closest('table,nav,aside') && /品类|类目|category/i.test(e.getAttribute('placeholder') || ''));
   if (!control) return false;
   (control.closest('.ant-cascader,.ant-cascader-picker') || control).click();
   await sleep(120);
   return !!menus().length;
 };
 const activate = async item => {
   item.dispatchEvent(new MouseEvent('mouseover', {bubbles:true}));
   item.dispatchEvent(new MouseEvent('mousemove', {bubbles:true}));
   item.click();
   await sleep(140);
 };
 const selectRoot = async () => {
   if (!await open()) return false;
   const root = findItem(menus()[0], wantedRoot);
   if (!root) return false;
   await activate(root);
   return true;
 };
 const paths = [[wantedRoot]];
 if (!await selectRoot()) return JSON.stringify({found:false, paths:[], root:wantedRoot});
 const secondLabels = [...new Set(items(menus()[1]).map(labelOf).filter(usable))];
 for (const second of secondLabels.slice(0,500)) {
   let item = findItem(menus()[1], second);
   if (!item) {
     if (!await selectRoot()) continue;
     item = findItem(menus()[1], second);
   }
   if (!item) continue;
   paths.push([wantedRoot, second]);
   await activate(item);
   const thirdLabels = [...new Set(items(menus()[2]).map(labelOf).filter(usable))];
   for (const third of thirdLabels.slice(0,1000)) paths.push([wantedRoot, second, third]);
 }
 return JSON.stringify({found:true, paths, root:wantedRoot, second_count:secondLabels.length});
})(%s)
"""


DETAIL_CATEGORY_JS = r"""
(() => {
 const paths = [];
 for (const el of document.querySelectorAll('[class*="category"],[class*="Category"],[class*="breadcrumb"],[itemprop="category"],[data-category-path]')) {
   if(el.closest('nav,aside,footer') || !el.getClientRects().length) continue;
   for(const value of [el.getAttribute('data-category-path'),el.getAttribute('title'),el.innerText || el.textContent]) {
     if(value && value.trim().length < 250) paths.push(value.trim());
   }
 }
 return JSON.stringify({url:location.href, paths:[...new Set(paths)]});
})()
"""
