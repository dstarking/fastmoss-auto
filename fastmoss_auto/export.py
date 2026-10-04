import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd


def export_run(job, rows, warnings=()):
    """One unique folder per successful run; remove incomplete exports on failure."""
    if not rows:
        raise ValueError("没有数据可导出")
    root = Path(job.output).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    prefix = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + job.section + "_"
    run = Path(tempfile.mkdtemp(prefix=prefix, dir=root))
    try:
        frame = pd.DataFrame(rows)
        frame.to_csv(run / "data.csv", index=False, encoding="utf-8-sig")
        record = {"schema_version": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
                  "filters": job.metadata(), "row_count": len(rows),
                  "warnings": list(warnings), "rows": rows}
        (run / "data.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        name_col = "product_name" if job.section == "products" else "shop_name"
        names = frame.get(name_col, pd.Series(dtype=str)).dropna().astype(str).nunique()
        report = ["# FastMoss 采集报告", "", f"- 平台：TikTok Shop / 跨境店", f"- 国家：{job.country}",
                  f"- 品类：{job.category or '页面默认'}", f"- 周期：{job.period or '页面默认'}",
                  f"- 数据行：{len(rows)}", f"- 不同名称数量：{names}", "", "数据来自当前账号可访问的榜单页面。",
                  "名称数量不是全市场商品/店铺数量；未提供历史快照，无法计算销量增幅。",
                  "不同币种、区间值与累计指标未合并为总销售额。", "", *[f"- 提示：{w}" for w in warnings]]
        (run / "report.md").write_text("\n".join(report), encoding="utf-8")
        return run
    except Exception:
        import shutil
        shutil.rmtree(run)
        raise


def numeric_sales(value):
    """Only parse unambiguous nonnegative counts, never currency or ranges."""
    text = str(value).strip().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kKmM万亿]?)", text)
    if not match:
        return None
    return float(match[1]) * {"": 1, "k": 1000, "m": 1000000, "万": 10000, "亿": 100000000}[match[2].lower()]
