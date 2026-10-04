from dataclasses import asdict, dataclass
from pathlib import Path
import importlib.util
import os

COUNTRIES = ["新加坡", "马来西亚", "泰国", "越南", "菲律宾", "印度尼西亚", "美国", "英国", "日本", "德国", "法国", "意大利", "西班牙", "墨西哥", "巴西"]


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class Job:
    country: str = "新加坡"
    section: str = "products"
    ranking: str = "sales"
    category: str = "宠物用品"
    period: str = ""
    pages: int = 3
    wait: float = 5.0
    output: str = ""
    source: str = ""
    bsk: str = "bsk"

    def validate(self):
        if not self.country.strip():
            raise ValueError("请选择国家")
        if self.period:
            raise ValueError("周期 --time 仅适用于上游达人榜，商品和店铺请留空")
        if self.section == "shops" and self.category:
            raise ValueError("上游店铺榜不支持品类参数，请留空或使用商品分析")
        if self.section not in ("products", "shops"):
            raise ValueError("只支持商品和店铺榜单")
        if self.section == "shops" and self.ranking not in ("sales", "hot"):
            raise ValueError("店铺榜单无效")
        if not 1 <= self.pages <= 100:
            raise ValueError("页数应为 1–100")
        if not 1 <= self.wait <= 60:
            raise ValueError("页面等待应为 1–60 秒")
        if not self.output.strip():
            raise ValueError("请选择输出目录")
        if not self.bsk.strip():
            raise ValueError("请选择 bsk 可执行文件")

    def metadata(self):
        data = asdict(self)
        # Keep machine-local tool paths out of exported reports.
        for key in ("source", "bsk", "output"):
            data.pop(key)
        return {"platform": "TikTok Shop", "shop_type": "跨境店", **data}


def load_sections(source):
    """Load user's existing upstream parser without vendoring unlicensed code."""
    path = Path(source).expanduser()
    if path.is_dir():
        path = path / "scripts" / "sections.py" if (path / "scripts").is_dir() else path / "sections.py"
    if not path.is_file():
        raise ValueError("请选择 fastmoss-rpa-skills 仓库目录（需包含 scripts/sections.py）")
    spec = importlib.util.spec_from_file_location("fastmoss_upstream_sections", path)
    if spec is None or spec.loader is None:
        raise ValueError("无法加载采集模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for section in ("products", "shops"):
        if section not in module.SECTIONS:
            raise ValueError(f"上游缺少 {section} 模块")
    return module.SECTIONS


def default_output():
    if os.name == "nt" and Path("F:/").exists():
        return "F:/fastmoss/data"
    return str(Path.home() / "FastMoss" / "data")
