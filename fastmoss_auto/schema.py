"""Header-driven product schema and exact country aliases, independent of UI locale."""
import re

COUNTRY_ALIASES = {
    '新加坡': ('SG', 'SGP', 'Singapore', '🇸🇬'),
    '马来西亚': ('MY', 'MYS', 'Malaysia', '🇲🇾'),
    '泰国': ('TH', 'THA', 'Thailand', '🇹🇭'),
    '越南': ('VN', 'VNM', 'Vietnam', 'Viet Nam', '🇻🇳'),
    '菲律宾': ('PH', 'PHL', 'Philippines', '🇵🇭'),
    '印度尼西亚': ('ID', 'IDN', 'Indonesia', '印尼', '🇮🇩'),
    '美国': ('US', 'USA', 'United States', 'United States of America', '🇺🇸'),
    '英国': ('GB', 'GBR', 'UK', 'United Kingdom', '🇬🇧'),
    '日本': ('JP', 'JPN', 'Japan', '🇯🇵'),
    '德国': ('DE', 'DEU', 'Germany', '🇩🇪'),
    '法国': ('FR', 'FRA', 'France', '🇫🇷'),
    '意大利': ('IT', 'ITA', 'Italy', '🇮🇹'),
    '西班牙': ('ES', 'ESP', 'Spain', '🇪🇸'),
    '墨西哥': ('MX', 'MEX', 'Mexico', '🇲🇽'),
    '巴西': ('BR', 'BRA', 'Brazil', '🇧🇷'),
}


def country_tokens(value):
    text = str(value or '').strip()
    if not text:
        return set()
    parts = {text.casefold(), re.sub(r'\s+', ' ', text).casefold()}
    parts.update(p.strip().casefold() for p in re.split(r'[\n/|,;()（）]+', text) if p.strip())
    # Allow country plus code in a single cell, but never substring-match US in USD.
    for token in re.findall(r'(?<![A-Za-z])[A-Z]{2,3}(?![A-Za-z])', text):
        parts.add(token.casefold())
    for aliases in COUNTRY_ALIASES.values():
        for alias in aliases:
            if len(alias) > 3 and re.search(r'(?<![A-Za-z])' + re.escape(alias) + r'(?![A-Za-z])', text, re.I):
                parts.add(alias.casefold())
    return {country for country, aliases in COUNTRY_ALIASES.items()
            if parts.intersection({country.casefold(), *(alias.casefold() for alias in aliases)})}


def canonical_country(value):
    found = country_tokens(value)
    return next(iter(found)) if len(found) == 1 else None


def category_path(value):
    """Compare complete hierarchy segments, never title substrings."""
    return [re.sub(r'\s+', '', part).casefold() for part in
            re.split(r'\s*(?:/|>|›|→|\n|\\|－|-)\s*', str(value or '').strip()) if part.strip()]


def category_matches(selected, actual):
    wanted, observed = category_path(selected), category_path(actual)
    return bool(wanted and observed and observed[:len(wanted)] == wanted)


def taxonomy_paths(nodes):
    """Normalize nested and parent-ID category vocabularies; never infer by keywords."""
    if not isinstance(nodes, list):
        return []
    records = []
    def visit(items, ancestors=()):
        for node in items:
            if not isinstance(node, dict):
                continue
            label = next((str(node[k]).strip() for k in ('c_name', 'category_name', 'label', 'name', 'title')
                          if node.get(k) is not None and str(node[k]).strip()), '')
            identity = next((str(node[k]) for k in ('c_code', 'category_id', 'id', 'value', 'key') if node.get(k) is not None), '')
            parent = next((str(node[k]) for k in ('parent_id', 'parentId', 'parent_code', 'c_parent_code', 'p_code', 'pid')
                           if node.get(k) is not None), '')
            path = (*ancestors, label) if label else ancestors
            if label:
                records.append((identity, parent, path))
            for key in ('children', 'child', 'sub_categories', 'categories'):
                if isinstance(node.get(key), list):
                    visit(node[key], path)
    visit(nodes)
    by_id = {}
    for identity, parent, path in records:
        if identity:
            by_id.setdefault(identity, []).append((parent, path))
    def expand(parent, path, visited):
        if len(path) > 1 or not parent or parent in ('0', '-1'):
            return [path]
        if parent in visited or len(by_id.get(parent, [])) != 1:
            return []
        pp, prefix = by_id[parent][0]
        return [(*ancestor, *path) for ancestor in expand(pp, prefix, visited | {parent})]
    return list(dict.fromkeys(expanded for _, parent, path in records
                             for expanded in expand(parent, path, set())))


