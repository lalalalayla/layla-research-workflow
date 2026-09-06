# -*- coding: utf-8 -*-
"""生成每周论文候选池：抓取 -> 打分 -> 去重 -> 输出 Markdown。"""

import json
import os
import re
from datetime import date
from pathlib import Path

from config import (
    DOMAIN_KEYWORDS,
    MAX_POOL,
    METHOD_KEYWORDS,
    MIN_SCORE,
    NEGATIVE_KEYWORDS,
    STRONG_METHOD_SCORE,
    THEMES,
    TOP_READ,
)
from fetch_arxiv import fetch_recent_papers

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = Path(os.environ.get("RESEARCH_OUTPUT_ROOT", str(ROOT)))
INBOX = OUTPUT_ROOT / "00_inbox_临时收件箱"
STATE_DIR = OUTPUT_ROOT / ".state"


def _lower(text):
    return (text or "").lower()


def _kw_pattern(keyword: str) -> re.Pattern:
    """词边界匹配，避免 wind 命中 window、solar 命中 solaris 这类误报。"""
    return re.compile(rf"\b{re.escape(keyword)}\b")


def _unique_keep_order(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def score_paper(paper: dict) -> None:
    title = _lower(paper["title"])
    abstract = _lower(paper["summary"])
    text = title + " " + abstract
    score = 0
    matched = []
    domain_hits = []

    for kw in DOMAIN_KEYWORDS:
        pattern = _kw_pattern(kw)
        if pattern.search(title):
            score += 3
            domain_hits.append(kw)
            matched.append(kw)
        elif pattern.search(abstract):
            score += 1
            domain_hits.append(kw)
            matched.append(kw)
    for kw in METHOD_KEYWORDS:
        pattern = _kw_pattern(kw)
        if pattern.search(title):
            score += 2
            matched.append(kw)
        elif pattern.search(abstract):
            score += 1
            matched.append(kw)
    for d_kw, m_kw in THEMES:
        if _kw_pattern(d_kw).search(text) and _kw_pattern(m_kw).search(text):
            score += 2
            matched.append(f"{d_kw}+{m_kw}")
    if not domain_hits:
        for kw in NEGATIVE_KEYWORDS:
            if _kw_pattern(kw).search(text):
                score -= 5
                matched.append(f"neg:{kw}")

    paper["score"] = score
    paper["matched"] = _unique_keep_order(matched)
    paper["domain_hits"] = domain_hits


def load_seen() -> set:
    state_file = STATE_DIR / "seen_ids.json"
    if state_file.exists():
        return set(json.loads(state_file.read_text(encoding="utf-8")))
    return set()


def save_seen(seen: set) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "seen_ids.json").write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def iso_week_str(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def build():
    papers = fetch_recent_papers()
    seen = load_seen()

    new_papers = []
    for p in papers:
        if p["arxiv_id"] in seen:
            continue
        score_paper(p)
        new_papers.append(p)

    # 全部加入 seen，避免下周重复出现
    seen.update(p["arxiv_id"] for p in papers)
    save_seen(seen)

    pool = sorted(
        [
            p
            for p in new_papers
            if p["score"] >= MIN_SCORE
            and (p["domain_hits"] or p["score"] >= STRONG_METHOD_SCORE)
        ],
        key=lambda p: p["score"],
        reverse=True,
    )[:MAX_POOL]
    for i, p in enumerate(pool):
        p["status"] = "Read" if i < TOP_READ else "Maybe"

    today = date.today()
    week = iso_week_str(today)
    filename = INBOX / f"每周论文候选池_{week}.md"
    INBOX.mkdir(parents=True, exist_ok=True)

    lines = [
        "# 每周论文候选池",
        "",
        f"> 周期：{week}（最近 7 天 arXiv 新投稿，关键词自动打分）",
        f"> 生成时间：{today.isoformat()}",
        "> 使用方式：每天扫读，每周选 2-3 篇进入 Gemini Notebook 精读。",
        "",
        "## 候选论文",
        "",
        "| 状态 | 标题 | 来源 | 年份 | 链接 | 为什么值得看 | 初步判断 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for p in pool:
        year = p["published"][:4]
        why = "、".join(p["matched"][:6]) or "关键词匹配"
        link = f"https://arxiv.org/abs/{p['arxiv_id']}"
        authors = "、".join(p["authors"][:2]) + (" 等" if len(p["authors"]) > 2 else "")
        title_link = f"[{p['title']}]({link})"
        lines.append(
            f"| {p['status']} | {title_link} | arXiv | {year} | [链接]({link}) | {why} | 得分 {p['score']}；{authors} |"
        )
    if not pool:
        lines.append("| - | 本周没有新命中关键词的论文 | - | - | - | - | - |")

    lines += [
        "",
        "## 本周不读但保留",
        "",
        "- （手动补充）",
        "",
        "## 本周放弃",
        "",
        "- （手动补充）",
        "",
    ]
    filename.write_text("\n".join(lines), encoding="utf-8")

    # 摘要文件：给 GitHub Issue 用
    summary = [f"# 本周论文候选池 {week}", "", f"共 {len(pool)} 篇命中，Top {min(TOP_READ, len(pool))} 为 Read。", ""]
    for p in pool[:10]:
        summary.append(f"- {p['status']} [{p['title']}](https://arxiv.org/abs/{p['arxiv_id']}) — 得分 {p['score']}")
    summary.append("")
    summary.append(f"完整列表见 `00_inbox_临时收件箱/{filename.name}`")
    summary_file = INBOX / f"候选池摘要_{week}.md"
    summary_file.write_text("\n".join(summary), encoding="utf-8")

    print(f"抓取 {len(papers)} 篇，新论文 {len(new_papers)} 篇，候选池 {len(pool)} 篇")
    print(f"候选池文件：{filename}")
    return pool


if __name__ == "__main__":
    build()
