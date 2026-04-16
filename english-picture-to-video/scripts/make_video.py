#!/usr/bin/env python3
"""
English Passage → Educational Video (v3)
Phases: refs | images | video
Usage:
  python3 make_video.py <output_dir> --json <scenes.json> --phase refs
  python3 make_video.py <output_dir> --json <scenes.json> --phase images
  python3 make_video.py <output_dir> --json <scenes.json> --phase video
  python3 make_video.py <output_dir> --json <scenes.json> --phase all
"""

import asyncio, json, os, subprocess, sys, urllib.request, textwrap, random
from PIL import Image, ImageDraw, ImageFont

CANVAS_W, CANVAS_H = 1920, 1080
FPS = 25
TTS_VOICE  = "en-US-JennyNeural"
TTS_RATE   = "-8%"
DRM_MODEL  = "5.0"
DRM_RES    = "2k"

STYLE_SUFFIX = (
    "semi-realistic comic art style, detailed expressive linework, "
    "vibrant rich colors, dynamic cinematic composition, dramatic lighting, "
    "high quality digital illustration, detailed background, "
    "inspired by Disney and Pixar visual storytelling"
)

# Ken Burns zoom/pan patterns (cycled per scene for variety)
KB_PATTERNS = [
    # zoom in from center
    lambda d: f"scale=2400:1350,zoompan=z='min(zoom+0.0015,1.5)':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',scale={CANVAS_W}:{CANVAS_H},setsar=1",
    # zoom out from center
    lambda d: f"scale=2400:1350,zoompan=z='if(lte(zoom,1.0),1.5,max(zoom-0.0015,1.0))':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',scale={CANVAS_W}:{CANVAS_H},setsar=1",
    # pan left to right, slight zoom
    lambda d: f"scale=2400:1350,zoompan=z='1.2':d={d}:x='if(lte(on,1),0,x+1.5)':y='ih/2-(ih/zoom/2)',scale={CANVAS_W}:{CANVAS_H},setsar=1",
    # pan right to left, slight zoom
    lambda d: f"scale=2400:1350,zoompan=z='1.2':d={d}:x='if(lte(on,1),iw-iw/zoom,max(x-1.5,0))':y='ih/2-(ih/zoom/2)',scale={CANVAS_W}:{CANVAS_H},setsar=1",
    # zoom in from bottom-left (for drama)
    lambda d: f"scale=2400:1350,zoompan=z='min(zoom+0.002,1.6)':d={d}:x='0':y='ih-(ih/zoom)',scale={CANVAS_W}:{CANVAS_H},setsar=1",
]


# ── dreamina helpers ──────────────────────────────────────────────────────────

def _fetch_url(url, path):
    urllib.request.urlretrieve(url, path)
    return path

def run_t2i(prompt, out_path, ratio="16:9"):
    if os.path.exists(out_path):
        return out_path
    r = subprocess.run(
        ["dreamina", "text2image",
         f"--prompt={prompt}", f"--ratio={ratio}",
         f"--model_version={DRM_MODEL}", f"--resolution_type={DRM_RES}",
         "--poll=90"],
        capture_output=True, text=True, timeout=130)
    if r.returncode != 0:
        print(f"  [T2I ERR] {r.stderr[-150:]}", file=sys.stderr); return None
    try:
        url = json.loads(r.stdout)["result_json"]["images"][0]["image_url"]
        return _fetch_url(url, out_path)
    except Exception as e:
        print(f"  [T2I PARSE] {e}", file=sys.stderr); return None

def run_i2i(ref, prompt, out_path, ratio="16:9"):
    if os.path.exists(out_path):
        return out_path
    r = subprocess.run(
        ["dreamina", "image2image",
         f"--images={ref}", f"--prompt={prompt}", f"--ratio={ratio}",
         f"--model_version={DRM_MODEL}", f"--resolution_type={DRM_RES}",
         "--poll=90"],
        capture_output=True, text=True, timeout=130)
    if r.returncode != 0:
        print(f"  [I2I ERR fallback t2i]", file=sys.stderr)
        return run_t2i(prompt, out_path, ratio)
    try:
        url = json.loads(r.stdout)["result_json"]["images"][0]["image_url"]
        return _fetch_url(url, out_path)
    except Exception as e:
        print(f"  [I2I PARSE] {e}", file=sys.stderr)
        return run_t2i(prompt, out_path, ratio)