def resolve_category(selected, actual, paths=(), trees=()):
    """A leaf alone is acceptable only with an unambiguous source hierarchy."""
    raw = category_path(actual)
    if category_matches(selected, actual):
        return str(actual).strip()
    if not raw or len(raw) > 1:
        return None
    candidates = {tuple(category_path(path)) for path in paths if isinstance(path, str)}
    for tree in trees:
        candidates.update(tuple(category_path(' / '.join(path))) for path in taxonomy_paths(tree))
    candidates = {path for path in candidates if len(path) > 1 and path[-1:] == tuple(raw)}
    # Ambiguous labels under different parents are not proof of membership.
    if len(candidates) != 1:
        return None
    full = next(iter(candidates))
    return ' / '.join(full) if category_matches(selected, ' / '.join(full)) else None


def parse_product(headers, cells, evidence, fallback):
    """Use names instead of column positions when a product header exists."""
    names = [re.sub(r'\s+', '', h).casefold() for h in headers]
    aliases = {
        'rank': ('排名', '序号', 'rank'),
        'product_name': ('商品', '商品信息', '商品名称', '商品标题', '产品', 'product', 'productinfo', 'productname'),
        'country': ('国家', '国家/地区', '国家地区', '所属国家', 'country', 'country/region'),
        'shop': ('店铺', '所属店铺', '关联店铺', '店铺信息', 'shop', 'shopinfo'),
        'category': ('品类', '商品品类', '商品分类', '类目', '商品类目', '所属类目', 'category'),
        'commission': ('佣金', '佣金比例', '佣金率', 'commission'),
        'sales_period': ('销量', '周期销量', '商品销量', 'sales', '近7天销量', '近28天销量', '近30天销量', '昨日销量'),
        'gmv_period': ('销售额', '周期销售额', 'gmv', '近7天销售额', '近30天销售额'),
        'total_sales': ('总销量', '累计销量', 'totalsales'),
        'total_gmv': ('总销售额', '累计销售额', 'totalgmv'),
        'price': ('售价', '价格', 'price'),
        'listed_at': ('上架时间', '上架日期', 'listedat'),
    }
    indexes = {field: next((i for i, name in enumerate(names) if name in labels), None)
               for field, labels in aliases.items()}
    if headers and indexes['product_name'] is None:
        raise RuntimeError(f"商品表头无法识别，不能继续按固定列解析：{headers}")
    if not headers:
        row = fallback(cells)
        if row:
            row['country_raw'] = row.get('country', '')
            row['country_evidence'] = evidence
        return row
    row = {field: cells[i].strip() if i is not None and i < len(cells) else ''
           for field, i in indexes.items()}
    if not row['product_name']:
        return None
    raw_product = row['product_name']
    raw_shop = row['shop']
    row['product_name'] = raw_product.splitlines()[0].strip()
    row['shop'] = raw_shop.splitlines()[0].strip() if raw_shop else ''
    # Preserve source columns as well as normalized fields.
    for i, header in enumerate(headers):
        if header.strip() and i < len(cells):
            row['raw_' + header.replace('\n', ' ').strip()] = cells[i]
    for line in raw_product.splitlines()[1:]:
        if '售价' in line and not row['price']:
            row['price'] = re.split('[：:]', line)[-1].strip()
        if '上架' in line and not row['listed_at']:
            row['listed_at'] = re.split('[：:]', line)[-1].strip()
    row['country_raw'] = row['country']
    row['country_evidence'] = evidence
    row['sales_metric'] = headers[indexes['sales_period']] if indexes['sales_period'] is not None else ''
    return row


