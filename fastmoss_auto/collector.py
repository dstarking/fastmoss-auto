"""Combined filters, selected-state checks, stable pagination, cancellation."""
import json
import re
from threading import Event
from .bridge import Bridge
from .domain import Cancelled, load_sections
from .schema import PRODUCT_EXTRACT_JS, parse_product, canonical_country, country_tokens, category_matches

# Exact visible text; never treat a substring match or mere click as proof.
FILTER_JS = r"""
((label, action) => {
  const visible = e => !!(e.getClientRects().length);
  const text = e => (e.innerText || e.textContent || '').trim();
  const radios = Array.from(document.querySelectorAll('input[type=radio]'));
  const radio = radios.find(e => {
    const p = e.closest('label') || e.parentElement;
    return p && !p.closest('table,nav,aside') && visible(p) && text(p) === label;
  });
  if (radio) {
    if (action === 'click' && !radio.checked) radio.click();
    return JSON.stringify({found:true, selected:radio.checked, kind:'radio'});
  }
  if (action === 'click') {
    const expand = Array.from(document.querySelectorAll('button,span,a'))
      .find(e => visible(e) && text(e) === '展开');
    if (expand) expand.click();
  }
  const candidates = Array.from(document.querySelectorAll('button,a,span,li,label,div'))
    .filter(e => visible(e) && !e.closest('table,nav,aside') && text(e) === label)
    .sort((a,b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
  const el = candidates[0];
  if (!el) return JSON.stringify({found:false,selected:false});
  const active = e => e && (
    e.getAttribute('aria-selected') === 'true' ||
    e.getAttribute('aria-checked') === 'true' ||
    /(^|[\s_-])(active|selected|checked)([\s_-]|$)/i.test(e.className || '')
  );
  const selected = () => active(el) || (text(el.parentElement) === label && active(el.parentElement)) ||
    !!el.querySelector('input:checked');
  if (action === 'click' && !selected()) el.click();
  return JSON.stringify({found:true,selected:!!selected(),kind:'label'});
})(%s, %s)
"""

# Resolve the real navigation link; do not invent a sales URL or reuse newProducts.
SALES_BOARD_JS = r"""(() => {
 const links = Array.from(document.querySelectorAll('a[href]')).filter(a =>
   /^(商品销量榜|销量榜|商品销量|热销商品榜)$/.test((a.innerText || a.textContent || '').trim()) &&
   a.getClientRects().length && !a.closest('table') &&
   /\/e-commerce\//.test(a.href) && !/\/detail\/|\/newProducts(?:[/?#]|$)/.test(a.href));
 const urls = [...new Set(links.map(a => a.href))];
 return JSON.stringify({url:urls.length === 1 ? urls[0] : '', candidates:urls});
})()"""

GUARD_JS = """(() => JSON.stringify({url: location.href, title: document.title,
 blocked: /登录后|请登录|验证码|访问过于频繁|Access denied|Verify you are human/i.test(document.body.innerText),
 table: !!document.querySelector('table')}))()"""
PAGE_JS = """(() => JSON.stringify({page: Array.from(document.querySelectorAll(
 '.ant-pagination-item-active,[aria-current="page"]')).map(e => e.textContent.trim()).join('|')}))()"""
NEXT_JS = """(() => {
 const nodes = Array.from(document.querySelectorAll('li[title="下一页"],li[class*=next],button[aria-label="Next Page"]'));
 const button = nodes.find(e => e.getClientRects().length && !/disabled/.test(e.className || '') &&
 e.getAttribute('aria-disabled') !== 'true' && !e.disabled);
 if (!button) return JSON.stringify({clicked:false});
 button.click(); return JSON.stringify({clicked:true});
})()"""


