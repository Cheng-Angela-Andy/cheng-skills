---
name: wechat-to-feishu
description: 当用户发送微信公众号文章链接（mp.weixin.qq.com 开头的 URL）时，使用此 skill 自动提取文章内容并写入飞书文档。适用场景：用户说"把这篇文章写入飞书"、"保存到飞书文档"、"帮我把公众号文章存到飞书"，或者直接粘贴一个 mp.weixin.qq.com 链接并表示想保存。即使用户只是说"保存这篇文章"或"存到飞书"，只要有微信公众号链接，也应该触发此 skill。
---

# 微信公众号文章 → 飞书文档

将微信公众号文章一键抓取并写入飞书文档。整个流程分三步：抓取 → 创建文档 → 写入内容。

---

## 第一步：抓取文章内容

微信文章直接 fetch 会被安全验证拦截，但伪装成桌面 Chrome 的普通 HTTP 请求即可绕过。用 Python 抓取并转换为 Markdown：

```python
import urllib.request, gzip, re, sys

url = "用户提供的 mp.weixin.qq.com URL"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=15) as resp:
    raw = resp.read()

try:
    html = gzip.decompress(raw).decode("utf-8", errors="ignore")
except Exception:
    html = raw.decode("utf-8", errors="ignore")
```

**提取标题**（按优先级尝试）：
```python
for pat in [
    r'<meta\s+property="og:title"\s+content="([^"]+)"',
    r'var\s+msg_title\s*=\s*"([^"]+)"',
    r'<h1[^>]*class="rich_media_title"[^>]*>\s*(.*?)\s*</h1>',
]:
    m = re.search(pat, html, re.DOTALL)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        break
else:
    title = "微信文章"
```

**提取公众号名称和日期**：
```python
author_m = re.search(r'var\s+nickname\s*=\s*"([^"]+)"', html)
author = author_m.group(1) if author_m else ""

date_m = re.search(r'var\s+ct\s*=\s*"(\d+)"', html)
if date_m:
    import datetime
    date_str = datetime.datetime.fromtimestamp(int(date_m.group(1))).strftime("%Y-%m-%d")
else:
    date_str = ""
```

**提取正文并转为 Markdown**：
```python
body_m = re.search(
    r'id=["\']js_content["\'][^>]*>(.*?)(?=<div[^>]*id=["\']js_pc_qr_code["\']|<div[^>]*class=["\']rich_media_tool)',
    html, re.DOTALL
)
body_html = body_m.group(1) if body_m else ""

def html_to_md(s):
    s = re.sub(r'<h([1-6])[^>]*>(.*?)</h\1>',
                lambda m: "\n" + "#"*int(m.group(1)) + " " + re.sub(r"<[^>]+>","",m.group(2)).strip() + "\n",
                s, flags=re.DOTALL)
    s = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', s, flags=re.DOTALL)
    s = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', s, flags=re.DOTALL)
    s = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', s, flags=re.DOTALL)
    s = re.sub(r'<br\s*/?>', '\n', s)
    s = re.sub(r'<p[^>]*>', '\n', s)
    s = re.sub(r'</p>', '\n', s)
    s = re.sub(r'<img[^>]+data-src="([^"]+)"[^>]*/?>',
                lambda m: f'![]({m.group(1)})', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = s.replace('&nbsp;',' ').replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&#39;',"'").replace('&quot;','"')
    return re.sub(r'\n{3,}', '\n\n', s).strip()

body = html_to_md(body_html)
```

**组装最终 Markdown**，写入 `/tmp/wechat_article.md`：
```python
meta_parts = [p for p in [author, date_str, url] if p]
markdown = f"> 来源：{'  ·  '.join(meta_parts)}\n\n{body}\n"
with open("/tmp/wechat_article.md", "w") as f:
    f.write(markdown)
print(f"TITLE:{title}")
```

---

## 第二步：同步创建飞书文档

用 `lark-cli api` 直接调 Feishu docx API，**同步返回 document_id**（不走异步）：

```bash
DOC_JSON=$(lark-cli api POST /open-apis/docx/v1/documents \
  --as user \
  --data "{\"title\":\"$TITLE\"}" 2>&1)

DOC_ID=$(echo "$DOC_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['document']['document_id'])")
echo "Created: $DOC_ID"
```

---

## 第三步：写入内容（等待异步完成）

`lark-cli docs +update` 是异步的，但后台实际执行很快（5-15秒）。写入后等待，再用 `+fetch` 验证：

```bash
lark-cli docs +update \
  --doc "$DOC_ID" \
  --markdown "$(cat /tmp/wechat_article.md)" \
  --mode overwrite

sleep 20

# 验证内容已写入（取前几行确认）
lark-cli docs +fetch --doc "$DOC_ID" --format pretty 2>&1 | head -5
```

---

## 第四步：返回结果

document_id 已知，直接构造飞书文档 URL：

```
https://feishu.cn/docx/{DOC_ID}
```

向用户展示：
```
✅ 已写入飞书文档：
📄 《{标题}》
🔗 https://feishu.cn/docx/{DOC_ID}
```

---

## 错误处理

| 情况 | 处理方式 |
|------|---------|
| 抓取返回"环境异常" | 极少发生，重试一次即可；仍失败则请用户复制正文粘贴给我 |
| `lark-cli api` 报权限错误 | 提示运行 `lark-cli auth login --recommend` 重新授权 |
| `+fetch` 验证内容为空 | 再等 10 秒重试 fetch；如仍为空说明 update 失败，重新执行第三步 |

## 依赖

- `lark-cli`（全局安装：`npm install -g @larksuite/cli`）
- 用户已完成飞书登录：`lark-cli auth login --recommend`