PRODUCT_EXTRACT_JS = r"""
(() => {
 const tables = Array.from(document.querySelectorAll('table'));
 const readHeaders = table => {
   const grid = [];
   Array.from(table.tHead ? table.tHead.rows : []).forEach((row, ri) => {
     grid[ri] = grid[ri] || [];
     let ci = 0;
     for(const cell of Array.from(row.cells)) {
       while(grid[ri][ci] !== undefined) ci++;
       const text = (cell.innerText || cell.textContent || cell.title || '').trim();
       for(let r=ri; r<ri+cell.rowSpan; r++) {
         grid[r] = grid[r] || [];
         for(let c=ci; c<ci+cell.colSpan; c++) grid[r][c] = text;
       }
       ci += cell.colSpan;
     }
   });
   const width = Math.max(0, ...grid.map(r => r.length));
   return Array.from({length:width}, (_,i) => [...grid].reverse().map(r => r[i]).find(v => v !== undefined) || '');
 };
 const candidates = tables.map(table => {
   const rs = Array.from(table.tBodies).flatMap(body => Array.from(body.rows)).filter(r => r.cells.length >= 5);
   const headers = readHeaders(table);
   const cols = Math.max(0, ...rs.map(r => r.cells.length));
   return {table, rs, headers, score: cols * 100000 + rs.length * 10 + headers.length};
 }).filter(c => c.rs.length);
 candidates.sort((a,b) => b.score - a.score);
 const main = candidates[0];
 if (!main) return JSON.stringify({headers:[],rows:[],country_evidence:[]});
 const container = main.table.closest('.ant-table-wrapper');
 if (!main.headers.length && container) {
   const width = main.rs[0].cells.length;
   const header = tables.find(t => t.closest('.ant-table-wrapper') === container && readHeaders(t).length === width);
   if(header) main.headers = readHeaders(header);
 }
 const headerIndex = main.headers.findIndex(h => /^(国家(?:\s*\/\s*地区)?|国家地区|所属国家|country(?:\s*\/\s*region)?)$/i.test(h.trim()));
 const countryIndex = main.headers.length ? headerIndex : 2;
 const evidence = [];
 const metadata = [];
 const productIndex = main.headers.findIndex(h => /^(商品|商品信息|商品名称|商品标题|产品|product(?:\s*(?:info|name))?)$/i.test(h.trim()));
 const categoryIndex = main.headers.findIndex(h => /^(品类|商品品类|商品分类|类目|商品类目|所属类目|category)$/i.test(h.trim()));
 const rows = main.rs.map(r => {
   const cells = Array.from(r.cells);
   const cell = countryIndex >= 0 ? cells[countryIndex] : null;
   const hints = [];
   if (cell) {
     for (const el of [cell, ...cell.querySelectorAll('img,[title],[aria-label],[data-country]')]) {
       for (const key of ['alt','title','aria-label','data-country']) {
         const value = el.getAttribute(key); if(value) hints.push(value);
       }
       if(el.tagName === 'IMG') {
         const src = el.getAttribute('src') || '';
         const match = src.match(/(?:^|[/_-])([A-Z]{2,3})(?:\.(?:png|svg|webp|jpg)|[/_?-]|$)/i);
         if(match) hints.push(match[1].toUpperCase());
       }
     }
   }
   evidence.push(hints.join('\n'));
   const productCell = cells[productIndex >= 0 ? productIndex : 1];
   const anchors = productCell ? Array.from(productCell.querySelectorAll('a[href]')) : [];
   const anchor = anchors.find(a => /\/e-commerce\/detail\//.test(a.href)) ||
                  anchors.find(a => /\/view\/product\//.test(a.href));
   const absolute = value => { try { const u = new URL(value, location.href); return /^https?:$/.test(u.protocol) ? u.href : ''; } catch(e) { return ''; } };
   const imgs = productCell ? Array.from(productCell.querySelectorAll('img')) : [];
   const img = imgs.find(i => !/flag|country|icon|avatar|logo/i.test([i.alt,i.className,i.src].join(' ')) &&
                     (i.naturalWidth >= 40 || i.width >= 40 || i.getAttribute('data-src'))) || null;
   const productUrl = anchor ? absolute(anchor.getAttribute('href')) : '';
   const categoryCell = cells[categoryIndex >= 0 ? categoryIndex : 4];
   const categoryPaths = categoryCell ? [categoryCell, ...categoryCell.querySelectorAll('[title],[aria-label],[data-category-path]')]
      .flatMap(e => ['title','aria-label','data-category-path'].map(key => e.getAttribute(key)).filter(Boolean)) : [];
   const imageTitle = img && img.alt && !/^(image|product|商品|图片)$/i.test(img.alt.trim()) ? img.alt.trim() : '';
   const title = (anchor ? (anchor.title || anchor.getAttribute('aria-label') || imageTitle ||
                  (anchor.innerText || anchor.textContent || '').split('\n')[0]) : imageTitle).trim();
   metadata.push({product_title:title, product_url:productUrl, category_paths:categoryPaths,
      product_id: (productUrl.match(/\/(?:detail|product)\/(\d+)/) || [])[1] || '',
      main_image_url:img ? absolute(img.getAttribute('data-src') || img.currentSrc || img.src) : ''});
   return cells.map(e => (e.innerText || e.textContent || '').trim());
 });
 const wrapper = main.table.closest('.ant-table-wrapper') || main.table.parentElement;
 const loading = !!Array.from(wrapper.querySelectorAll('.ant-spin-spinning')).find(e => e.getClientRects().length);
 return JSON.stringify({headers:main.headers,rows,country_evidence:evidence,product_metadata:metadata,loading,title:document.title});
})()
"""