# ── TTS ───────────────────────────────────────────────────────────────────────

async def tts(text, path):
    if os.path.exists(path): return
    import edge_tts
    await edge_tts.Communicate(text, voice=TTS_VOICE, rate=TTS_RATE).save(path)

def get_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path], capture_output=True, text=True)
    return float(json.loads(r.stdout)["format"]["duration"])


# ── subtitle burn ─────────────────────────────────────────────────────────────

def burn_subtitle(img_path, text, out_path):
    img = Image.open(img_path).convert("RGB").resize(
        (CANVAS_W, CANVAS_H), Image.LANCZOS)
    font = None
    for fp in ["/System/Library/Fonts/Helvetica.ttc",
               "/System/Library/Fonts/Arial.ttf",
               "/Library/Fonts/Arial.ttf",
               "/System/Library/Fonts/Supplemental/Arial.ttf"]:
        if os.path.exists(fp):
            try: font = ImageFont.truetype(fp, 40); break
            except: pass
    if not font: font = ImageFont.load_default()

    lines = textwrap.wrap(text, width=56)
    lh = 50
    total_h = lh * len(lines) + 24
    y0 = CANVAS_H - total_h - 40

    bg = Image.new("RGBA", (CANVAS_W, total_h + 16), (0, 0, 0, 175))
    rgba = img.convert("RGBA")
    rgba.alpha_composite(bg, (0, y0 - 8))
    img = rgba.convert("RGB")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        y = y0 + i * lh
        bb = draw.textbbox((0, 0), line, font=font)
        x = (CANVAS_W - (bb[2] - bb[0])) // 2
        for dx, dy in [(-2,0),(2,0),(0,-2),(0,2),(-2,-2),(2,2)]:
            draw.text((x+dx, y+dy), line, font=font, fill=(0,0,0))
        draw.text((x, y), line, font=font, fill=(255,255,255))
    img.save(out_path, "JPEG", quality=95)


# ── video: per-scene clip + concat ───────────────────────────────────────────

