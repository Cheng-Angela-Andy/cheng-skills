---
name: wechat-to-lark
description: 微信内容 → 飞书文档。支持两种链接类型：(1) 微信公众号文章（mp.weixin.qq.com）自动抓取并格式化写入飞书；(2) 微信视频号视频（wxapp.tc.qq.com）自动转写为逐字稿写入飞书。触发词：保存到飞书、写入飞书、转写、视频转文字。即使用户只是粘贴一个微信链接，也应触发。
---

# Skill：微信内容 → 飞书文档

将微信公众号文章或视频号视频一键转化为飞书文档。根据链接类型自动选择提取方案。

## 触发条件

当用户发送以下任一类型的链接时自动触发：

| 链接类型 | 域名特征 | 处理方案 |
|---------|---------|---------|
| 公众号文章 | `mp.weixin.qq.com` | 方案 A：Playwright 抓取网页 |
| 视频号视频 | `wxapp.tc.qq.com` | 方案 B：Fun-ASR 语音转写 |

## 方案 A：公众号文章提取

### A1. 抓取文章内容

**首选：Playwright 无头浏览器**

```python
python3 << 'PYEOF'
import asyncio
from playwright.async_api import async_playwright

async def fetch_and_convert():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="zh-CN"
        )
        page = await context.new_page()
        await page.goto("文章URL", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # 检查安全验证
        content = await page.content()
        if "环境异常" in content or "去验证" in content:
            print("STATUS: SECURITY_BLOCK")
            await browser.close()
            return

        # 提取元数据
        title_el = await page.query_selector("#activity-name")
        title = (await title_el.inner_text()).strip() if title_el else ""

        author_el = await page.query_selector("#js_name")
        author = (await author_el.inner_text()).strip() if author_el else ""

        time_el = await page.query_selector("#publish_time")
        pub_time = (await time_el.inner_text()).strip() if time_el else ""

        # 用 JS 提取结构化内容并转为 Markdown
        md_content = await page.evaluate("""() => { /* 见下方 JS 提取逻辑 */ }""")

        print(f"TITLE: {title}")
        print(f"AUTHOR: {author}")
        print(f"TIME: {pub_time}")
        print("---CONTENT---")
        print(md_content)

        await browser.close()

asyncio.run(fetch_and_convert())
PYEOF
```

JS 提取逻辑要点：
- 从 `#js_content` 容器递归遍历 DOM 节点
- `<section>`/`<p>`/`<div>` → 段落（前后加空行）
- `<strong>`/`<b>` 或 `style="font-weight: bold"` → `**加粗**`
- `<h1>`-`<h4>` → 对应 `#`-`####` 标题
- `<img>` → `![](data-src 或 src)`，过滤 icon/emoji 类小图
- `<blockquote>` → `> 引用`
- `<a>` → `[文本](href)`
- `<code>` → `` `代码` ``，`<pre>` → 代码块
- `<li>` → `- 列表项`
- `<hr>`/`<br>` → `---`/换行
- 加粗短文本 + font-size >= 18px → `## 标题`
- 过滤 `display: none` 的隐藏元素

**备选：Chrome MCP**

如果 Playwright 不可用但 `mcp__Claude_in_Chrome` 可用：
1. `mcp__Claude_in_Chrome__navigate` 打开文章 URL
2. 等待 2-3 秒页面加载
3. `mcp__Claude_in_Chrome__get_page_text` 获取全文

**最后手段：WebFetch**

使用 WebFetch 尝试抓取。微信大概率会触发安全验证，此时告知用户。

### A2. 提取结构化内容

| 字段 | 说明 | 必需 |
|------|------|------|
| 标题 | 文章主标题 | ✅ |
| 作者/公众号名称 | 来源信息 | 尽量提取 |
| 发布时间 | 原文发布日期 | 尽量提取 |
| 正文 | 完整文章内容 | ✅ |

**必须过滤掉的内容：**
- 页脚导航、"阅读原文"链接
- 广告、推广内容、公众号关注引导
- 文末投票、评论区、"点赞、在看、转发"引导语
- 微信平台 UI 元素

### A3. 格式化为 Markdown

