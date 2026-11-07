import os, json, time, base64, subprocess, datetime, requests, re
from pathlib import Path

Path("images").mkdir(exist_ok=True)

def load_locations():
    # ウェザーニュース 10ヶ所 (YouTubeを使わない)
    # 形式: https://gvs.weathernews.jp/livecam/{ID}/640/{YYYYMMDDHHMMSS}.webp or .jpg
    return [
        {"id": "kobe", "name": "神戸", "lat": 34.69, "lon": 135.19, "weathernews_id": "7CDDE9067E16"},
        {"id": "osaka", "name": "大阪", "lat": 34.69, "lon": 135.50, "weathernews_id": "7CDDE906F8CE"},
        {"id": "sapporo", "name": "札幌", "lat": 43.06, "lon": 141.35, "weathernews_id": "410001361"},
        {"id": "tokyo", "name": "東京", "lat": 35.68, "lon": 139.76, "weathernews_id": "410000116"},
        {"id": "sendai", "name": "仙台", "lat": 38.26, "lon": 140.87, "weathernews_id": "7CDDE905CDB1"},
        {"id": "nagoya", "name": "名古屋", "lat": 35.18, "lon": 136.90, "weathernews_id": "7CDDE906B81D"},
        {"id": "joetsu", "name": "上越市", "lat": 37.15, "lon": 138.23, "weathernews_id": "410000925"},
        {"id": "hiroshima", "name": "広島市", "lat": 34.39, "lon": 132.45, "weathernews_id": "7CDDE908C8DC"},
        {"id": "fukuoka", "name": "福岡市", "lat": 33.59, "lon": 130.40, "weathernews_id": "7CDDE906F156"},
        {"id": "naha", "name": "那覇市", "lat": 26.21, "lon": 127.68, "weathernews_id": "7CDDE9086CB8"},
    ]

def fetch_direct_jpg(direct_url, out_path):
    """YouTube以外: 直接JPGをダウンロードする。ボット判定なし"""
    import time as _t
    try:
        url = direct_url + f"?t={int(_t.time())}"
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
        if r.status_code == 200 and len(r.content) > 8000:
            Path(out_path).write_bytes(r.content)
            print(f"direct-jpg ok {direct_url[:60]} {len(r.content)} bytes")
            return "direct-jpg"
        print(f"direct-jpg fail {direct_url} status={r.status_code} size={len(r.content) if r.status_code==200 else 0}")
    except Exception as e:
        print(f"direct-jpg fail {direct_url}: {e}")
    return None

