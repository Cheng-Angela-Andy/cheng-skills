#!/usr/bin/env python3
"""视频号 URL → Fun-ASR 云端转写，输出纯文本"""

import sys
import time
import json
from dashscope.audio.asr import Transcription


def transcribe(video_url: str) -> str:
    """提交 Fun-ASR 转写任务并轮询结果，返回转写文本"""
    resp = Transcription.async_call(
        model="paraformer-v2",
        file_urls=[video_url],
        language_hints=["zh"],
    )

    task_id = resp.output.get("task_id")
    if not task_id:
        print(json.dumps({"ok": False, "error": "未获得 task_id", "raw": str(resp)}), file=sys.stderr)
        sys.exit(1)

    # 轮询等待完成
    start = time.time()
    while True:
        result = Transcription.fetch(task=task_id)
        status = result.output.get("task_status", "")
        if status == "SUCCEEDED":
            break
        if status == "FAILED":
            print(json.dumps({"ok": False, "error": "转写失败", "raw": str(result)}), file=sys.stderr)
            sys.exit(1)
        if time.time() - start > 300:
            print(json.dumps({"ok": False, "error": "转写超时(5分钟)"}), file=sys.stderr)
            sys.exit(1)
        time.sleep(2)

    elapsed = round(time.time() - start, 1)

    # 提取文本
    results = result.output.get("results", [])
    if not results:
        print(json.dumps({"ok": False, "error": "无转写结果"}), file=sys.stderr)
        sys.exit(1)

    transcription_url = results[0].get("transcription_url", "")
    if not transcription_url:
        print(json.dumps({"ok": False, "error": "无 transcription_url"}), file=sys.stderr)
        sys.exit(1)

    # 下载转写结果 JSON
    import urllib.request
    with urllib.request.urlopen(transcription_url) as f:
        data = json.loads(f.read())

    transcripts = data.get("transcripts", [])
    if not transcripts:
        print(json.dumps({"ok": False, "error": "transcripts 为空"}), file=sys.stderr)
        sys.exit(1)

    text = transcripts[0].get("text", "")

    output = {"ok": True, "text": text, "elapsed": elapsed}
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: transcribe.py <video_url>", file=sys.stderr)
        sys.exit(1)
    transcribe(sys.argv[1])
