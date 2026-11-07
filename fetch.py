import os, json, time, base64, subprocess, datetime, requests, re, hashlib
from pathlib import Path
from io import BytesIO

Path("images").mkdir(exist_ok=True)

def load_locations():
    return [
        {"id": "kobe", "name": "神戸", "lat": 34.69, "lon": 135.19, "weathernews_id": "7CDDE9067E16", "page_url": "https://weathernews.jp/onebox/livecam/kinki/hyogo/7CDDE9067E16/"},
        {"id": "osaka", "name": "大阪", "lat": 34.69, "lon": 135.50, "weathernews_id": "7CDDE906F8CE", "page_url": "https://weathernews.jp/onebox/livecam/kinki/osaka/7CDDE906F8CE/"},
        {"id": "sapporo", "name": "札幌", "lat": 43.06, "lon": 141.35, "weathernews_id": "410001361", "page_url": "https://weathernews.jp/onebox/livecam/hokkaido/douou/410001361/"},
        {"id": "tokyo", "name": "東京", "lat": 35.68, "lon": 139.76, "weathernews_id": "410000116", "page_url": "https://weathernews.jp/onebox/livecam/kanto/tokyo/410000116/"},
        {"id": "sendai", "name": "仙台", "lat": 38.26, "lon": 140.87, "weathernews_id": "7CDDE905CDB1", "page_url": "https://weathernews.jp/onebox/livecam/tohoku/miyagi/7CDDE905CDB1/"},
        {"id": "nagoya", "name": "名古屋", "lat": 35.18, "lon": 136.90, "weathernews_id": "7CDDE906B81D", "page_url": "https://weathernews.jp/onebox/livecam/chubu/aichi/7CDDE906B81D/"},
        {"id": "hiroshima", "name": "広島市", "lat": 34.39, "lon": 132.45, "weathernews_id": "7CDDE908C8DC", "page_url": "https://weathernews.jp/onebox/livecam/chugoku/hiroshima/7CDDE908C8DC/"},
        {"id": "fukuoka", "name": "福岡市", "lat": 33.59, "lon": 130.40, "weathernews_id": "7CDDE906F156", "page_url": "https://weathernews.jp/onebox/livecam/kyushu/fukuoka/7CDDE906F156/"},
        {"id": "naha", "name": "那覇市", "lat": 26.21, "lon": 127.68, "weathernews_id": "7CDDE9086CB8", "page_url": "https://weathernews.jp/onebox/livecam/okinawa/7CDDE9086CB8/"},
    ]

