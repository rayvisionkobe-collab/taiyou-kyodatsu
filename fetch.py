# ============================================================
# fetch.py v19 - 朝・昼・晩の3回だけAI詩を作る版
# POEM_HOURS = [6, 12, 18]  <- ここにあります (朝6時・昼12時・晩18時)
# BUSY_HOURS = [15, 16]     <- 15-16時はGeminiを使わない
# GEMINI_MODELS = 7つ回遊  <- 3.8が429でも次へ逃げる
# ============================================================
import os, json, time, base64, subprocess, datetime, requests, re, hashlib
from pathlib import Path
from io import BytesIO

Path("images").mkdir(exist_ok=True)

POEM_HOURS = [6, 12, 18]  # 朝6時・昼12時・晩18時だけAI詩を作る
BUSY_HOURS = [15, 16]  # 15-16時はGeminiを使わない (429/503回避)

def load_locations():
    return [
        {"id": "kobe", "name": "神戸", "lat": 34.69, "lon": 135.19, "weathernews_id": "7CDDE9067E16", "page_url": "https://weathernews.jp/onebox/livecam/kinki/hyogo/7CDDE9067E16/"},
        {"id": "osaka", "name": "大阪", "lat": 34.69, "lon": 135.50, "weathernews_id": "7CDDE906F8CE", "page_url": "https://weathernews.jp/onebox/livecam/kinki/osaka/7CDDE906F8CE/"},
        {"id": "sapporo", "name": "札幌", "lat": 43.06, "lon": 141.35, "weathernews_id": "410001361", "page_url": "https://weathernews.jp/onebox/livecam/hokkaido/douou/410001361/"},
        {"id": "tokyo", "name": "東京", "lat": 35.68, "lon": 139.76, "weathernews_id": "410000116", "page_url": "https://weathernews.jp/onebox/livecam/kanto/tokyo/410000116/"},
        {"id": "sendai", "name": "仙台", "lat": 38.26, "lon": 140.87, "weathernews_id": "7CDDE905CDB1", "page_url": "https://weathernews.jp/onebox/livecam/tohoku/miyagi/7CDDE905CDB1/"},
        {"id": "nagoya", "name": "名古屋", "lat": 35.18, "lon": 136.90, "weathernews_id": "7CDDE906B81D", "page_url": "https://weathernews.jp/onebox/livecam/chubu/aichi/7CDDE906B81D/"},
        {"id": "hiroshima", "name": "広島", "lat": 34.39, "lon": 132.45, "weathernews_id": "7CDDE908C8DC", "page_url": "https://weathernews.jp/onebox/livecam/chugoku/hiroshima/7CDDE908C8DC/"},
        {"id": "fukuoka", "name": "福岡", "lat": 33.59, "lon": 130.40, "weathernews_id": "7CDDE906F156", "page_url": "https://weathernews.jp/onebox/livecam/kyushu/fukuoka/7CDDE906F156/"},
        {"id": "naha", "name": "那覇", "lat": 26.21, "lon": 127.68, "weathernews_id": "7CDDE9086CB8", "page_url": "https://weathernews.jp/onebox/livecam/okinawa/7CDDE9086CB8/"},
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
                if rr.status_code == 200 and len(rr.content) > 3000:
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
    max_back = 60 if camera_id.startswith("410") else 13  # 180分だと遅いので60分に
    step = 5 if camera_id.startswith("410") else 1
    for back in range(0, max_back + 1, step):
        t_base = now - datetime.timedelta(minutes=back)
        for sec in ["00", "01", "11", "30", "50", "41"]:
            ts = t_base.strftime("%Y%m%d%H%M") + sec
            for ext in ["webp", "jpg"]:
                url = f"https://gvs.weathernews.jp/livecam/{camera_id}/640/{ts}.{ext}"
                try:
                    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                    if r.status_code == 200 and len(r.content) > 3000:
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

def temp_to_feeling(temp):
    # 数字の温度は使わない。時間帯が変わるとズレるため、体感に変える
    if temp >= 32:
        return "焼けるような暑さ"
    if temp >= 28:
        return "熱い"
    if temp >= 24:
        return "ほどよく暖かい"
    if temp >= 19:
        return "過ごしやすい"
    if temp >= 15:
        return "涼しい"
    if temp >= 10:
        return "肌寒い"
    if temp >= 4:
        return "冷たい"
    if temp >= 0:
        return "凍えそう"
    return "凍えそう"

def fallback_poems(place_name, lat=None, lon=None):
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    hour = now.hour
    time_word = "夜明け" if 5 <= hour < 8 else "朝" if 8 <= hour < 12 else "昼下がり" if 12 <= hour < 17 else "夕暮れ" if 17 <= hour < 19 else "夜"
    weather, temp, wind = get_weather(lat, lon) if lat else ("曇り", 14, 3)
    feeling = temp_to_feeling(temp)
    return {
        "kyodatsu": {
            "0": f"{place_name}の空は、{weather}、{feeling}。",
            "1": f"{place_name}の空は、{weather}、{feeling}。\n{time_word}の風が、遠くで何かを運んでくる。",
            "2": f"{place_name}の空は、{weather}、{feeling}。\n{time_word}の風が、遠くで何かを運んでくる。\nどこへも行けず、空だけが遠くへ行く。",
            "3": f"{place_name}の空は、{weather}、{feeling}。{time_word}の風が、遠くで何かを運んでくる。どこへも行けず、空だけが遠くへ行ってしまうような、虚脱の午後だった."
        },
        "taiyou": {
            "0": f"{place_name}に、{weather}の光が落ちている。",
            "1": f"{place_name}に、{weather}の光が落ちている。\n{time_word}、海の向こうで風が渡ろうとしている。",
            "2": f"{place_name}に、{weather}の光が落ちている。\n{time_word}、海の向こうで風が渡ろうとしている。\n{feeling}光が、今日の空を包んでいる。",
            "3": f"{place_name}に、{weather}の光が落ちている。{time_word}、海の向こうで風が渡ろうとしている。{feeling}光が、樹々を照らし、すべての存在を光に包むような、太陽の涙の午後だった."
        }
    }

# ---- Gemini 設定: 忙しい時間とモデル回遊 ----
# 3.8だけだと429で止まるので、広げて回遊する。404なら次へ、429/503なら少し待って次へ
GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
]  # 2.5-flash は 404 なので外す  # 7つだと404ばかりで時間がかかるので、確実にある3つだけに絞る

