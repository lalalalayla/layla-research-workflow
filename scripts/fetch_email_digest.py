# -*- coding: utf-8 -*-
"""抓取 Gmail 中的论文 / 资讯 alert 邮件，生成每周 Markdown 摘要。

覆盖来源：
  - 论文候选：Google Scholar Alerts、arXiv 每日列表、Semantic Scholar
  - 能源资讯：IEA、EIA、Carbon Brief、Canary Media
  - AI 资讯：The Batch、Import AI、MIT Tech Review、Hugging Face

认证方式：Gmail IMAP + App Password（需在 Google 账号开启两步验证后生成）。
凭据通过环境变量传入：
  - GMAIL_USER：邮箱地址
  - GMAIL_APP_PASSWORD：App Password
本地可在仓库根目录创建 .env（已被 .gitignore 排除）；GitHub Actions 用 Secrets。

用法：
  python3 scripts/fetch_email_digest.py              # 最近 3 天未读邮件
  python3 scripts/fetch_email_digest.py --days 7     # 最近 7 天
  python3 scripts/fetch_email_digest.py --keep-unread  # 处理完不标记已读

处理策略：成功写入摘要后，默认把邮件标记为已读（下次不重复抓取）。
"""

import argparse
import email
import html
import imaplib
import os
import re
import socket
import ssl
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = Path(os.environ.get("RESEARCH_OUTPUT_ROOT", str(ROOT)))
INBOX = OUTPUT_ROOT / "00_inbox_临时收件箱"
ENV_FILE = ROOT / ".env"

# 按来源分组：显示分类 -> 发件人特征子串（IMAP FROM 模糊匹配，全小写）
MAIL_SOURCES = {
    "论文候选": [
        "scholaralerts",           # Google Scholar Alerts
        "arxiv.org",               # arXiv 每日列表 / 通知
        "semanticscholar",         # Semantic Scholar alerts
    ],
    "能源资讯": [
        "iea.org",
        "eia.gov",
        "carbonbrief.org",
        "canarymedia.com",
    ],
    "AI资讯": [
        "deeplearning.ai",         # The Batch
        "importai.substack.com",   # Import AI
        "technologyreview.com",    # MIT Tech Review
        "huggingface.co",          # Hugging Face
    ],
}

MONTHS_EN = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


class IMAP4_SSL_Proxy(imaplib.IMAP4_SSL):
    """支持走本地 HTTP CONNECT 代理（如 Clash 7897）连接 Gmail IMAP。"""

    def __init__(self, host, timeout=None, proxy_host=None, proxy_port=None):
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        super().__init__(host, timeout=timeout)

    def _http_connect_tunnel(self, host, port, timeout):
        if not self._proxy_host or not self._proxy_port:
            return None
        sock = socket.create_connection(
            (self._proxy_host, self._proxy_port), timeout=timeout
        )
        sock.settimeout(timeout)
        request = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n"
        sock.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        status = response.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 200 " not in status:
            sock.close()
            raise OSError(f"HTTP CONNECT 代理返回异常：{status}")
        return sock

    def open(self, host="", port=imaplib.IMAP4_SSL_PORT, timeout=None):
        tunnel = self._http_connect_tunnel(host, port, timeout)
        if tunnel is None:
            return super().open(host, port, timeout)
        self.host = host
        self.port = port
        try:
            self.sock = self.ssl_context.wrap_socket(tunnel, server_hostname=self.host)
            self.file = self.sock.makefile("rb")
        except OSError as exc:
            self.sock = None
            raise OSError(f"通过代理连接 Gmail 失败：{exc}") from exc


