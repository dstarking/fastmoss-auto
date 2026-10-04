"""Read source category vocabularies in the user's logged-in browser."""

CATEGORY_TREE_JS = r"""
(async (selected) => {
 const trees = [];
 const seen = new Set();
 const keys = ['category','categories','categoryList','category_list','categoryTree','category_tree','treeData'];
 const clean = (items, depth=0) => {
   if (!Array.isArray(items) || depth > 12) return [];
   return items.slice(0,10000).filter(n => n && typeof n === 'object').map(n => {
     const out = {};
     for (const key of ['c_name','category_name','label','name','title','c_code','category_id','id','value','key',
                        'parent_id','parentId','parent_code','c_parent_code','p_code','pid']) {
       if (['string','number'].includes(typeof n[key])) out[key] = n[key];
     }
     for (const key of ['children','child','sub_categories','categories']) {
       if (Array.isArray(n[key])) out[key] = clean(n[key], depth+1);
     }
     return out;
   });
 };
 const inspect = (props, options=false) => {
   if (!props || typeof props !== 'object') return;
   for (const key of [...keys, ...(options ? ['options'] : [])]) {
     if (Array.isArray(props[key])) {
       const tree = clean(props[key]);
       const signature = JSON.stringify(tree);
       if(tree.length && !seen.has(signature)) { seen.add(signature); trees.push(tree); }
     }
   }
 };
 const nodes = Array.from(document.querySelectorAll('[role=tree],.ant-cascader,.ant-cascader-menus,.ant-select-tree,[data-category-tree],span,button'))
   .filter(e => !e.closest('table,nav,aside') && (e.matches('[role=tree],.ant-cascader,.ant-cascader-menus,.ant-select-tree,[data-category-tree]') ||
     (e.innerText || e.textContent || '').trim() === selected));
 for (const node of nodes) {
   for(let el=node, depth=0; el && depth<6; el=el.parentElement, depth++) {
     const propKey = Object.keys(el).find(k => k.startsWith('__reactProps$'));
     if(propKey) inspect(el[propKey], true);
     const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
     if(fiberKey) for(let f=el[fiberKey], d=0; f && d<16; f=f.return, d++) {
       inspect(f.memoizedProps, true); inspect(f.pendingProps, true);
     }
   }
 }
 // Endpoint verified against upstream scripts/market_api.py. Read-only, same origin.
 let apiStatus = null;
 const controller = new AbortController();
 const timer = setTimeout(() => controller.abort(), 8000);
 try {
   const now = Date.now();
   const response = await fetch('/api/analysis/GoodCategory/filterInfo?_time=' + Math.floor(now/1000) + '&cnonce=' + (now %% 100000000),
     {credentials:'include', signal:controller.signal});
   apiStatus = response.status;
   if(response.ok) {
     const data = await response.json();
     inspect(data.data || data);
   }
 } catch(e) { apiStatus = 'unavailable'; }
 finally { clearTimeout(timer); }
 return JSON.stringify({trees, api_status:apiStatus});
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