def current_poem_slot(hour):
    # 6時台->朝, 12時台->昼, 18時台->晩。それ以外は None (作らない)
    if hour == 6:
        return "morning"
    if hour == 12:
        return "noon"
    if hour == 18:
        return "evening"
    return None

def should_generate_poem(now, existing):
    # 1回だけ強制: Actionsで FORCE_POEM=1 を付けたら、時間に関係なく作る
    if os.environ.get("FORCE_POEM") == "1":
        # 今の時間に近いスロットを決める (19時なら evening)
        h = now.hour
        slot_now = "morning" if 5 <= h < 11 else "noon" if 11 <= h < 17 else "evening" if 17 <= h < 22 else "morning"
        print(f"FORCE_POEM=1: force slot={slot_now} hour={h}")
        return True, slot_now
    hour = now.hour
    # 忙しい時間は作らない
    if hour in BUSY_HOURS:
        print(f"skip gemini: busy hour {hour} (429/503回避)")
        return False, None
    slot = current_poem_slot(hour)
    if slot is None:
        return False, None
    # 同じ日の同じスロットなら作らない (重複防止)
    if existing.get("poem_date") == now.date().isoformat() and existing.get("poem_slot") == slot:
        return False, slot
    # 前のスロットの詩がまだ無い場合 (初回) も作る
    return True, slot

