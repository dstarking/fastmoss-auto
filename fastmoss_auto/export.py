import json
import re
import tempfile
import hashlib
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from .domain import Cancelled


def export_run(job, rows, warnings=(), cancel=None, progress=lambda *args: None):
    """One unique folder per successful run; remove incomplete exports on failure."""
    if not rows:
        raise ValueError("没有数据可导出")
    root = Path(job.output).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    prefix = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + job.section + "_"
    run = Path(tempfile.mkdtemp(prefix=prefix, dir=root))
    try:
        rows = [dict(row) for row in rows]
        notices = list(warnings)
        if job.section == 'products':
            failed = 0
            cached = {}
            for index, row in enumerate(rows):
                if cancel and cancel.is_set():
                    raise Cancelled('任务已取消；未导出未完成的数据')
                row.setdefault('product_title', row.get('product_name', ''))
                for key in ('product_url', 'main_image_url'):
                    row.setdefault(key, '')
                row['main_image_file'] = ''
                url = row['main_image_url']
                if url:
                    if url not in cached:
                        try:
                            cached[url] = download_image(url, run)
                        except Exception:
                            cached[url] = ''
                    row['main_image_file'] = cached[url]
                    failed += not bool(cached[url])
                progress(95, f'保存商品主图 {index + 1}/{len(rows)}')
            if failed:
                notices.append(f'{failed} 条主图下载失败；CSV保留原始主图URL，可在浏览器打开。')
        if cancel and cancel.is_set():
            raise Cancelled('任务已取消；未导出未完成的数据')
        frame = pd.DataFrame(rows)
        frame.to_csv(run / "data.csv", index=False, encoding="utf-8-sig")
        record = {"schema_version": 2, "captured_at": datetime.now(timezone.utc).isoformat(),
                  "filters": job.metadata(), "row_count": len(rows),
                  "warnings": notices, "rows": rows}
        (run / "data.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        name_col = "product_name" if job.section == "products" else "shop_name"
        names = frame.get(name_col, pd.Series(dtype=str)).dropna().astype(str).nunique()
        report = ["# FastMoss 采集报告", "", f"- 平台：TikTok Shop / 跨境店", f"- 国家：{job.country}",
                  f"- 品类：{job.category or '页面默认'}", f"- 周期：{job.period or '页面默认'}",
                  f"- 数据行：{len(rows)}", f"- 不同名称数量：{names}", "", "数据来自当前账号可访问的榜单页面。",
                  "名称数量不是全市场商品/店铺数量；未提供历史快照，无法计算销量增幅。",
                  "不同币种、区间值与累计指标未合并为总销售额。", "", *[f"- 提示：{w}" for w in notices]]
        if job.section == 'products':
            candidates = sales_candidates(rows)
            pd.DataFrame(candidates, columns=['candidate_rank', 'sales_value', *frame.columns]).to_csv(
                run / 'bestsellers.csv', index=False, encoding='utf-8-sig')
            report.extend(['', '## 销量榜爆款候选 Top 10', '',
                '在已采集且通过国家、类目校验的样本内，按榜单销量降序排列；不混用累计销量。',
                '候选表示当前高销量商品，不能据此推断增长趋势、利润或未来爆款。',
                f'可解析销量：{len(candidates)}/{len(rows)} 条；区间、隐藏值与缺失值不参与排序。', '',
                '| 排名 | 商品标题 | 榜单销量 | 指标 | 商品链接 | 主图 |',
                '| --- | --- | --- | --- | --- | --- |'])
            def cell(value):
                return str(value).replace('|', '\\|').replace('\n', ' ')
            for row in candidates[:10]:
                report.append('| ' + ' | '.join(cell(row.get(key, '')) for key in
                    ('candidate_rank', 'product_title', 'sales_period', 'sales_metric', 'product_url', 'main_image_url')) + ' |')
            report.extend(['', '完整排序见 bestsellers.csv。CSV以主图URL和相对文件路径保存图片引用；图片文件位于 images/。'])
        (run / "report.md").write_text("\n".join(report), encoding="utf-8")
        return run
    except Exception:
        import shutil
        shutil.rmtree(run)
        raise


def sales_candidates(rows):
    ranked = [(numeric_sales(row.get('sales_period', '')), row) for row in rows]
    ranked = sorted((pair for pair in ranked if pair[0] is not None), key=lambda pair: pair[0], reverse=True)
    return [{**row, 'candidate_rank': index + 1, 'sales_value': value} for index, (value, row) in enumerate(ranked)]


def download_image(url, run):
    """Download public image bytes; never substitute an image or a guessed URL."""
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('不是公开图片URL')
    request = Request(url, headers={'User-Agent': 'FastMossAuto/0.1.7'})
    with urlopen(request, timeout=5) as response:
        data = response.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise ValueError('主图超过10MB')
    ext = ('png' if data.startswith(b'\x89PNG\r\n\x1a\n') else
           'jpg' if data.startswith(b'\xff\xd8\xff') else
           'gif' if data.startswith((b'GIF87a', b'GIF89a')) else
           'webp' if data.startswith(b'RIFF') and data[8:12] == b'WEBP' else
           'avif' if data[4:8] == b'ftyp' and data[8:12] in (b'avif', b'avis') else '')
    if not ext:
        raise ValueError('响应不是支持的图片格式')
    relative = Path('images') / (hashlib.sha256(url.encode()).hexdigest()[:24] + '.' + ext)
    (run / 'images').mkdir(exist_ok=True)
    (run / relative).write_bytes(data)
    return relative.as_posix()


def numeric_sales(value):
    """Only parse unambiguous nonnegative counts, never currency or ranges."""
    text = str(value).strip().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kKmM万亿]?)", text)
    if not match:
        return None
    return float(match[1]) * {"": 1, "k": 1000, "m": 1000000, "万": 10000, "亿": 100000000}[match[2].lower()]
