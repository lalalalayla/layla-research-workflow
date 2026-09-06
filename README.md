# layla-research-workflow

Layla 个人研究工作流的**代码仓库**：arXiv 抓取候选池、Gmail alerts 摘要、月度复盘草稿。

> 本仓库只包含代码。自动化产物（候选池、邮件摘要、月报草稿）提交到独立的私有数据仓库 `layla-research-output`；私人文档资料库保存在本机 Documents，不进入任何 GitHub 仓库。

## 目录

- `scripts/build_weekly_pool.py`：抓 arXiv 最近 7 天新投稿，关键词打分 + 去重，生成每周候选池。
- `scripts/fetch_email_digest.py`：通过 Gmail IMAP 抓取 Scholar Alerts / 行业 newsletter，生成邮件摘要。
- `scripts/build_monthly_review.py`：生成月度研究简报草稿。
- `scripts/config.py`：arXiv 分类与关键词权重配置。
- `.github/workflows/`：GitHub Actions 定时任务（写入产物仓库）。

## 本地运行

脚本通过环境变量 `RESEARCH_OUTPUT_ROOT` 指定产物目录。不设置时默认写到代码仓目录（建议始终显式指定到本地资料库）：

```bash
export RESEARCH_OUTPUT_ROOT="/Users/laylachiao/Documents/ChatGPT/日常工作流的创建/Layla_Research_Workflow"

python3 scripts/build_weekly_pool.py           # 每周候选池
python3 scripts/fetch_email_digest.py --days 7 # Gmail 摘要（本地需 .env + 7897 代理）
python3 scripts/build_monthly_review.py        # 月度简报草稿
```

邮箱抓取需要 `.env`（已被 gitignore，不入库）：

```dotenv
GMAIL_USER=livachiao@gmail.com
GMAIL_APP_PASSWORD=xxxx
IMAP_PROXY_HOST=127.0.0.1
IMAP_PROXY_PORT=7897
```

## GitHub Actions 需要的 Secrets

- `OUTPUT_REPO_TOKEN`：PAT，需对 `layla-research-workflow`（读）和 `layla-research-output`（读/写）有权限。
- `GMAIL_USER` / `GMAIL_APP_PASSWORD`：邮件摘要任务用。

## 产物仓库布局

`layla-research-output` 私有仓库下由 Actions 自动生成：

```text
00_inbox_临时收件箱/   每周论文候选池_*.md、邮箱alerts_*.md
04_monthly_reviews_月度复盘/   月度研究简报草稿
.state/                arXiv 去重状态（勿删）
```