def load_env() -> None:
    """从仓库根目录 .env 读取 KEY=VALUE（不覆盖已存在的环境变量）。"""
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _decode_header_value(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _decode_payload(part) -> str:
    charset = part.get_content_charset() or "utf-8"
    payload = part.get_payload(decode=True)
    if payload is None:
        return part.get_payload() or ""
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    # 先保留链接：<a href="URL">文字</a> -> 文字 (URL)
    raw = re.sub(
        r'(?is)<a\s+[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        lambda m: f"{re.sub(r'(?s)<[^>]+>', ' ', m.group(2)).strip()} ({m.group(1)})",
        raw,
    )
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
    return "\n".join(line for line in lines if line)


def _get_body_text(msg) -> str:
    candidates = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                candidates.append(_decode_payload(part))
            elif ctype == "text/html":
                candidates.append(html_to_text(_decode_payload(part)))
        if candidates:
            # 有些邮件（如 Carbon Brief）text/plain 只是占位符，取内容最长部分
            return max(candidates, key=len)
        return ""
    if msg.get_content_type() == "text/html":
        return html_to_text(_decode_payload(msg))
    return _decode_payload(msg)


def _clean_url(url: str) -> str:
    """把 scholar_url / scholar_share 包裹的链接解包成真实地址。"""
    parsed = urllib.parse.urlparse(url)
    if "scholar.google.com" in parsed.netloc:
        params = urllib.parse.parse_qs(parsed.query)
        target = params.get("url")
        if target:
            return target[0]
    return url


def _should_skip_url(url: str) -> bool:
    lowered = url.lower()
    if any(mark in lowered for mark in ("unsubscribe", "scholar_alerts", "email_for_op")):
        return True
    parsed = urllib.parse.urlparse(url)
    if "scholar.google.com" in parsed.netloc and parsed.path in ("/citations", "/scholar"):
        return True
    return False


def _extract_items(text: str, limit: int = 20):
    """提取正文里的链接：优先用同一行链接前的文字作为标题，否则用上一行。"""
    lines = [line for line in text.splitlines() if line.strip()]
    items = []
    seen_urls = set()
    for i, line in enumerate(lines):
        urls = re.findall(r"https?://[^\s<>\"')]+", line)
        if not urls:
            continue
        url = _clean_url(urls[0])
        if _should_skip_url(url):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        before = line[: line.find(urls[0])].strip(" -–•·\t()")
        if re.search(r"can't display HTML|clicking here|Not interested", before, re.I):
            continue
        if re.match(
            r"(?i)^(view in browser|sign up|subscribe|unsubscribe|share|tweet|x post|facebook|linkedin|whatsapp|email)\b",
            before.strip(),
        ):
            continue
        label = before if len(before) >= 10 else (lines[i - 1][:120] if i > 0 else "")
        label = label.strip(" -–•·\t()")
        if len(label) < 10 or label.isdigit():
            label = "候选论文"
        items.append(f"- {label}\n  - {url}")
        if len(items) >= limit:
            break
    return items


def _parse_message(raw_bytes: bytes):
    msg = email.message_from_bytes(raw_bytes)
    subject = _decode_header_value(msg.get("Subject"))
    sender = _decode_header_value(msg.get("From"))
    date_raw = msg.get("Date")
    try:
        dt = parsedate_to_datetime(date_raw)
        date_str = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        date_str = "日期未知"
    body = _get_body_text(msg)
    return {
        "subject": subject or "(无主题)",
        "sender": sender,
        "date": date_str,
        "items": _extract_items(body),
    }


def _imap_date(d: date) -> str:
    return f"{d.day:02d}-{MONTHS_EN[d.month - 1]}-{d.year}"


def _find_all_mail(mail):
    """在 Gmail 中定位 All Mail 文件夹（兼容中英文界面），找不到返回 None。"""
    try:
        typ, data = mail.list()
        if typ != "OK":
            return None
        for item in data:
            line = item.decode(errors="replace") if isinstance(item, bytes) else str(item)
            m = re.search(r'"([^"]+)"\s*$', line.strip())
            if not m:
                continue
            name = m.group(1)
            lower = name.lower()
            if lower.startswith("[gmail]") and ("all mail" in lower or "所有邮件" in name):
                return name
    except Exception:
        return None
    return None


def _select_mailbox(mail) -> bool:
    """选择包含归档邮件的文件夹；逐个尝试直到成功。"""
    all_mail = _find_all_mail(mail)
    candidates = []
    if all_mail:
        candidates.append(f'"{all_mail}"')
    candidates += ['"[Gmail]/All Mail"', '"[Gmail]/所有邮件"', "INBOX"]
    for folder in candidates:
        try:
            typ, _data = mail.select(folder)
            if typ == "OK":
                return True
        except Exception:
            continue
    return False


def _run_once(days: int, keep_unread: bool) -> str:
    user = os.environ.get("GMAIL_USER", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not user or not app_password:
        sys.exit("缺少凭据：请设置 GMAIL_USER 和 GMAIL_APP_PASSWORD（本地放 .env，Actions 用 Secrets）")
    proxy_host = os.environ.get("IMAP_PROXY_HOST", "").strip() or None
    proxy_port_raw = os.environ.get("IMAP_PROXY_PORT", "").strip()
    proxy_port = int(proxy_port_raw) if proxy_port_raw else None

    since = date.today() - timedelta(days=days)
    since_str = _imap_date(since)

    mail = None
    try:
        mail = IMAP4_SSL_Proxy(
            "imap.gmail.com",
            timeout=300,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
        )
        mail.login(user, app_password)
        if not _select_mailbox(mail):
            sys.exit("无法选择 Gmail 文件夹，请检查 IMAP 是否已开启")

        # 每个来源各做一次 UNSEEN + FROM 搜索，合并 UID
        grouped_uids = {}  # category -> {uid -> True}
        for category, senders in MAIL_SOURCES.items():
            found = {}
            for sender_sub in senders:
                criteria = f'(UNSEEN SINCE {since_str} FROM "{sender_sub}")'
                result, data = mail.uid("search", None, criteria)
                if result != "OK":
                    continue
                for num in data[0].split():
                    found[num.decode()] = True
            if found:
                grouped_uids[category] = found

        entries = []  # (category, parsed_message)
        uids_to_mark = []
        for category, uid_map in grouped_uids.items():
            for uid in sorted(uid_map.keys()):
                result, data = mail.uid("fetch", uid, "(BODY.PEEK[])")
                if result != "OK" or not data or data[0] is None:
                    continue
                raw = data[0][1]
                try:
                    parsed = _parse_message(raw)
                except Exception:
                    continue
                entries.append((category, uid, parsed))
                uids_to_mark.append(uid)

        if not entries:
            return "本周暂无符合条件的未读邮件。"

        # 生成 / 追加每周摘要文件
        today = date.today()
        iso = today.isocalendar()
        week = f"{iso[0]}-W{iso[1]:02d}"
        digest_file = INBOX / f"邮箱alerts_{week}.md"
        INBOX.mkdir(parents=True, exist_ok=True)

        header = [
            f"# 邮箱 Alerts 摘要 {week}",
            "",
            f"> 抓取时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}；窗口：最近 {days} 天未读邮件",
            "> 来源：Gmail IMAP（Google Scholar Alerts / arXiv / Semantic Scholar / 行业与 AI newsletter）",
            "",
        ]
        old_content = digest_file.read_text(encoding="utf-8") if digest_file.exists() else ""
        if old_content:
            parts = [old_content.rstrip(), ""]
        else:
            parts = list(header)

        order = list(grouped_uids.keys())
        for category in order:
            cat_entries = [e for e in entries if e[0] == category]
            if not cat_entries:
                continue
            parts.append(f"## {category}")
            parts.append("")
            for _cat, _uid, parsed in cat_entries:
                parts.append(f"### {parsed['date']} · {parsed['sender']}")
                parts.append(f"**{parsed['subject']}**")
                if parsed["items"]:
                    parts.append("")
                    parts.extend(parsed["items"])
                else:
                    parts.append("")
                    parts.append("- （正文未解析出链接，请到 Gmail 查看）")
                parts.append("")

        new_content = "\n".join(parts).strip() + "\n"
        digest_file.write_text(new_content, encoding="utf-8")

        # 全部写入成功后才标记已读
        if not keep_unread and uids_to_mark:
            mail.uid("store", ",".join(uids_to_mark), "+FLAGS", "(\\Seen)")

        print(f"抓取完成：{len(entries)} 封邮件，摘要文件：{digest_file}")
        return f"抓取完成：{len(entries)} 封邮件"
    except (imaplib.IMAP4.error, socket.timeout, OSError) as exc:
        sys.exit(f"Gmail IMAP 连接失败：{exc}")
    finally:
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                pass


def fetch_digest(days: int, keep_unread: bool) -> str:
    """带重试的入口：代理/网络不稳时最多尝试 3 次。"""
    last_error = "未知错误"
    for attempt in range(1, 4):
        try:
            return _run_once(days, keep_unread)
        except SystemExit as exc:
            last_error = str(exc.code)
            if attempt < 3:
                print(f"第 {attempt} 次连接失败（{last_error}），5 秒后重试……")
                time.sleep(5)
    sys.exit(f"连续 3 次连接失败：{last_error}")


def main():
    load_env()
    parser = argparse.ArgumentParser(description="抓取 Gmail alerts 并生成 Markdown 摘要")
    parser.add_argument("--days", type=int, default=3, help="抓取最近 N 天（默认 3）")
    parser.add_argument("--keep-unread", action="store_true", help="处理完不标记已读")
    args = parser.parse_args()
    print(fetch_digest(args.days, args.keep_unread))


if __name__ == "__main__":
    main()
