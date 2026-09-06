# -*- coding: utf-8 -*-
"""生成月度研究简报草稿：统计论文卡片与候选池，输出到 04_monthly_reviews_月度复盘/。"""

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = Path(os.environ.get("RESEARCH_OUTPUT_ROOT", str(ROOT)))
CARDS = OUTPUT_ROOT / "02_paper_cards_论文卡片"
INBOX = OUTPUT_ROOT / "00_inbox_临时收件箱"
REVIEWS = OUTPUT_ROOT / "04_monthly_reviews_月度复盘"


def previous_month(d: date):
    y, m = d.year, d.month - 1
    if m == 0:
        y, m = y - 1, 12
    return y, m


def build():
    today = date.today()
    y, m = previous_month(today)
    month_str = f"{y:04d}-{m:02d}"

    cards = sorted(CARDS.glob("*.md")) if CARDS.exists() else []
    cards = [p for p in cards if p.name != "论文卡片_模板.md"]

    pools = sorted(
        INBOX.glob("每周论文候选池_*.md") if INBOX.exists() else [],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:4]

    REVIEWS.mkdir(parents=True, exist_ok=True)
    report = REVIEWS / f"{month_str}_研究简报.md"

    lines = [
        f"# {month_str} 研究简报",
        "",
        "> 自动化草稿：统计与占位内容由脚本生成，需要人工补充判断。",
        "",
        "## 本月概览",
        "",
        f"- 论文卡片总数：{len(cards)}",
        f"- 最近候选池文件：{len(pools)} 份",
        "",
        "## 最近候选池",
        "",
    ]
    lines += [f"- [{p.name}](../00_inbox_临时收件箱/{p.name})" for p in pools]
    lines += [
        "",
        "## 技术趋势信号",
        "",
        "- （待补充：本月读过的论文里反复出现的方法/主题）",
        "",
        "## 能源行业需求信号",
        "",
        "- （待补充：行业资讯里值得关注的趋势）",
        "",
        "## 能力缺口",
        "",
        "- （待补充：本月阅读中暴露的补课知识点）",
        "",
        "## 下月计划",
        "",
        "- （待补充）",
        "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"月度简报草稿：{report}")
    return report


if __name__ == "__main__":
    build()