def fetch_weathernews(camera_id, out_path, page_url=None):
    """ウェザーニュース: ページから最新の画像URLを取る。推測しない"""
    try:
        from PIL import Image
    except:
        Image = None
    # 1. ページから最新のURLを探す (一番大きい枠 = 自分のIDが入ったURLだけ)
    if page_url:
        try:
            r = requests.get(page_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            html = r.text
            # 自分のIDだけを拾う。周辺カメラ(別のID)は無視する
            pattern = re.compile(r"https://gvs\.weathernews\.jp/livecam/" + re.escape(camera_id) + r"/640/\d+\.(?:webp|jpg)")
            found = pattern.findall(html)
            # HTMLエスケープや // になっている場合も拾う
            if not found:
                pattern2 = re.compile(r"gvs\.weathernews\.jp/livecam/" + re.escape(camera_id) + r"/640/\d+\.(?:webp|jpg)")
                found2 = pattern2.findall(html)
                found = ["https://" + u for u in found2]
            if found:
                # 一番新しい時刻 = ファイル名の数字が一番大きいもの
                found = sorted(set(found))
                latest = found[-1]
                print(f"page parse {camera_id} found {len(found)} -> latest {latest}")
                rr = requests.get(latest, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                if rr.status_code == 200 and len(rr.content) > 8000:
                    if Image:
                        try:
                            img = Image.open(BytesIO(rr.content)).convert("RGB")
                            img.save(out_path, "JPEG", quality=88)
                        except:
                            Path(out_path).write_bytes(rr.content)
                    else:
                        Path(out_path).write_bytes(rr.content)
                    print(f"weathernews ok {camera_id} via page {latest} {len(rr.content)} bytes")
                    return "weathernews-page"
                else:
                    print(f"page image fail {camera_id} {latest} status={rr.status_code}")
        except Exception as e:
            print(f"page parse fail {camera_id}: {e}")
    # 2. ページから取れなければ、時刻推測でバックアップ
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    max_back = 180 if camera_id.startswith("410") else 13
    step = 5 if camera_id.startswith("410") else 1
    for back in range(0, max_back + 1, step):
        t_base = now - datetime.timedelta(minutes=back)
        for sec in ["00", "01", "11", "30", "50", "41"]:
            ts = t_base.strftime("%Y%m%d%H%M") + sec
            for ext in ["webp", "jpg"]:
                url = f"https://gvs.weathernews.jp/livecam/{camera_id}/640/{ts}.{ext}"
                try:
                    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                    if r.status_code == 200 and len(r.content) > 8000:
                        if Image:
                            try:
                                img = Image.open(BytesIO(r.content)).convert("RGB")
                                img.save(out_path, "JPEG", quality=88)
                            except:
                                Path(out_path).write_bytes(r.content)
                        else:
                            Path(out_path).write_bytes(r.content)
                        print(f"weathernews ok {camera_id} via guess {ts}.{ext} {len(r.content)} bytes")
                        return "weathernews"
                except Exception:
                    continue
    print(f"weathernews FAILED {camera_id}")
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
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    hour = now.hour
    time_word = "夜明け" if 5 <= hour < 8 else "朝" if 8 <= hour < 12 else "昼下がり" if 12 <= hour < 17 else "夕暮れ" if 17 <= hour < 19 else "夜"
    weather, temp, wind = get_weather(lat, lon) if lat else ("曇り", 14, 3)
    return {
        "kyodatsu": {
            "0": f"{place_name}の空は、{weather}、{temp}℃。",
            "1": f"{place_name}の空は、{weather}、{temp}℃。\n{time_word}の風が、遠くで何かを運んでくる。",
            "2": f"{place_name}の空は、{weather}、{temp}℃。\n{time_word}の風が、遠くで何かを運んでくる。\n風{wind}m、どこへも行けず、空だけが遠くへ行く。",
            "3": f"{place_name}の空は、{weather}、{temp}℃。{time_word}の風が、遠くで何かを運んでくる。風{wind}mの午後、どこへも行けず、空だけが遠くへ行ってしまうような、虚脱の午後だった."
        },
        "taiyou": {
            "0": f"{place_name}に、{weather}の光が落ちている。",
            "1": f"{place_name}に、{weather}の光が落ちている。\n{time_word}、海の向こうで風が渡ろうとしている。",
            "2": f"{place_name}に、{weather}の光が落ちている。\n{time_word}、海の向こうで風が渡ろうとしている。\n{temp}℃の光が、今日の空を包んでいる。",
            "3": f"{place_name}に、{weather}の光が落ちている。{time_word}、海の向こうで風が渡ろうとしている。{temp}℃の光が、樹々を照らし、すべての存在を光に包むような、太陽の涙の午後だった."
        }
    }

def generate_poems(image_path, place_name, lat=None, lon=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return fallback_poems(place_name, lat, lon), "fallback-no-key"
    model = "gemini-3.8-flash"
    try:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        prompt = f"""この画像は日本の{place_name}のライブカメラです。画像をよく見て、詩を8つ作ってください。\n形式は必ずこれだけ。JSONは使わない。説明文なし。\n---\nKYODATSU0: {place_name}を入れた1行の詩、中原中也風、少し寂しく温かい\nKYODATSU1: {place_name}を入れた2行の詩、中原中也風、比喩少し\nKYODATSU2: {place_name}を入れた3行の詩、中原中也風、主観濃く\nKYODATSU3: {place_name}を入れた長めの1段落、中原中也風、解体的\nTAIYOU0: {place_name}を入れた1行の詩、宮沢賢治風、光と風\nTAIYOU1: {place_name}を入れた2行の詩、宮沢賢治風、比喩少し\nTAIYOU2: {place_name}を入れた3行の詩、宮沢賢治風、主観濃く\nTAIYOU3: {place_name}を入れた長めの1段落、宮沢賢治風、宇宙感じる\n---\n条件: 各詩に天気の言葉(晴れ・曇り・雨・風・雪など)を1つだけ入れる。改行は詩の中では使わず、1行で書く。\n"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":"image/jpeg","data":b64}}]}], "generationConfig":{"temperature":0.9,"maxOutputTokens":1200}}
        r = requests.post(url, json=payload, timeout=60)
        if r.status_code != 200:
            print(f"gemini {model} status {r.status_code}: {r.text[:300]}")
            raise Exception(f"{model} {r.status_code}")
        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
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
    # 古い場所と古い画像を掃除する (不一致の原因)
    valid_ids = {l["id"] for l in load_locations()}
    # data.json の古い場所を削除
    if "locations" in data:
        for old_key in list(data["locations"].keys()):
            if old_key not in valid_ids:
                print(f"cleanup data.json: remove old {old_key}")
                del data["locations"][old_key]
    # images/ の古い画像を削除
    for img in Path("images").glob("*.jpg"):
        if img.stem not in valid_ids:
            try:
                img.unlink()
                print(f"cleanup images: remove old {img.name}")
            except Exception as e:
                print(f"cleanup fail {img.name}: {e}")
    for loc in load_locations():
        key = loc["id"]; name = loc.get("name", key)
        out = f"images/{key}.jpg"
        status = fetch_weathernews(loc["weathernews_id"], out, loc.get("page_url"))
        if status is None:
            print(f"skip {key}: no image, keep old")
            if key not in data["locations"]:
                data["locations"][key] = {"image": out, "poems": fallback_poems(name, loc.get("lat"), loc.get("lon")), "model": "fallback-no-image", "updated_at": now, "status": "no-image", "poem_date": now[:10]}
            continue
        today = now[:10]
        existing = data.get("locations", {}).get(key, {})
        if existing.get("poems") and existing.get("poem_date") == today:
            poems, model = existing["poems"], "cached"
            print(f"{key}: reuse poems from today {today}")
        else:
            hour = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).hour
            if hour == 6 or not existing.get("poems"):
                poems, model = generate_poems(out, name, loc.get("lat"), loc.get("lon"))
            else:
                poems, model = fallback_poems(name, loc.get("lat"), loc.get("lon")), "fallback-hourly"
        data["locations"][key] = {"image": out, "poems": poems, "model": model, "updated_at": now, "status": status, "poem_date": now[:10], "weathernews_id": loc["weathernews_id"]}
        print(f"{key}: {status} {model}")
        time.sleep(2)
    Path("data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