**文档头部：**
```markdown
> 来源：[公众号名称](原文URL) | 作者：xxx | 发布时间：xxxx-xx-xx

---
```

**正文规则：**
- 段落之间一个空行，保持段落完整性
- 文章大标题不在正文中重复（已作为飞书文档标题）
- 原文一级小标题 → `## 标题`，二级 → `### 标题`，最多 `####`
- 加粗 → `**文本**`，斜体 → `*文本*`
- 图片 → `![](图片URL)`，去除装饰性图片
- 引用 → `> 引用文本`
- 超链接保留：`[文本](URL)`
- emoji 和特殊符号原样保留

### A4. 排版质检

写入飞书前检查：
1. 标题层级合理，不跳级
2. 段落之间有且仅有一个空行
3. 无残留噪音（广告、关注引导等）
4. 格式一致，图片合理
5. 来源信息完整

---

## 方案 B：视频号语音转写

### B1. 提交 Fun-ASR 云端转写

运行转写脚本，直接将视频 URL 提交给阿里云 DashScope Fun-ASR API（零下载）：

```bash
python3 ~/.agents/skills/wechat-to-lark/scripts/transcribe.py "视频URL"
```

脚本输出 JSON：`{"ok": true, "text": "转写文本...", "elapsed": 19.5}`

如果失败，检查 stderr 中的错误信息并告知用户。

### B2. 文字修订

对转写文案进行轻度修订：

**只改这些：**
- 错别字（语音转文字导致的同音错字）
- 明显的标点符号错误
- 语音识别乱码或无意义片段
- 末尾的广告推荐、关注引导等非正文内容

**不要改这些：**
- 正常的口语化表达和语气词
- 作者的个人用语风格
- 段落结构和叙事顺序
- 观点和事实陈述

**段落整理：**
- Fun-ASR 返回整段连续文字，需按语义切分为自然段落
- 每段之间一个空行

### B3. 生成标题

根据文案内容生成简洁有吸引力的标题。

---

## 通用步骤：写入飞书文档

两步法创建（避免大文档 async 超时）：

```bash
# 1. 用 Write 工具将内容写入 ~/feishu_article.md，占位内容写入 ~/feishu_mini.md

# 2. 创建占位文档
lark-cli docs +create --title "标题" --markdown @feishu_mini.md

# 3. 用完整内容覆盖
lark-cli docs +update --doc "{doc_id}" --mode overwrite --markdown @feishu_article.md

# 4. 清理临时文件
rm -f ~/feishu_article.md ~/feishu_mini.md
```

注意：
- `--markdown` 使用 `@文件名` 语法传入，文件名必须是相对路径
- 临时文件写到用户主目录 `~/`，用完即删
- 如果 lark-cli 返回 `"status": "running"` 和 `task_id`，再执行一次同样的命令即可获取最终结果

## 返回结果

**公众号文章：**
```
已创建飞书文档：
标题：《文章标题》
来源：公众号名称
链接：https://xxx.feishu.cn/docx/xxx
```

**视频号视频：**
```
已创建飞书文档：
标题：《文章标题》
转写耗时：XX 秒
链接：https://xxx.feishu.cn/docx/xxx
```

## 错误处理

| 情况 | 处理方式 |
|------|---------|
| Playwright 遇到安全验证 | 告知用户，尝试 Chrome MCP 方案 |
| Chrome MCP 不可用 | 自动使用 Playwright 方案（首选） |
| Fun-ASR 转写失败 | 检查 DASHSCOPE_API_KEY，告知用户 |
| lark-cli 未配置 | 提示运行 `lark-cli config init --new` 和 `lark-cli auth login --recommend` |
| 文章/视频内容为空 | 告知用户具体情况 |
| 写入飞书失败 | 检查 lark-cli 登录状态，提示重新 `lark-cli auth login` |

## 依赖

- Python 3 + Playwright（`pip3 install playwright && python3 -m playwright install chromium`）
- Python 3 + dashscope SDK（视频号转写）
- 环境变量 DASHSCOPE_API_KEY（阿里云百炼 API Key）
- lark-cli（飞书命令行工具，已登录）
