import os, json, base64, subprocess, datetime, requests, re
from pathlib import Path

Path("images").mkdir(exist_ok=True)

def load_locations():
    # config.json に依存しない: ここが正解。config.json が古くても、こちらが使われる
    return [
        {"id": "maiko", "name": "舞子ビラ・明石海峡大橋", "lat": 34.634, "lon": 135.029, "video_id": "W5iKrSNyJhQ"},
        {"id": "kobe_air", "name": "神戸空港", "lat": 34.632, "lon": 135.223, "video_id": "dpVyxSYsVs0"},
        {"id": "sapporo", "name": "札幌すすきの", "lat": 43.055, "lon": 141.353, "video_id": "wRYonRnKsKw"},
        {"id": "tokyo", "name": "東京タワー", "lat": 35.6586, "lon": 139.7454, "video_id": "nu6NE55_X7A"},
        {"id": "fuji", "name": "富士山裾野", "lat": 35.28, "lon": 138.61, "video_id": "F2NbYrc-gBU"},
        {"id": "fukuoka", "name": "福岡・博多中洲", "lat": 33.584, "lon": 130.451, "video_id": "NGbqP0fEZSE"},
        {"id": "naha", "name": "那覇空港", "lat": 26.195, "lon": 127.646, "video_id": "dc8Iqi5Xxl8"},
    ]

def fetch_still(video_id, out_path):
    import hashlib
    # 前の画像のハッシュを覚えて、同じ画像なら「更新なし」と分かるようにする
    old_hash = None
    if Path(out_path).exists():
        try:
            old_hash = hashlib.md5(Path(out_path).read_bytes()).hexdigest()
        except:
            pass

    # 1) yt-dlp + ffmpeg で本物のフレームを取る
    # GitHub ActionsのIPはYouTubeにブロックされやすいので、player_client を変えて3通り試す
    for client in ["android", "web", "tv"]:
        for fmt in ["bv*[height<=720]+ba/b[height<=720]/best", "best[height<=720]"]:
            try:
                cmd = ["yt-dlp", "-g", "-f", fmt, "--no-check-certificates", "--extractor-args", f"youtube:player_client={client}", f"https://www.youtube.com/watch?v={video_id}"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
                if result.returncode != 0:
                    print(f"yt-dlp {client} {fmt} fail {video_id}: {result.stderr[:300]}")
                    continue
                urls = [u.strip() for u in result.stdout.strip().splitlines() if u.strip().startswith("http")]
                if not urls:
                    print(f"yt-dlp {client} {fmt} no url {video_id}")
                    continue
                stream_url = urls[0]
                # ffmpeg で1フレーム切り出す。-reconnect で途切れ対策
                r = subprocess.run(["ffmpeg", "-y", "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "2", "-i", stream_url, "-vframes", "1", "-q:v", "3", out_path], capture_output=True, timeout=40)
                if Path(out_path).exists() and Path(out_path).stat().st_size > 8000:
                    new_hash = hashlib.md5(Path(out_path).read_bytes()).hexdigest()
                    print(f"ffmpeg ok {video_id} client={client} fmt={fmt} hash_changed={new_hash!=old_hash}")
                    return "live"
                else:
                    print(f"ffmpeg small file {video_id} client={client}")
            except Exception as e:
                print(f"ffmpeg try {client} {fmt} fail {video_id}: {e}")
                continue

    # 2) ライブサムネイル - ただしキャッシュバスター付きで、古い静止サムネイルを避ける
    import time
    for q in ["hqdefault_live", "maxresdefault_live", "sddefault_live"]:
        try:
            url = f"https://i.ytimg.com/vi/{video_id}/{q}.jpg?t={int(time.time())}"
            r = requests.get(url, timeout=15, headers={"Cache-Control": "no-cache"})
            if r.status_code == 200 and len(r.content) > 8000:
                new_hash = hashlib.md5(r.content).hexdigest()
                if new_hash == old_hash:
                    print(f"live-thumb same as before {video_id} {q} - サムネイルが更新されていません")
                    continue
                Path(out_path).write_bytes(r.content)
                print(f"live-thumb ok {video_id} {q} {len(r.content)} bytes hash_changed=True")
                return "live-thumb"
            else:
                print(f"live-thumb skip {video_id} {q} status={r.status_code}")
        except Exception as e:
            print(f"live-thumb fail {video_id} {q}: {e}")

    # 3) 最後の手段: 通常サムネイル (静止画でも、何もないよりマシ)
    try:
        r = requests.get(f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", timeout=15)
        if r.status_code == 200 and len(r.content) > 8000:
            Path(out_path).write_bytes(r.content)
            print(f"thumb fallback ok {video_id} hqdefault")
            return "thumbnail"
    except Exception as e:
        print(f"thumb fallback fail {video_id}: {e}")
    print(f"fetch_still FAILED {video_id} - 前の画像を残します")
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
        r = requests.post(url, json=payload, timeout=90)
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
        if not vid:
            continue
        out = f"images/{key}.jpg"
        # 既存画像があればバックアップとして残す
        status = fetch_still(vid, out)
        if status is None:
            print(f"skip {key}: no image, keep old")
            # 既存がなければフォールバック詩だけ保存
            if key not in data["locations"]:
                data["locations"][key] = {"video_id": vid, "image": out, "poems": fallback_poems(name, loc.get("lat"), loc.get("lon")), "model": "fallback-no-image", "updated_at": now, "status": "no-image"}
            continue
        poems, model = generate_poems(out, name, loc.get("lat"), loc.get("lon"))
        data["locations"][key] = {"video_id": vid, "image": out, "poems": poems, "model": model, "updated_at": now, "status": status}
        print(f"{key}: {status} {model} {poems['kyodatsu']['1'][:20]}")
        time.sleep(3)  # 429対策: 地点ごとに3秒待つ
    Path("data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