def generate_poems(image_path, place_name, lat=None, lon=None, loc_index=0):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return fallback_poems(place_name, lat, lon), "fallback-no-key"
    try:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    except Exception as e:
        print(f"gemini fail {place_name}: image read {e}")
        return fallback_poems(place_name, lat, lon), "fallback-no-image"
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
条件: 各詩に天気の言葉(晴れ・曇り・雨・風・雪など)を1つだけ入れる。温度の数字(℃)は入れない。代わりに体感(熱い・過ごしやすい・涼しい・肌寒い・凍えそうなど)を使う。改行は詩の中では使わず、1行で書く。
"""
    # 場所ごとに開始モデルをずらして、1つのモデルに集中しない (429分散)
    models = GEMINI_MODELS[loc_index % len(GEMINI_MODELS):] + GEMINI_MODELS[:loc_index % len(GEMINI_MODELS)]
    last_err = ""
    for mi, model in enumerate(models):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":"image/jpeg","data":b64}}]}], "generationConfig":{"temperature":0.9,"maxOutputTokens":1200}}
            r = requests.post(url, json=payload, timeout=60)
            if r.status_code == 404:
                print(f"gemini {model} 404 NotFound {place_name}: 次のモデルへ")
                last_err = "404"
                continue
            if r.status_code == 429:
                print(f"gemini {model} 429 TooManyRequests {place_name}: 10秒待って次のモデルへ")
                last_err = "429"
                time.sleep(3)  # 503は3秒だけ待つ  # 429は5秒だけ待つ (長く待っても直らない)
                continue
            if r.status_code == 503:
                print(f"gemini {model} 503 ServiceUnavailable {place_name}: 5秒待って次のモデルへ")
                last_err = "503"
                time.sleep(3)  # 503は3秒だけ待つ
                continue
            if r.status_code != 200:
                print(f"gemini {model} status {r.status_code}: {r.text[:300]}")
                last_err = str(r.status_code)
                time.sleep(3)
                continue
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = {"kyodatsu":{}, "taiyou":{}}
            import re as _re
            # KYODATSU0: / KYODATSU 0: / KYODATSU-0: / **KYODATSU0** など全部拾う
            for m in _re.finditer(r"(KYODATSU|TAIYOU)[\s\*\-\:]*([0-3])\s*[:：]\s*(.+)", txt, _re.IGNORECASE):
                poet = "kyodatsu" if m.group(1).upper() == "KYODATSU" else "taiyou"
                lvl = m.group(2)
                val = m.group(3).strip().strip("*").strip()
                # 改行が混ざっていたら1行にする
                val = val.replace("\n", " ").strip()
                if val:
                    data[poet][lvl] = val
            fb = fallback_poems(place_name, lat, lon)
            ok = 0
            for poet in ["kyodatsu","taiyou"]:
                for lvl in ["0","1","2","3"]:
                    if data[poet].get(lvl):
                        ok += 1
                    else:
                        data[poet][lvl] = fb[poet][lvl]
            print(f"gemini ok {place_name} model={model} parsed={ok}/8 (試した {mi+1} 個目)")
            if ok == 0:
                continue
            return data, model
        except Exception as e:
            print(f"gemini fail {place_name} model={model}: {e}")
            last_err = str(e)
            time.sleep(3)
            continue
    print(f"gemini all failed {place_name}: last={last_err} -> fallback")
    return fallback_poems(place_name, lat, lon), "fallback"

def main():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
    now_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    data = {"updated_at": now, "locations": {}}
    if Path("data.json").exists():
        try:
            old = json.loads(Path("data.json").read_text(encoding="utf-8"))
            data = old
            data["updated_at"] = now
        except:
            pass
    locs = load_locations()
    valid_ids = {l["id"] for l in locs}
    if "locations" in data:
        for old_key in list(data["locations"].keys()):
            if old_key not in valid_ids:
                print(f"cleanup data.json: remove old {old_key}")
                del data["locations"][old_key]
    for img in Path("images").glob("*.jpg"):
        if img.stem not in valid_ids:
            try:
                img.unlink()
                print(f"cleanup images: remove old {img.name}")
            except Exception as e:
                print(f"cleanup fail {img.name}: {e}")
    # 古い詩の掃除: data.json に残っている「広島市・福岡市・那覇市」を直す
    # 新しく作らなくても、使い回しの詩の地名だけ直す
    if "locations" in data:
        for _k, _v in data["locations"].items():
            if _v.get("poems"):
                for _poet in ["kyodatsu", "taiyou"]:
                    for _lvl in ["0","1","2","3"]:
                        _txt = _v["poems"].get(_poet, {}).get(_lvl, "")
                        if _txt:
                            _txt = _txt.replace("広島市", "広島").replace("福岡市", "福岡").replace("那覇市", "那覇")
                            # 古い温度表示も体感に置き換える (例: 25℃ -> ほどよく暖かい は難しいので、数字だけ消す)
                            # 25℃ が入っていたら、そのままにせず、後で新しい詩で上書きされるまで置いておく
                            _v["poems"][_poet][_lvl] = _txt
    for loc_index, loc in enumerate(locs):
        key = loc["id"]; name = loc.get("name", key)
        out = f"images/{key}.jpg"
        status = fetch_weathernews(loc["weathernews_id"], out, loc.get("page_url"))
        if status is None:
            print(f"warn {key}: no new image, keep old image but still make poem")
            # 画像が取れなくても、詩は作る。画像だけ古いままにする
            status = "keep-old-image"
            # 古い画像があれば、それを詩生成に使う。無ければフォールバック
        existing = data.get("locations", {}).get(key, {})
        do_gen, slot = should_generate_poem(now_dt, existing)
        if do_gen:
            poems, model = generate_poems(out, name, loc.get("lat"), loc.get("lon"), loc_index=loc_index)
            # 失敗して fallback になったら、古いAIの詩を捨てないで残す
            if model.startswith("fallback") and existing.get("poems"):
                print(f"{key}: gemini failed, KEEP old AI poems (slot={existing.get('poem_slot')}) instead of fallback")
                poems, model = existing["poems"], "cached-keep"
                poem_slot = existing.get("poem_slot")
                # poem_date も古いままにして、次の 12時で再試行できるようにする
            else:
                poem_slot = slot
                print(f"{key}: NEW poem slot={slot} model={model}")
        else:
            if existing.get("poems"):
                poems, model = existing["poems"], "cached"
                poem_slot = existing.get("poem_slot")
                print(f"{key}: reuse poems slot={poem_slot} date={existing.get('poem_date')}")
            else:
                poems, model = fallback_poems(name, loc.get("lat"), loc.get("lon")), "fallback-hourly"
                poem_slot = existing.get("poem_slot")
                print(f"{key}: fallback poems (no existing)")
        data["locations"][key] = {"image": out, "poems": poems, "model": model, "updated_at": now, "status": status, "poem_date": now[:10], "poem_slot": poem_slot, "weathernews_id": loc["weathernews_id"]}
        print(f"{key}: {status} {model}")
        time.sleep(15)  # 地点ごとに15秒待つ (429回避: 一気に作らない) (8秒だと9分超える)
    Path("data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
