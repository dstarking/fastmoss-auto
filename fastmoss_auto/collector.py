"""Combined filters, selected-state checks, stable pagination, cancellation."""
import json
from threading import Event
from .bridge import Bridge
from .domain import Cancelled, load_sections

# Exact visible text; never treat a substring match or mere click as proof.
FILTER_JS = r"""
((label, action) => {
  const visible = e => !!(e.getClientRects().length);
  const text = e => (e.innerText || e.textContent || '').trim();
  const radios = Array.from(document.querySelectorAll('input[type=radio]'));
  const radio = radios.find(e => {
    const p = e.closest('label') || e.parentElement;
    return p && visible(p) && text(p) === label;
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
    .filter(e => visible(e) && text(e) === label)
    .sort((a,b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
  const el = candidates[0];
  if (!el) return JSON.stringify({found:false,selected:false});
  const active = e => e && (
    e.getAttribute('aria-selected') === 'true' ||
    e.getAttribute('aria-checked') === 'true' ||
    /(^|[\s_-])(active|selected|checked)([\s_-]|$)/i.test(e.className || '')
  );
  const selected = () => active(el) || active(el.parentElement) ||
    !!el.querySelector('input:checked');
  if (action === 'click' && !selected()) el.click();
  return JSON.stringify({found:true,selected:!!selected(),kind:'label'});
})(%s, %s)
"""

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
        filters = [job.country, "跨境店"] + ([job.category] if job.category else []) + ([job.period] if job.period else [])

        def wait():
            if cancel.wait(job.wait):
                raise Cancelled("任务已取消；未导出未完成的数据")

        def check_filters():
            for label in filters:
                state = bridge.evaluate(FILTER_JS % (json.dumps(label, ensure_ascii=False), '"check"'))
                if not state.get("found") or not state.get("selected"):
                    raise RuntimeError(f"无法确认筛选已生效：{label}。请检查页面标签、账号权限，或清空可选筛选后重试。")

        rows, signatures, warnings = [], set(), []
        try:
            progress(0, "连接 BrowserSkill")
            bridge.start()
            url = cfg["url"] if job.section == "products" else cfg["rankings"][job.ranking]
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
                check_filters()
                data = bridge.evaluate(cfg["extract_js"])
                cells = data.get("rows", [])
                signature = json.dumps(cells, ensure_ascii=False, sort_keys=True)
                if signature in signatures:
                    raise RuntimeError("分页内容重复，页面可能未刷新；已停止，未导出可疑结果")
                signatures.add(signature)
                parsed = []
                for cell in cells:
                    row = cfg["parse_row"](cell) if job.section == "products" else cfg["parse_row"](data.get("headers", []), cell)
                    if row:
                        if job.section == "products" and row.get("country", "").strip() != job.country:
                            raise RuntimeError("数据中的国家与所选国家不一致，已停止导出")
                        parsed.append({**row, "page": index + 1, "filter_country": job.country,
                                       "filter_shop_type": "跨境店", "filter_category": job.category,
                                       "filter_period": job.period})
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
            return rows, warnings
        finally:
            try:
                bridge.close()
            except Exception as exc:
                progress(90, f"清理浏览器会话失败：{exc}")
