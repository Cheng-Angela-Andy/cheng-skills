---
name: english-picture-to-video
description: |
  拍一张英语短文图片，自动生成带旁白和字幕的教育视频。
  适合小学/初中英语短文学习，把文章变成真人漫画风插图+女声朗读+字幕+动态切换的视频。
  触发词：英语视频、英文视频、生成英语视频、英语短文视频、帮我把这篇英语做成视频、英文教学视频
  即使用户只是说"帮我做成视频"并附上英语文章图片，也应触发。
permissions:
  exec:
    - python3
    - ffmpeg
    - ffprobe
    - dreamina
  file_read:
    - ~/Desktop/
    - ~/.claude/skills/english-picture-to-video/
  file_write:
    - ~/Desktop/english_lessons/
---

# English Video Skill (v3)

用户拍一张英语短文图片，输出教育视频：
- **每句话一个分镜**，不合并不省略
- **先生角色参考图 + 场景参考图**，再 image2image 保证一致性
- **真人漫画风**（semi-realistic comic art，Disney/Pixar 视觉叙事感）
- **迪士尼 IP 风格角色**，对小朋友更有吸引力
- **QC 质检环节**：我逐张审图，不合格重新生成
- **Ken Burns 动态效果**：每张图有推拉摇移，视频不呆板
- **逐场景生成视频片段再拼接**，避免后半段丢失
- **Jenny 女声旁白**（自然亲切）+ 字幕烧录，无背景音乐

## 核心脚本

```
~/.claude/skills/english-picture-to-video/scripts/make_video.py
```

三个阶段独立执行，便于 QC 插入：

```bash
# Phase 1: 生成角色/场景参考图
python3 ~/.claude/skills/english-picture-to-video/scripts/make_video.py \
  ~/Desktop/english_lessons/<dir>/ --json scenes.json --phase refs

# Phase 2: 生成分镜图 + TTS 音频
python3 ~/.claude/skills/english-picture-to-video/scripts/make_video.py \
  ~/Desktop/english_lessons/<dir>/ --json scenes.json --phase images

# Phase 3: 合成视频（字幕+Ken Burns+拼接）
python3 ~/.claude/skills/english-picture-to-video/scripts/make_video.py \
  ~/Desktop/english_lessons/<dir>/ --json scenes.json --phase video
```

---

## 完整工作流程

### Step 1：从图片提取英文短文

提取完整英文正文，跳过中文注释、二维码、页码。文字模糊时先确认再继续。

---

### Step 2：人物与场景分析

识别所有角色（姓名、外貌、服装）和场景地点。

---

### Step 3：专业分镜规划

**核心原则：每一个完整句子 = 一个分镜，宁多勿少。**

- 对话句单独成镜，突出说话人表情和动作
- 转折/高潮用特写或戏剧性构图
- 每个分镜 prompt 写明：人物动作、表情、镜头角度、光线氛围
- 避免空镜：每帧必须有吸引眼球的元素（表情、动作、道具、环境细节）

---

### Step 4：生成 scenes.json

**角色描述要求（提升吸引力）：**
- 参考具体迪士尼 IP 角色的外貌风格（如"inspired by Anna from Frozen"）
- 每个场景 prompt 必须重复完整外貌描述，不能只写名字
- 服装、发色、眼睛颜色每次都写

**prompt 质量要求：**
- 明确构图：close-up / medium shot / wide shot / low angle / bird's eye view
- 明确光线：golden hour / dramatic side lighting / soft morning light
- 明确情绪：exaggerated surprise / warm heartfelt / energetic dynamic
- 避免模糊词：不写"a scene of..." 要直接描述画面

**JSON 格式：**

```json
{
  "characters": [
    {
      "name": "Mandy",
      "description": "12-year-old girl inspired by Anna from Frozen: chestnut-brown hair in two braids, bright teal eyes, rosy cheeks, wearing light blue PE uniform with white stripes, energetic cheerful expression",
      "ref_prompt": "Character turnaround sheet, 12-year-old girl inspired by Anna from Frozen, chestnut-brown hair in two braids, bright teal eyes, rosy cheeks, light blue PE uniform with white stripes, full body front / 3/4 / side view, white background"
    }
  ],
  "locations": [
    {
      "name": "sports field",
      "description": "Sunny school sports field, green grass, red running track, bright blue sky",
      "ref_prompt": "Establishing shot, sunny school sports field, lush green grass, red running track, white goal posts, blue sky, no characters"
    }
  ],
  "scenes": [
    {
      "text": "Mandy and Sandy are twin sisters.",
      "prompt": "Wide shot, two identical 12-year-old girls inspired by Anna from Frozen with chestnut-brown braids and teal eyes, wearing matching light blue PE uniforms, arms around each other smiling warmly at camera, sunny outdoor background, vibrant warm colors",
      "char_ref": "Mandy",
      "loc_ref": null
    }
  ]
}
```

---

### Step 5：Phase 1 — 生成参考图

运行 `--phase refs`，生成：
- 每个角色的三视图参考图
- 每个场景的环境参考图

---

### Step 6：Phase 2 — 生成分镜图（含 TTS）

运行 `--phase images`，每个场景用 image2image 以参考图为底生图。

---

### ⚠️ Step 7：QC 质检（关键步骤）

**在运行 Phase 3 之前，我必须逐张审阅所有分镜图。**

用 Read 工具逐张查看 `images/s01.jpg` 到 `images/sNN.jpg`。

**QC 判断标准：**

| 检查项 | 合格标准 | 不合格处理 |
|--------|---------|-----------|
| 内容连贯性 | 画面内容与 text 对应 | 用更具体 prompt 重新生成 |
| 元素丰富度 | 有角色、动作、背景细节 | 在 prompt 加更多具体元素重生 |
| 空镜检查 | 不能只有背景无角色 | 必须重生 |
| 角色一致性 | 主要角色外貌前后一致 | 重生时加强外貌描述 |
| 画面吸引力 | 有看点，不呆板 | 换构图重生 |

**重新生成单张图：**
```bash
dreamina image2image \
  --images=~/Desktop/english_lessons/<dir>/references/char_XX.jpg \
  --prompt="<改进后的详细 prompt>, semi-realistic comic art style..." \
  --ratio=16:9 --model_version=5.0 --resolution_type=2k --poll=90
```
下载后覆盖对应 `images/sNN.jpg`。

所有图 QC 通过后，继续 Phase 3。

---

### Step 8：Phase 3 — 合成视频

运行 `--phase video`：
- PIL 字幕烧录
- 每场景独立 Ken Burns 动效（推/拉/摇，循环多种模式）
- 每场景生成独立视频片段
- FFmpeg concat 拼接成最终 MP4
- 自动打开

---

## 注意事项

- **Jenny 声音**：当前 `TTS_VOICE = "en-US-JennyNeural"`，自然亲切
- **Ken Burns**：5 种动效模式按场景序号循环，视频不单调
- **逐片段拼接**：彻底解决后半段丢失问题
- **即梦会员**：生图不扣积分，放心使用
- **输出目录**：`~/Desktop/english_lessons/<短文名>/final/english_lesson.mp4`
