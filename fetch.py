import os, json, base64, subprocess, datetime, requests
from pathlib import Path

CAMS = {
  "kobe_maiko": "W5iKrSNyJhQ",
  "kobe_airport": "dpVyxSYsVs0",
}

Path("images").mkdir(exist_ok=True)

def fetch_still(video_id, out_path):
    try:
        result = subprocess.run(
            ["yt-dlp", "-g", f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=60
        )
        stream_url = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        if stream_url:
            subprocess.run(
                ["ffmpeg", "-y", "-i", stream_url, "-vframes", "1", "-q:v", "3", out_path],
                capture_output=True, timeout=60
            )
            if Path(out_path).exists() and Path(out_path).stat().st_size > 10000:
                print(f"ffmpeg ok: {video_id}")
                return True
    except Exception as e:
        print(f"ffmpeg fail {video_id}: {e}")
    thumb = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    try:
        r = requests.get(thumb, timeout=20)
        if r.status_code == 200 and len(r.content) > 10000:
            Path(out_path).write_bytes(r.content)
            print(f"thumb ok: {video_id}")
            return True
    except Exception as e:
        print(f"thumb fail {video_id}: {e}")
    return False

def generate_poem(image_path):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "空が、そっと息をしている。", "fallback"
    try:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        prompt = """この画像は日本のライブカメラの空と風景です。画像をよく見て、中原中也風の詩を日本語で3行作ってください。
条件:
- 1行目は空や雲や光の様子を具体的に
- 2行目は風や音や気配を感じる言葉を
- 3行目は少し寂しく、でも温かい余韻で終わる
- 天気の言葉（晴れ・曇り・雨・風など）を1つだけ入れる
- 説明文やタイトルは不要、詩の3行だけを返す
"""
        payload = {
            "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 300}
        }
        r = requests.post(url, json=payload, timeout=60)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        lines = [l.strip() for l in text.splitlines() if l.strip()][:3]
        while len(lines) < 3:
            lines.append("")
        return "\n".join(lines), "gemini-2.0-flash"
    except Exception as e:
        print(f"gemini fail: {e}")
        return "空が、そっと息をしている。\n風は、遠くで何かを運んでくる。\n今日も、ここで生きている。", "fallback"

def main():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
    data = {"updated_at": now, "locations": {}}
    if Path("data.json").exists():
        try:
            old = json.loads(Path("data.json").read_text(encoding="utf-8"))
            data = old
            data["updated_at"] = now
        except:
            pass
    for key, vid in CAMS.items():
        out = f"images/{key}.jpg"
        ok = fetch_still(vid, out)
        poem, model = generate_poem(out) if ok else ("空が、そっと息をしている。\n風は、遠くで何かを運んでくる。\n今日も、ここで生きている。", "fallback")
        data["locations"][key] = {"video_id": vid, "image": out, "poem": poem, "model": model, "updated_at": now}
        print(f"{key}: {poem[:20]}")
    Path("data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