class Collector:
    def __init__(self, bridge=None, sections=None):
        self.bridge = bridge
        self.sections = sections

    def collect(self, job, cancel=None, progress=lambda *args: None):
        job.validate()
        cancel = cancel or Event()
        sections = self.sections or load_sections(job.source)
        cfg = sections[job.section]
        bridge = self.bridge or Bridge(job.bsk, cancel)
        country_label = canonical_country(job.country) or job.country
        category_labels = [part.strip() for part in re.split(r'\s*(?:/|>|›|→|\\|－|-)\s*', job.category) if part.strip()]
        filters = [country_label, "跨境店"] + (category_labels if job.category else [])
        # Parent category choices may collapse after selecting a leaf; verify the leaf
        # control and the full path in every product row.
        checked_filters = [country_label, "跨境店"] + (category_labels[-1:] if job.category else [])

        def wait():
            if cancel.wait(job.wait):
                raise Cancelled("任务已取消；未导出未完成的数据")

        def check_filters():
            for label in checked_filters:
                state = bridge.evaluate(FILTER_JS % (json.dumps(label, ensure_ascii=False), '"check"'))
                if not state.get("found") or not state.get("selected"):
                    raise RuntimeError(f"无法确认筛选已生效：{label}。请检查页面标签、账号权限，或清空可选筛选后重试。")

        rows, signatures, warnings = [], set(), []
        try:
            progress(0, "连接 BrowserSkill")
            if job.period:
                raise ValueError("上游商品/店铺榜不支持 --time；周期仅适用于达人榜，请清空周期")
            if job.section == "shops" and job.category:
                raise ValueError("上游店铺榜不支持 --category；请在商品分析中按品类筛选")
            bridge.start()
            url = cfg["url"] if job.section == "products" else cfg["rankings"][job.ranking]
            bridge.navigate(url)
            wait()
            if job.section == "products":
                sales = bridge.evaluate(SALES_BOARD_JS)
                if not sales.get("url"):
                    raise RuntimeError("无法定位唯一的商品销量榜入口；请检查 FastMoss 中文导航和账号权限。不会用新品榜代替销量榜。")
                url = sales["url"]
                bridge.navigate(url)
                wait()
            for label in filters:
                state = bridge.evaluate(FILTER_JS % (json.dumps(label, ensure_ascii=False), '"click"'))
                if not state.get("found"):
                    raise RuntimeError(f"页面未提供筛选：{label}。不会保存其他市场或本土店数据。")
                wait()
            check_filters()
            for index in range(job.pages):
                if cancel.is_set():
                    raise Cancelled("任务已取消")
                guard = bridge.evaluate(GUARD_JS)
                if guard.get("blocked") or not guard.get("table"):
                    raise RuntimeError("页面未就绪或需要登录/验证，请在浏览器处理后重试")
                if job.section == "products" and guard.get("url"):
                    from urllib.parse import urlsplit
                    if urlsplit(guard["url"]).path.rstrip('/') != urlsplit(url).path.rstrip('/'):
                        raise RuntimeError("页面已离开商品销量榜；停止采集")
                check_filters()
                extract = PRODUCT_EXTRACT_JS if job.section == "products" and cfg.get("parse_kind") == "fixed" else cfg["extract_js"]
                data = bridge.evaluate(extract)
                parsed = []
                for attempt in range(4):
                    parsed = []
                    mismatch = "表格仍在加载" if data.get("loading") else None
                    current_signature = json.dumps(data.get("rows", []), ensure_ascii=False, sort_keys=True)
                    if current_signature in signatures:
                        mismatch = "分页内容重复，等待页面刷新"
                    headers = data.get("headers", [])
                    hints = data.get("country_evidence", [])
                    metadata = data.get("product_metadata", [])
                    for row_index, cell in enumerate(data.get("rows", [])):
                        hint = hints[row_index] if row_index < len(hints) else ""
                        row = (parse_product(headers, cell, hint, cfg["parse_row"])
                               if job.section == "products" and cfg.get("parse_kind") == "fixed"
                               else cfg["parse_row"](cell) if job.section == "products"
                               else cfg["parse_row"](headers, cell))
                        if not row:
                            continue
                        if job.section == "products":
                            raw = row.get("country_raw", row.get("country", ""))
                            evidence = row.get("country_evidence", "")
                            observed = country_tokens(raw) | country_tokens(evidence)
                            wanted = canonical_country(job.country) or job.country
                            if observed and observed != {wanted}:
                                mismatch = f"第{index + 1}页国家不一致：所选={job.country}；读取={raw!r}；图标信息={evidence!r}；识别={sorted(observed)}"
                                break
                            if str(raw).strip() and not observed:
                                mismatch = f"国家字段无法识别：所选={job.country}；读取={raw!r}；表头={headers}。可能是列结构变化，请核对上游版本。"
                                break
                            if observed:
                                row["country_raw"] = raw
                                row["country"] = wanted
                                row["country_verification"] = "row_and_page_filter"
                            else:
                                mismatch = "商品行国家缺少可验证信息，不能保证精确国家范围"
                                break
                            if not category_matches(job.category, row.get("category", "")):
                                mismatch = f"第{index + 1}页类目不一致或缺失：所选={job.category}；读取={row.get('category', '')!r}"
                                break
                            row["category_verification"] = "row_and_page_filter"
                            info = metadata[row_index] if row_index < len(metadata) else {}
                            row.update({key: info.get(key, '') for key in ('product_title', 'product_url', 'product_id', 'main_image_url')})
                            row['product_title'] = row['product_title'] or row.get('product_name', '')
                            row['product_name'] = row['product_title']
                            row['source_url'] = url
                            row['ranking'] = 'sales'
                        parsed.append({**row, "page": index + 1, "filter_country": country_label,
                                       "filter_shop_type": "跨境店", "filter_category": job.category,
                                       "filter_period": ""})
                    if not parsed and not mismatch:
                        mismatch = "当前页没有可解析数据，等待加载"
                    if not mismatch:
                        break
                    if attempt == 3:
                        raise RuntimeError(mismatch + "；刷新重试后仍不一致，已停止导出")
                    progress(int(index / job.pages * 90), mismatch + "；等待页面刷新后重试")
                    wait()
                    check_filters()
                    data = bridge.evaluate(extract)
                cells = data.get("rows", [])
                signature = json.dumps(cells, ensure_ascii=False, sort_keys=True)
                if signature in signatures:
                    raise RuntimeError("分页内容重复，页面可能未刷新；已停止，未导出可疑结果")
                signatures.add(signature)
                if not parsed:
                    raise RuntimeError("当前页没有可解析数据；请检查会员权限、筛选结果或上游解析器版本")
                rows.extend(parsed)
                progress(int((index + 1) / job.pages * 90), f"第 {index + 1} 页：{len(parsed)} 条，累计 {len(rows)} 条")
                if index + 1 < job.pages:
                    before = bridge.evaluate(PAGE_JS).get("page")
                    if not bridge.evaluate(NEXT_JS).get("clicked"):
                        warnings.append("榜单已到末页，实际页数少于请求页数")
                        break
                    wait()
                    after = bridge.evaluate(PAGE_JS).get("page")
                    if before and after and before == after:
                        raise RuntimeError("点击下一页后页码未变化，请增加页面等待时间")
            if cancel.is_set():
                raise Cancelled("任务已取消")
            if job.section == 'products':
                unique, seen = [], set()
                for row in rows:
                    identity = row.get('product_id') or row.get('product_url')
                    if identity and identity in seen:
                        continue
                    if identity:
                        seen.add(identity)
                    unique.append(row)
                rows = unique
                for key, caption in [('product_url', '商品详情链接'), ('main_image_url', '主图链接')]:
                    count = sum(not row.get(key) for row in rows)
                    if count:
                        warnings.append(f'{count} 条商品未展示可提取的{caption}；保留空值，未生成猜测链接。')
            return rows, warnings
        finally:
            try:
                bridge.close()
            except Exception as exc:
                progress(90, f"清理浏览器会话失败：{exc}")