def make_scene_clip(img_path, audio_path, out_path, kb_pattern_fn, duration):
    """Generate one scene clip: Ken Burns image + audio."""
    n_frames = int(duration * FPS) + 2
    vf = kb_pattern_fn(n_frames)
    r = subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(duration + 0.1), "-i", img_path,
        "-i", audio_path,
        "-vf", vf,
        "-r", str(FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        out_path
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [CLIP ERR] {r.stderr[-300:]}", file=sys.stderr)
        return False
    return True

def concat_clips(clip_paths, out_path):
    """Concatenate individual scene clips into final video."""
    list_file = out_path.replace(".mp4", "_list.txt")
    with open(list_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
    r = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy", out_path
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [CONCAT ERR] {r.stderr[-300:]}", file=sys.stderr)
        return False
    os.remove(list_file)
    return True


# ── phases ────────────────────────────────────────────────────────────────────

def phase_refs(plan, ref_dir, char_refs, loc_refs):
    characters = plan.get("characters", [])
    locations  = plan.get("locations", [])

    print(f"\n=== [Phase: refs] Character sheets ({len(characters)}) ===")
    for c in characters:
        path = os.path.join(ref_dir, f"char_{c['name'].lower().replace(' ','_')}.jpg")
        prompt = f"{c['ref_prompt']}, {STYLE_SUFFIX}"
        print(f"  {c['name']}...")
        run_t2i(prompt, path, ratio="3:2")
        char_refs[c["name"]] = path
        print(f"  → {path}")

    print(f"\n=== [Phase: refs] Location refs ({len(locations)}) ===")
    for l in locations:
        path = os.path.join(ref_dir, f"loc_{l['name'].lower().replace(' ','_')}.jpg")
        prompt = f"{l['ref_prompt']}, {STYLE_SUFFIX}"
        print(f"  {l['name']}...")
        run_t2i(prompt, path, ratio="16:9")
        loc_refs[l["name"]] = path
        print(f"  → {path}")


async def phase_images(plan, audio_dir, img_dir, char_refs, loc_refs):
    scenes = plan["scenes"]

    print(f"\n=== [Phase: images] TTS ({len(scenes)} scenes) ===")
    for i, s in enumerate(scenes, 1):
        p = os.path.join(audio_dir, f"s{i:02d}.mp3")
        await tts(s["text"], p)
        print(f"  [{i:02d}] ok")

    print(f"\n=== [Phase: images] Scene images ({len(scenes)}) ===")
    for i, s in enumerate(scenes, 1):
        out = os.path.join(img_dir, f"s{i:02d}.jpg")
        ref_name = s.get("char_ref") or s.get("loc_ref")
        ref_path = char_refs.get(ref_name) or loc_refs.get(ref_name)
        full_prompt = f"{s['prompt']}, {STYLE_SUFFIX}"

        if ref_path and os.path.exists(ref_path):
            print(f"  [{i:02d}] i2i ref={ref_name}...")
            run_i2i(ref_path, full_prompt, out)
        else:
            print(f"  [{i:02d}] t2i...")
            run_t2i(full_prompt, out)
        print(f"        → {out}")


def phase_video(plan, audio_dir, img_dir, sub_dir, clips_dir, final_dir):
    scenes = plan["scenes"]

    print(f"\n=== [Phase: video] Burn subtitles ===")
    for i, s in enumerate(scenes, 1):
        burn_subtitle(
            os.path.join(img_dir, f"s{i:02d}.jpg"),
            s["text"],
            os.path.join(sub_dir, f"s{i:02d}.jpg"))
        print(f"  [{i:02d}] done")

    print(f"\n=== [Phase: video] Build scene clips with Ken Burns ===")
    clip_paths = []
    for i, s in enumerate(scenes, 1):
        img_p   = os.path.join(sub_dir,   f"s{i:02d}.jpg")
        audio_p = os.path.join(audio_dir, f"s{i:02d}.mp3")
        clip_p  = os.path.join(clips_dir, f"clip_{i:02d}.mp4")
        dur = get_duration(audio_p)
        kb_fn = KB_PATTERNS[i % len(KB_PATTERNS)]
        ok = make_scene_clip(img_p, audio_p, clip_p, kb_fn, dur)
        print(f"  [{i:02d}] {dur:.1f}s → {'ok' if ok else 'FAIL'}")
        if ok:
            clip_paths.append(clip_p)

    print(f"\n=== [Phase: video] Concatenate {len(clip_paths)} clips ===")
    final = os.path.join(final_dir, "english_lesson.mp4")
    ok = concat_clips(clip_paths, final)
    if ok:
        print(f"\n✅  {final}")
        subprocess.run(["open", final])
    else:
        print("❌ Concat failed")


# ── main ──────────────────────────────────────────────────────────────────────

async def main():
    args = sys.argv[1:]
    if len(args) < 4:
        print("Usage: make_video.py <out_dir> --json <scenes.json> --phase <refs|images|video|all>")
        sys.exit(1)

    out_dir    = args[0]
    plan_file  = args[2]
    phase      = args[4] if len(args) > 4 else "all"

    with open(plan_file) as f:
        plan = json.load(f)

    ref_dir   = os.path.join(out_dir, "references")
    audio_dir = os.path.join(out_dir, "audio")
    img_dir   = os.path.join(out_dir, "images")
    sub_dir   = os.path.join(out_dir, "images_sub")
    clips_dir = os.path.join(out_dir, "clips")
    final_dir = os.path.join(out_dir, "final")
    for d in [ref_dir, audio_dir, img_dir, sub_dir, clips_dir, final_dir]:
        os.makedirs(d, exist_ok=True)

    char_refs, loc_refs = {}, {}
    # pre-load existing refs
    for c in plan.get("characters", []):
        p = os.path.join(ref_dir, f"char_{c['name'].lower().replace(' ','_')}.jpg")
        if os.path.exists(p): char_refs[c["name"]] = p
    for l in plan.get("locations", []):
        p = os.path.join(ref_dir, f"loc_{l['name'].lower().replace(' ','_')}.jpg")
        if os.path.exists(p): loc_refs[l["name"]] = p

    if phase in ("refs", "all"):
        phase_refs(plan, ref_dir, char_refs, loc_refs)

    if phase in ("images", "all"):
        await phase_images(plan, audio_dir, img_dir, char_refs, loc_refs)

    if phase in ("video", "all"):
        phase_video(plan, audio_dir, img_dir, sub_dir, clips_dir, final_dir)

    if phase not in ("refs", "images", "video", "all"):
        print(f"Unknown phase: {phase}. Use refs|images|video|all")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