def fetch_still(video_id, out_path, direct_url=None):
    # 0) YouTube以外があれば、まずそちら (ボット判定なしで確実)
    if direct_url:
        res = fetch_direct_jpg(direct_url, out_path)
        if res:
            return res
        print(f"direct-jpg failed, fallback to YouTube {video_id}")
    import hashlib
    old_hash = None
    if Path(out_path).exists():
        try:
            old_hash = hashlib.md5(Path(out_path).read_bytes()).hexdigest()
        except:
            pass
    # 1) yt-dlp + ffmpeg (1回だけ試す。6回試すと時間がかかる)
    try:
        cmd = ["yt-dlp", "-g", "-f", "bv*[height<=720]+ba/b[height<=720]/best", "--no-check-certificates", "--extractor-args", "youtube:player_client=android", f"https://www.youtube.com/watch?v={video_id}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if result.returncode == 0:
            urls = [u.strip() for u in result.stdout.strip().splitlines() if u.strip().startswith("http")]
            if urls:
                r = subprocess.run(["ffmpeg", "-y", "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "2", "-i", urls[0], "-vframes", "1", "-q:v", "3", out_path], capture_output=True, timeout=25)
                if Path(out_path).exists() and Path(out_path).stat().st_size > 8000:
                    print(f"ffmpeg ok {video_id}")
                    return "live"
        else:
            print(f"yt-dlp fail {video_id}: {result.stderr[:150]}")
    except Exception as e:
        print(f"ffmpeg try fail {video_id}: {e}")
    # 2) ライブサムネイル
    import time as _t2
    for q in ["maxresdefault_live", "hqdefault_live", "sddefault_live"]:
        try:
            url = f"https://i.ytimg.com/vi/{video_id}/{q}.jpg?t={int(_t2.time())}"
            r = requests.get(url, timeout=15, headers={"Cache-Control": "no-cache"})
            if r.status_code == 200 and len(r.content) > 8000:
                new_hash = hashlib.md5(r.content).hexdigest()
                if new_hash == old_hash:
                    print(f"live-thumb same {video_id} {q}")
                    continue
                Path(out_path).write_bytes(r.content)
                print(f"live-thumb ok {video_id} {q} {len(r.content)} bytes")
                return "live-thumb"
        except Exception as e:
            print(f"live-thumb fail {video_id} {q}: {e}")
    try:
        r = requests.get(f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", timeout=15)
        if r.status_code == 200 and len(r.content) > 8000:
            Path(out_path).write_bytes(r.content)
            print(f"thumb fallback ok {video_id}")
            return "thumbnail"
    except Exception as e:
        print(f"thumb fallback fail {video_id}: {e}")
    print(f"fetch_still FAILED {video_id}")
    return None

def get_weather(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code,wind_speed_10m&timezone=Asia%2FTokyo"
        r = requests.get(url, timeout=15)
        j = r.json()
        cur = j["current"]
        wmap = {0:"晴れ",1:"晴れ",2:"曇り",3:"曇り",45:"霧",48:"霧",51:"小雨",53:"雨",55:"雨",61:"雨",63:"雨",65:"大雨",71:"雪",73:"雪",75:"大雪",80:"雨",95:"雷雨"}
        return wmap.get(cur["weather_code"], "曇り"), round(cur["temperature_2m"]), round(cur["wind_speed_10m"])
    except:
        return "曇り", 14, 3

def fallback_poems(place_name, lat=None, lon=None):
    # Geminiが失敗しても、天気・気温・時間で毎回違う詩になる
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9)))
    hour = now.hour
    time_word = "夜明け" if 5 <= hour < 8 else "朝" if 8 <= hour < 12 else "昼下がり" if 12 <= hour < 17 else "夕暮れ" if 17 <= hour < 19 else "夜"
    weather, temp, wind = get_weather(lat, lon) if lat else ("曇り", 14, 3)
    return {
        "kyodatsu": {
            "0": f"{place_name}の空は、{weather}、{temp}℃。",
            "1": f"{place_name}の空は、{weather}、{temp}℃。\n{time_word}の風が、遠くで何かを運んでくる。",
            "2": f"{place_name}の空は、{weather}、{temp}℃。\n{time_word}の風が、遠くで何かを運んでくる。\n風{wind}m、どこへも行けず、空だけが遠くへ行く。",
            "3": f"{place_name}の空は、{weather}、{temp}℃。{time_word}の風が、遠くで何かを運んでくる。風{wind}mの午後、どこへも行けず、空だけが遠くへ行ってしまうような、虚脱の午後だった。"
        },
        "taiyou": {
            "0": f"{place_name}に、{weather}の光が落ちている。",
            "1": f"{place_name}に、{weather}の光が落ちている。\n{time_word}、海の向こうで風が渡ろうとしている。",
            "2": f"{place_name}に、{weather}の光が落ちている。\n{time_word}、海の向こうで風が渡ろうとしている。\n{temp}℃の光が、今日の空を包んでいる。",
            "3": f"{place_name}に、{weather}の光が落ちている。{time_word}、海の向こうで風が渡ろうとしている。{temp}℃の光が、樹々を照らし、すべての存在を光に包むような、太陽の涙の午後だった。"
        }
    }

def generate_poems(image_path, place_name, lat=None, lon=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return fallback_poems(place_name, lat, lon), "fallback-no-key"
    # 2026-11: Google推奨は gemini-3.8-flash。1モデルだけ使う(5モデル試すと429になる)
    model = "gemini-3.8-flash"
    try:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        # JSONで返させない。プレーンテキストで区切り文字で返すと、壊れたJSONにならない
        prompt = f"""この画像は日本の{place_name}のライブカメラです。画像をよく見て、詩を8つ作ってください。
形式は必ずこれだけ。JSONは使わない。説明文なし。
---
KYODATSU0: {place_name}を入れた1行の詩、中原中也風、少し寂しく温かい
KYODATSU1: {place_name}を入れた2行の詩、中原中也風、比喩少し
KYODATSU2: {place_name}を入れた3行の詩、中原中也風、主観濃く
KYODATSU3: {place_name}を入れた長めの1段落、中原中也風、解体的
TAIYOU0: {place_name}を入れた1行の詩、宮沢賢治風、光と風
TAIYOU1: {place_name}を入れた2行の詩、宮沢賢治風、比喩少し
TAIYOU2: {place_name}を入れた3行の詩、宮沢賢治風、主観濃く
TAIYOU3: {place_name}を入れた長めの1段落、宮沢賢治風、宇宙感じる
---
条件: 各詩に天気の言葉(晴れ・曇り・雨・風・雪など)を1つだけ入れる。改行は詩の中では使わず、1行で書く。
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":"image/jpeg","data":b64}}]}], "generationConfig":{"temperature":0.9,"maxOutputTokens":1200}}
        r = requests.post(url, json=payload, timeout=60)
        if r.status_code != 200:
            print(f"gemini {model} status {r.status_code}: {r.text[:300]}")
            raise Exception(f"{model} {r.status_code}")
        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        # パース: KYODATSU0: ... の行を拾う
        data = {"kyodatsu":{}, "taiyou":{}}
        for line in txt.splitlines():
            line=line.strip()
            if not line or ":" not in line:
                continue
            key, val = line.split(":", 1)
            key=key.strip().upper(); val=val.strip()
            if key.startswith("KYODATSU") and key[-1] in "0123":
                data["kyodatsu"][key[-1]] = val
            elif key.startswith("TAIYOU") and key[-1] in "0123":
                data["taiyou"][key[-1]] = val
        # 足りない分はフォールバックで埋める
        fb = fallback_poems(place_name, lat, lon)
        ok = 0
        for poet in ["kyodatsu","taiyou"]:
            for lvl in ["0","1","2","3"]:
                if data[poet].get(lvl):
                    ok += 1
                else:
                    data[poet][lvl] = fb[poet][lvl]
        print(f"gemini ok {place_name} model={model} parsed={ok}/8")
        if ok == 0:
            raise ValueError("no poems parsed")
        return data, model
    except Exception as e:
        print(f"gemini fail {place_name}: {e}")
        return fallback_poems(place_name, lat, lon), "fallback"

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
        if not vid and not loc.get('weathernews_id') and not loc.get('direct_image_url'):
            continue
        out = f"images/{key}.jpg"
        # 既存画像があればバックアップとして残す
        status = None
        if loc.get('weathernews_id'):
            status = fetch_weathernews(loc['weathernews_id'], out)
        if status is None:
            status = fetch_still(vid, out, loc.get('direct_image_url')) if vid else fetch_direct_jpg(loc.get('direct_image_url'), out) if loc.get('direct_image_url') else None
        if status is None:
            print(f"skip {key}: no image, keep old")
            # 既存がなければフォールバック詩だけ保存
            if key not in data["locations"]:
                data["locations"][key] = {"video_id": vid, "image": out, "poems": fallback_poems(name, loc.get("lat"), loc.get("lon")), "model": "fallback-no-image", "updated_at": now, "status": "no-image"}
            continue
        # AI詩は1日1回だけ: 今日の詩がdata.jsonにあれば再利用 (Gemini 429/503対策)
        today = now[:10]
        existing = data.get("locations", {}).get(key, {})
        if existing.get("poems") and existing.get("poem_date") == today:
            poems, model = existing["poems"], existing.get("model", "cached") + "-cached"
            print(f"{key}: reuse poems from today {today}")
        else:
            # 朝6時の実行だけAI生成、それ以外は天気詩で済ませる (1日1回に減らす)
            hour = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).hour
            if hour == 6 or not existing.get("poems"):
                poems, model = generate_poems(out, name, loc.get("lat"), loc.get("lon"))
                # 生成した詩に日付を付ける
            else:
                poems, model = fallback_poems(name, loc.get("lat"), loc.get("lon")), "fallback-hourly"
        data["locations"][key] = {"video_id": vid, "image": out, "poems": poems, "model": model, "updated_at": now, "status": status, "poem_date": now[:10]}
        print(f"{key}: {status} {model} {poems['kyodatsu']['1'][:20]}")
        time.sleep(3)  # 429対策: 地点ごとに3秒待つ
    Path("data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main(def fetch_weathernews(camera_id, out_path):
    """ウェザーニュース: 最新の静止画を取る。webpとjpg両対応、秒も試す"""
    import datetime as _dt
    from io import BytesIO
    try:
        from PIL import Image
    except:
        Image = None
    now = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9)))
    # 0分〜12分前まで、秒も変えて試す (古いカメラは秒が00でない)
    for back in range(0, 13):
        t_base = now - _dt.timedelta(minutes=back)
        for sec in ["00", "11", "30", "50"]:
            ts = t_base.strftime("%Y%m%d%H%M") + sec
            for ext in ["webp", "jpg"]:
                url = f"https://gvs.weathernews.jp/livecam/{camera_id}/640/{ts}.{ext}"
                try:
                    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                    if r.status_code == 200 and len(r.content) > 8000:
                        if ext == "webp" and Image:
                            img = Image.open(BytesIO(r.content)).convert("RGB")
                            img.save(out_path, "JPEG", quality=88)
                            print(f"weathernews ok {camera_id} {ts}.{ext} {len(r.content)} bytes -> jpg")
                        elif ext == "jpg" and Image:
                            # jpgも一旦PILで開いて再保存 (壊れたjpg対策)
                            try:
                                img = Image.open(BytesIO(r.content)).convert("RGB")
                                img.save(out_path, "JPEG", quality=88)
                            except:
                                Path(out_path).write_bytes(r.content)
                            print(f"weathernews ok {camera_id} {ts}.{ext} {len(r.content)} bytes")
                        else:
                            Path(out_path).write_bytes(r.content)
                            print(f"weathernews ok {camera_id} {ts}.{ext}")
                        return "weathernews"
                except Exception as e:
                    continue
    print(f"weathernews FAILED {camera_id}")
    return None

)
