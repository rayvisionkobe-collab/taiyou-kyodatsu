import os, json, base64, subprocess, datetime, requests, re
from pathlib import Path

Path("images").mkdir(exist_ok=True)

def load_locations():
    try:
        cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))
        return cfg.get("locations", [])
    except Exception as e:
        print(f"config load fail: {e}")
        return [{"id":"maiko","name":"舞子ビラ","video_id":"W5iKrSNyJhQ"}]

def fetch_still(video_id, out_path):
    # 1) YouTube ライブサムネイル (数秒おきに更新される) を最優先 - ffmpegより確実で速い
    for q in ["hqdefault_live", "maxresdefault_live", "hqdefault", "maxresdefault"]:
        try:
            url = f"https://i.ytimg.com/vi/{video_id}/{q}.jpg"
            r = requests.get(url, timeout=15)
            # ライブサムネイルは 404 だと小さいグレーの画像 (約1-2KB) が返るので、サイズで判定
            if r.status_code == 200 and len(r.content) > 8000:
                Path(out_path).write_bytes(r.content)
                print(f"live-thumb ok {video_id} {q} {len(r.content)} bytes")
                return "live-thumb"
            else:
                print(f"live-thumb skip {video_id} {q} status={r.status_code} size={len(r.content) if r.status_code==200 else 0}")
        except Exception as e:
            print(f"live-thumb fail {video_id} {q}: {e}")
    # 2) yt-dlp + ffmpeg を試す (本物の動画フレーム)
    for fmt in ["bv*[height<=720]+ba/b[height<=720]/best", "best[height<=720]", "best"]:
        try:
            result = subprocess.run(["yt-dlp","-g","-f",fmt, f"https://www.youtube.com/watch?v={video_id}"], capture_output=True, text=True, timeout=35)
            urls = [u.strip() for u in result.stdout.strip().splitlines() if u.strip().startswith("http")]
            if not urls:
                continue
            stream_url = urls[0]
            r = subprocess.run(["ffmpeg","-y","-i",stream_url,"-vframes","1","-q:v","3",out_path], capture_output=True, timeout=35)
            if Path(out_path).exists() and Path(out_path).stat().st_size > 8000:
                print(f"ffmpeg ok {video_id} fmt={fmt}")
                return "live"
        except Exception as e:
            print(f"ffmpeg try {fmt} fail {video_id}: {e}")
            continue
    return None

def fallback_poems(place_name):
    # Geminiが失敗しても、場所・詩人・濃さで全て違う詩になるフォールバック
    return {
        "kyodatsu": {
            "0": f"{place_name}の空は、今日も静かだ。",
            "1": f"{place_name}の空は、今日も静かだ。\n風が、遠くで何かを運んでくる。",
            "2": f"{place_name}の空は、今日も静かだ。\n風が、遠くで何かを運んでくる。\n曇りの午後、どこへも行けず、空だけが遠くへ行く。",
            "3": f"{place_name}の空は、今日も静かだ。風が、遠くで何かを運んでくる。曇りの午後、どこへも行けず、空だけが遠くへ行ってしまうような、虚脱の午後だった。"
        },
        "taiyou": {
            "0": f"{place_name}に、光が落ちている。",
            "1": f"{place_name}に、光が落ちている。\n海の向こうで、風が渡ろうとしている。",
            "2": f"{place_name}に、光が落ちている。\n海の向こうで、風が渡ろうとしている。\n晴れの光が、今日の空を包んでいる。",
            "3": f"{place_name}に、光が落ちている。海の向こうで、風が渡ろうとしている。晴れの光が、樹々を照らし、すべての存在を光に包むような、太陽の涙の午後だった。"
        }
    }

def generate_poems(image_path, place_name):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return fallback_poems(place_name), "fallback-no-key"
    try:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        # fallback model if 2.0 fails
        fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        prompt = f"""この画像は日本の{place_name}のライブカメラです。画像をよく見て、2人の詩人の詩をJSONで作ってください。
返答はJSONだけ、説明文なしで。
形式:
{{"kyodatsu": {{"0":"1行","1":"2行（改行で区切る）","2":"3行","3":"長めの1段落"}}, "taiyou": {{"0":"1行","1":"2行","2":"3行","3":"長めの1段落"}}}}
条件:
- kyodatsuは中原中也風、少し寂しく温かい余韻
- taiyouは宮沢賢治風、光と風と宇宙を感じる
- 各詩に天気の言葉（晴れ・曇り・雨・風・雪など）を1つだけ入れる
- 場所名「{place_name}」を各詩に1回は入れる
- 0は短く事実的、1は比喩少し、2は主観濃く、3は長く解体的
"""
        payload = {"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":"image/jpeg","data":b64}}]}], "generationConfig":{"temperature":0.9,"maxOutputTokens":1200,"response_mime_type":"application/json"}}
        r = requests.post(url, json=payload, timeout=90)
        if r.status_code != 200:
            print(f"gemini 2.0 status {r.status_code}, try 1.5")
            # JSON mode may not be supported on 1.5, so remove response_mime_type
            payload2 = dict(payload); payload2.pop("generationConfig", None); payload2["generationConfig"]={"temperature":0.9,"maxOutputTokens":1200}
            r = requests.post(fallback_url, json=payload2, timeout=90)
        r.raise_for_status()
        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        # JSON抽出
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            txt = m.group(0)
        data = json.loads(txt)
        # バリデーション
        if "kyodatsu" in data and "taiyou" in data:
            # 欠けをフォールバックで補う
            fb = fallback_poems(place_name)
            for poet in ["kyodatsu","taiyou"]:
                for lvl in ["0","1","2","3"]:
                    if not data[poet].get(lvl):
                        data[poet][lvl] = fb[poet][lvl]
            return data, "gemini-2.0-flash"
        raise ValueError("bad json structure")
    except Exception as e:
        print(f"gemini fail {place_name}: {e}")
        return fallback_poems(place_name), "fallback"

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
    for loc in load_locations():
        key = loc["id"]; vid = loc.get("video_id"); name = loc.get("name", key)
        if not vid:
            continue
        out = f"images/{key}.jpg"
        # 既存画像があればバックアップとして残す
        status = fetch_still(vid, out)
        if status is None:
            print(f"skip {key}: no image, keep old")
            # 既存がなければフォールバック詩だけ保存
            if key not in data["locations"]:
                data["locations"][key] = {"video_id": vid, "image": out, "poems": fallback_poems(name), "model": "fallback-no-image", "updated_at": now, "status": "no-image"}
            continue
        poems, model = generate_poems(out, name)
        data["locations"][key] = {"video_id": vid, "image": out, "poems": poems, "model": model, "updated_at": now, "status": status}
        print(f"{key}: {status} {model} {poems['kyodatsu']['1'][:20]}")
    Path("data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
