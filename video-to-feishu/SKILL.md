---
name: video-to-feishu
description: 视频号链接 → 飞书文档。当用户发送一个 wxapp.tc.qq.com 域名的视频链接时自动触发。将视频号视频转写为逐字稿文案并写入飞书文档。触发词：视频号、转写、视频转文字、视频号链接。即使用户只是发了一个 wxapp.tc.qq.com 链接并说"帮我转写"或"保存到飞书"，也应触发。
---

# Skill：视频号链接 → 飞书文档

将微信视频号视频链接一键转写为逐字稿文案，并写入飞书个人文档库。全程零下载，约 30 秒完成。

## 触发条件

当用户发送一个 `wxapp.tc.qq.com` 域名的视频链接时自动触发。

## 工作流程

### 第一步：提交 Fun-ASR 云端转写

运行转写脚本，直接将视频 URL 提交给阿里云 DashScope Fun-ASR API：

```bash
python3 ~/.agents/skills/video-to-feishu/scripts/transcribe.py "视频URL"
```

脚本输出 JSON：`{"ok": true, "text": "转写文本...", "elapsed": 19.5}`

如果失败，检查 stderr 中的错误信息并告知用户。

### 第二步：文字修订

对转写文案进行轻度修订：

**只改这些：**
- 错别字（如语音转文字导致的同音错字）
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

### 第三步：生成标题

根据文案内容生成简洁有吸引力的标题。

### 第四步：写入飞书文档

两步法创建（避免大文档 async 超时）：

```bash
# 1. 将修订后的 Markdown 写入临时文件
# 用 Write 工具写入 ~/feishu_article.md

# 2. 创建占位文档
lark-cli docs +create --title "标题" --markdown @feishu_mini.md

# 3. 用完整内容覆盖
lark-cli docs +update --doc "{doc_url_or_token}" --mode overwrite --markdown @feishu_article.md

# 4. 清理临时文件
rm -f ~/feishu_article.md ~/feishu_mini.md
```

注意：
- `--markdown` 使用 `@文件名` 语法传入，文件名必须是相对路径
- 临时文件写到用户主目录 `~/`，用完即删
- 如果 lark-cli 返回 `"status": "running"` 和 `task_id`，再执行一次同样的命令即可获取最终结果

### 第五步：返回结果

展示文档标题、链接和转写耗时：

```
已创建飞书文档：
标题：《文章标题》
转写耗时：XX 秒
链接：https://xxx.feishu.cn/docx/xxx
```

## 依赖

- Python 3 + dashscope SDK
- 环境变量 DASHSCOPE_API_KEY（阿里云百炼 API Key）
- lark-cli（飞书命令行工具，已登录）
