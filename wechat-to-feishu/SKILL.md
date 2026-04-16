---
name: wechat-to-feishu
description: 当用户发送微信公众号文章链接（mp.weixin.qq.com 开头的 URL）时，使用此 skill 自动提取文章内容并写入飞书文档。适用场景：用户说"把这篇文章写入飞书"、"保存到飞书文档"、"帮我把公众号文章存到飞书"，或者直接粘贴一个 mp.weixin.qq.com 链接并表示想保存。即使用户只是说"保存这篇文章"或"存到飞书"，只要有微信公众号链接，也应该触发此 skill。
---

# 微信公众号文章 → 飞书文档

将微信公众号文章一键抓取、格式化为高质量 Markdown，并写入飞书个人文档库。

## 工作流程

### 第一步：抓取文章内容

**方案 A（首选）：Playwright 无头浏览器**

使用 Python Playwright 抓取文章，可绕过微信安全验证，无需额外 MCP 工具：

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

**方案 B（备选）：Chrome MCP**

如果 Playwright 不可用但 `mcp__Claude_in_Chrome` 可用：

1. `mcp__Claude_in_Chrome__navigate` 打开文章 URL
2. 等待 2-3 秒页面加载
3. `mcp__Claude_in_Chrome__get_page_text` 获取全文
4. 如果页面出现"环境异常"或"去验证"，告知用户在浏览器中手动验证后重试

**方案 C（最后手段）：WebFetch**

如果以上方案都不可用，使用 WebFetch 尝试抓取。微信大概率会触发安全验证，此时告知用户。

### 第二步：提取结构化内容

从页面中提取以下信息：

| 字段 | 说明 | 必需 |
|------|------|------|
| 标题 | 文章主标题 | ✅ |
| 作者/公众号名称 | 来源信息 | 尽量提取 |
| 发布时间 | 原文发布日期 | 尽量提取 |
| 正文 | 完整文章内容 | ✅ |

**必须过滤掉的内容：**
- 页脚导航、"阅读原文"链接
- 广告、推广内容
- 公众号关注引导（"点击关注"、"星标"等）
- 文末投票、评论区
- 微信平台 UI 元素（分享按钮等）
- 文末的"点赞、在看、转发"引导语

### 第三步：格式化为高质量 Markdown

按照以下规范将正文转化为飞书兼容的 Markdown：

#### 3.1 文档头部

```markdown
> 来源：[公众号名称](原文URL) | 作者：xxx | 发布时间：xxxx-xx-xx

---
```

#### 3.2 正文格式化规则

**段落：**
- 每个段落之间用一个空行分隔
- 不要在段落内部随意换行，保持段落完整性
- 连续的短句如果在原文中是同一段落，合并为一段

**标题层级：**
- 文章大标题不在正文中重复（已作为飞书文档标题）
- 原文中的一级小标题 → `## 标题`
- 原文中的二级小标题 → `### 标题`
- 最多使用三级标题，不要超过 `####`

**强调：**
- 加粗 → `**文本**`
- 斜体 → `*文本*`
- 不要过度使用加粗，只保留原文中确实有强调的部分

**列表：**
- 有序列表用 `1. 2. 3.`
- 无序列表用 `-`
- 嵌套列表缩进 2 个空格

**图片：**
- 格式：`![](图片URL)`
- 如果图片有说明文字，放在图片下方作为普通文本
- 去除装饰性图片（分隔线图片、表情包等非内容图片）

**引用：**
- 原文中的引用内容 → `> 引用文本`
- 不要把普通段落变成引用

**代码：**
- 行内代码 → `` `代码` ``
- 代码块 → 用 ``` 包裹并标注语言

**表格：**
- 如果原文有表格，使用标准 Markdown 表格语法
- 确保表头对齐

**特殊处理：**
- 原文中的分隔线 → `---`
- 原文中的超链接保留：`[文本](URL)`
- emoji 和特殊符号原样保留

### 第四步：排版质检

在写入飞书之前，对生成的 Markdown 执行以下质检：

**质检 Checklist：**

1. **结构清晰**：标题层级合理，不跳级（如 ## 后直接跟 ####）
2. **段落分明**：段落之间有且仅有一个空行，没有多余空行堆积
3. **无残留噪音**：没有"阅读原文"、广告文案、关注引导等
4. **格式一致**：加粗、列表、引用等格式统一，没有混用
5. **图片合理**：内容图片保留，装饰图片去除
6. **来源完整**：文档头部有来源、作者、时间信息
7. **可读性好**：通读一遍，确认排版流畅自然，不会让读者觉得混乱

**如果发现问题，先修正再写入。**

### 第五步：写入飞书文档

将 Markdown 内容用 Write 工具写入用户主目录下的临时文件，再调用 lark-cli 创建文档：

```bash
# 用 Write 工具将格式化好的 Markdown 写入 ~/feishu_article.md

# 创建飞书文档（使用 @file 语法传入，路径必须是相对路径）
lark-cli docs +create \
  --title "文章标题" \
  --markdown @feishu_article.md

# 如果返回 task_id 且 status 为 running，再次执行相同命令即可轮询获取结果

# 清理临时文件
rm -f ~/feishu_article.md
```

注意：
- **不要用 `--wiki-space my_library`**，直接创建到个人文档空间即可
- `--markdown` 使用 `@文件名` 语法传入，文件名必须是相对路径
- 临时文件写到用户主目录 `~/feishu_article.md`，用完即删
- 如果 lark-cli 返回 `"status": "running"` 和 `task_id`，再执行一次同样的命令即可获取最终结果（文档 URL）

### 第六步：返回结果

lark-cli 成功后展示结果：

```
✅ 已创建飞书文档：
标题：《文章标题》
来源：公众号名称
链接：https://xxx.feishu.cn/docx/xxx
```

## 错误处理

| 情况 | 处理方式 |
|------|---------|
| Playwright 遇到安全验证 | 告知用户，尝试 Chrome MCP 方案 |
| Chrome MCP 不可用 | 自动使用 Playwright 方案（首选） |
| lark-cli 未配置 | 提示运行 `lark-cli config init --new` 和 `lark-cli auth login --recommend` |
| 文章内容为空 | 截图确认页面状态，告知用户具体情况 |
| 写入飞书失败 | 检查 lark-cli 登录状态，提示用户重新 `lark-cli auth login` |
| 网络超时 | 重试一次，失败则告知用户 |

## 依赖

- Python 3 + Playwright（`pip3 install playwright && python3 -m playwright install chromium`）
- `mcp__Claude_in_Chrome` 工具（备选方案）
- `lark-cli`（已全局安装：`npm install -g @larksuite/cli`）
- 用户已完成 `lark-cli auth login`
