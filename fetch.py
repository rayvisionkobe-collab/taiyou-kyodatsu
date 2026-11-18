# ============================================================
# fetch.py v55 - Weathernews版（YouTube版ではありません）
# 実行したら最初に「Weathernews版 v55」と出ます。出なければ、古い fetch.py です
# - 画像は毎回取りに行く。詩だけ、POEM_SCHEDULE の時間に作る
# - 画像が取れなかった場所は、updated_at を古いままにする（新しいように見せない）
# - 東京は、元カメラ自体が 11/18 04:56 で止まっている（Weathernews側）
#   → その場合は、直接URLでも取れないので、赤いままが正しい
# - 那覇は、元は 11/19 05:29 で生きている。ページがJSでURLがHTMLにない場合、
#   直接URL（gvs.../1280/日時.jpg）を試すフォールバックを入れた
# ============================================================
import os, json, time, base64, datetime, requests, re
from pathlib import Path

print("Weathernews版 v55")

Path("images").mkdir(exist_ok=True)

POEM_SCHEDULE = {
    6:  {"slot": "morning", "targets": ["kobe", "osaka", "tokyo", "nagoya", "fukuoka"]},
    7:  {"slot": "morning", "targets": ["kobe", "osaka", "tokyo", "nagoya", "fukuoka"]},
    8:  {"slot": "morning", "targets": ["kobe", "osaka", "tokyo", "nagoya", "fukuoka"]},
    9:  {"slot": "morning", "targets": ["kobe", "osaka", "tokyo", "nagoya", "fukuoka"]},
    10: {"slot": "morning", "targets": ["kobe", "osaka", "tokyo", "nagoya", "fukuoka"]},
    12: {"slot": "noon",    "targets": ["sapporo", "sendai", "hiroshima", "naha"]},
    13: {"slot": "noon",    "targets": ["sapporo", "sendai", "hiroshima", "naha"]},
    14: {"slot": "noon",    "targets": ["sapporo", "sendai", "hiroshima", "naha"]},
    17: {"slot": "noon",    "targets": ["sapporo", "sendai", "hiroshima", "naha"]},
    18: {"slot": "evening", "targets": ["kobe", "osaka", "tokyo"]},
    19: {"slot": "evening", "targets": ["kobe", "osaka", "tokyo"]},
    20: {"slot": "evening", "targets": ["kobe", "osaka", "tokyo"]},
}
BUSY_HOURS = [15, 16]
GEMINI_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash", "gemini-1.5-pro"]

def load_locations():
    return [
        {"id": "kobe", "name": "神戸", "lat": 34.69, "lon": 135.19, "weathernews_id": "7CDDE9067E16", "page_url": "https://weathernews.jp/onebox/livecam/kinki/hyogo/7CDDE9067E16/"},
        {"id": "osaka", "name": "大阪", "lat": 34.69, "lon": 135.50, "weathernews_id": "7CDDE9068718", "page_url": "https://weathernews.jp/onebox/livecam/kinki/osaka/7CDDE9068718/"},
        {"id": "sapporo", "name": "札幌", "lat": 43.06, "lon": 141.35, "weathernews_id": "7CDDE9068F23", "page_url": "https://weathernews.jp/onebox/livecam/hokkaido/douou/7CDDE9068F23/"},
        {"id": "tokyo", "name": "東京", "lat": 35.68, "lon": 139.76, "weathernews_id": "7CDDE90689B1", "page_url": "https://weathernews.jp/onebox/livecam/kanto/tokyo/7CDDE90689B1/"},
        {"id": "sendai", "name": "仙台", "lat": 38.26, "lon": 140.87, "weathernews_id": "7CDDE905CDB1", "page_url": "https://weathernews.jp/onebox/livecam/tohoku/miyagi/7CDDE905CDB1/"},
        {"id": "nagoya", "name": "名古屋", "lat": 35.18, "lon": 136.90, "weathernews_id": "7CDDE906BBEF", "page_url": "https://weathernews.jp/onebox/livecam/chubu/aichi/7CDDE906BBEF/"},
        {"id": "hiroshima", "name": "広島", "lat": 34.39, "lon": 132.45, "weathernews_id": "7CDDE908C8DC", "page_url": "https://weathernews.jp/onebox/livecam/chugoku/hiroshima/7CDDE908C8DC/"},
        {"id": "fukuoka", "name": "福岡", "lat": 33.59, "lon": 130.40, "weathernews_id": "7CDDE906F156", "page_url": "https://weathernews.jp/onebox/livecam/kyushu/fukuoka/7CDDE906F156/"},
        {"id": "naha", "name": "那覇", "lat": 26.21, "lon": 127.68, "weathernews_id": "7CDDE9086CB8", "page_url": "https://weathernews.jp/onebox/livecam/okinawa/7CDDE9086CB8/"},
    ]

def _try_direct_guess(camera_id, out_path):
    """index.html と同じ直接URLを、10分刻みで直近1時間分試す"""
    now_jst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    for back in (0, 10, 20, 30, 40, 50, 60):
        tt = now_jst - datetime.timedelta(minutes=back)
        tt = tt.replace(minute=(tt.minute // 10) * 10, second=0, microsecond=0)
        ts = tt.strftime("%Y%m%d%H%M00")
        for size in ("1280", "640"):
            guess = f"https://gvs.weathernews.jp/livecam/{camera_id}/{size}/{ts}.jpg"
            try:
                rr = requests.get(guess, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                if rr.status_code == 200 and len(rr.content) > 10000:
                    Path(out_path).write_bytes(rr.content)
                    print(f"  direct guess ok {guess}")
                    return True
            except Exception:
                pass
    return False

def fetch_weathernews(camera_id, out_path, page_url=None):
    """ウェザーニュース：ページから最新の画像URLを取る。なければ直接URLを試す"""
    try:
        if page_url:
            r = requests.get(page_url + ("&" if "?" in page_url else "?") + "v=" + str(int(datetime.datetime.now().timestamp())), timeout=12, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
            html = r.text
            urls = re.findall(r'https://gvs\.weathernews\.jp/livecam/[A-Za-z0-9_\-\./\?=&%]+', html)
            urls = [u for u in urls if camera_id in u]
            urls = [u for u in urls if ('.jpg' in u or '.jpeg' in u or 'image' in u or '1280' in u or '640' in u)]
            if urls:
                seen = []
                for u in urls:
                    if u not in seen:
                        seen.append(u)
                img_url = seen[-1]
                print(f"  livecam url: {img_url[:120]}")
                rr = requests.get(img_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                if rr.status_code == 200 and len(rr.content) > 10000:
                    Path(out_path).write_bytes(rr.content)
                    return True, "ok"
                print(f"  image download fail {rr.status_code} len={len(rr.content)}")
            else:
                print("  no livecam url in page -> try direct guess")
            if _try_direct_guess(camera_id, out_path):
                return True, "direct-guess"
            return False, "no-url"
        if _try_direct_guess(camera_id, out_path):
            return True, "direct-guess"
        return False, "no-page"
    except Exception as e:
        print(f"  fetch_weathernews fail: {e} -> try direct guess")
        if _try_direct_guess(camera_id, out_path):
            return True, "direct-guess"
        return False, "error"

def fallback_poems(name, lat, lon):
    return {
        "kyodatsu": {
            "0": f"{name}の空は、今日も静かだ。",
            "1": f"{name}の空は、今日も静かだ。\n風が、遠くで何かを運んでくる。",
            "2": f"{name}の空は、今日も静かだ。\n風が、遠くで何かを運んでくる。\n曇りの午後、空だけが遠くへ行く。",
            "3": f"{name}の空は、今日も静かだ。風が、遠くで何かを運んでくる。曇りの午後、どこへも行けず、空だけが遠くへ行ってしまうような、虚脱の午後だった。",
        },
        "taiyou": {
            "0": f"{name}に、光が落ちている。",
            "1": f"{name}に、光が落ちている。\n海の向こうで、風が渡ろうとしている。",
            "2": f"{name}に、光が落ちている。\n海の向こうで、風が渡ろうとしている。\n晴れの光が、今日の空を包んでいる。",
            "3": f"{name}に、光が落ちている。海の向こうで、風が渡ろうとしている。晴れの光が、樹々を照らし、すべての存在を光に包むような、太陽の涙の午後だった。",
        },
    }

def generate_poems(image_path, place_name, lat, lon, loc_index=0, slot="morning"):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("  gemini: no API key -> fallback")
        return fallback_poems(place_name, lat, lon), "fallback-no-key"
    try:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    except Exception as e:
        print(f"  gemini: image read fail {e}")
        return fallback_poems(place_name, lat, lon), "fallback-no-image"
    models = GEMINI_MODELS[loc_index % len(GEMINI_MODELS):] + GEMINI_MODELS[:loc_index % len(GEMINI_MODELS)]
    prompt = f"""この画像は{place_name}のライブカメラの空と風景です。画像をよく見て、中原中也風（kyodatsu）と宮沢賢治風（taiyou）の詩を、日本語で作ってください。
条件：
- それぞれ 4段階：0=からっと（1行）、1=ほどよく（2行）、2=こいめ（3行）、3=仙人級（長め1段落）
- 1行目は空や雲や光の様子を具体的に
- 2行目以降は風や音や気配を感じる言葉を
- 天気の言葉（晴れ・曇り・雨・風など）を1つだけ入れる
- 説明文やタイトルは不要。JSONだけを返す
- 返却形式は必ずこの形：
{{"kyodatsu": {{"0": "...", "1": "...", "2": "...", "3": "..."}}, "taiyou": {{"0": "...", "1": "...", "2": "...", "3": "..."}}}}
"""
    for mi, model in enumerate(models):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}], "generationConfig": {"temperature": 0.9, "maxOutputTokens": 1200}}
            r = requests.post(url, json=payload, timeout=60)
            if r.status_code == 404:
                print(f"  gemini {model} 404 NotFound {place_name}: 次のモデルへ")
                continue
            if r.status_code == 429:
                print(f"  gemini {model} 429 TooManyRequests {place_name}: 20秒待って次のモデルへ")
                time.sleep(20)
                continue
            if r.status_code == 503:
                print(f"  gemini {model} 503 ServiceUnavailable {place_name}: 5秒待って次のモデルへ")
                time.sleep(5)
                continue
            if r.status_code != 200:
                print(f"  gemini {model} status {r.status_code}: {r.text[:300]}")
                continue
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            m = re.search(r'\{.*\}', text, re.S)
            if m:
                text = m.group(0)
            j = json.loads(text)
            ok = 0
            for poet in ("kyodatsu", "taiyou"):
                for lv in ("0", "1", "2", "3"):
                    if j.get(poet, {}).get(lv):
                        ok += 1
            print(f"  gemini ok {place_name} model={model} parsed={ok}/8")
            if ok >= 4:
                return j, model
        except Exception as e:
            print(f"  gemini fail {place_name} model={model}: {e}")
            continue
    return fallback_poems(place_name, lat, lon), "fallback-all-fail"

def main():
    now_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    now = now_dt.isoformat()
    hour = now_dt.hour
    print(f"now JST {now} hour={hour}")
    old = {}
    if Path("data.json").exists():
        try:
            old = json.loads(Path("data.json").read_text(encoding="utf-8"))
        except Exception as e:
            print(f"old data.json read fail: {e}")
            old = {}
    old_locs = old.get("locations", {}) if isinstance(old, dict) else {}
    data = {"updated_at": now, "locations": {}}
    sched = POEM_SCHEDULE.get(hour)
    if hour in BUSY_HOURS:
        print(f"BUSY_HOUR {hour}: 詩は作らない（画像だけ）")
        sched = None
    for loc_index, loc in enumerate(load_locations()):
        key = loc["id"]
        name = loc["name"]
        out = f"images/{key}.jpg"
        existing = old_locs.get(key, {})
        ok, status = fetch_weathernews(loc["weathernews_id"], out, loc["page_url"])
        do_gen = False
        slot = None
        if sched and key in sched["targets"]:
            slot = sched["slot"]
            if existing.get("poem_date") == now[:10] and existing.get("poem_slot") == slot and existing.get("poems"):
                print(f"{key}: poem already {now[:10]} {slot} -> keep")
                do_gen = False
            else:
                do_gen = True
        if do_gen:
            print(f"{key}: poem slot={slot} gen...")
            poems, model = generate_poems(out, name, loc.get("lat"), loc.get("lon"), loc_index=loc_index, slot=slot)
            if model.startswith("fallback") and existing.get("poems"):
                poems, model = existing["poems"], "cached-keep"
                print(f"{key}: gemini fail -> cached-keep, poem_date は更新しない（次の時間に再試行）")
                # ここがバグだった：fallback なのに poem_date を今日にすると、
                # 7,8,9,10時が「もう作った」と思って、ずっと再試行しなくなる
                poem_date = existing.get("poem_date", "")
                poem_slot = existing.get("poem_slot", "")
            else:
                poem_date = now[:10]
                poem_slot = slot
        else:
            if existing.get("poems"):
                poems, model = existing["poems"], "cached"
                poem_date = existing.get("poem_date", now[:10])
                poem_slot = existing.get("poem_slot", slot or "")
            else:
                poems, model = fallback_poems(name, loc.get("lat"), loc.get("lon")), "fallback-hourly"
                poem_date = now[:10]
                poem_slot = slot or ""
        _img_updated = now if ok else existing.get("updated_at", now)
        data["locations"][key] = {
            "image": out if (ok or existing.get("image")) else "",
            "poems": poems,
            "model": model,
            "updated_at": _img_updated,
            "status": status if ok else ("no-image" if not existing.get("image") else "keep-old"),
            "poem_date": poem_date,
            "poem_slot": poem_slot,
            "page_url": loc["page_url"],
        }
        print(f"{key}: image_ok={ok} status={data['locations'][key]['status']} poem slot={poem_slot} model={model}")
    Path("data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote data.json updated_at={now} locations={len(data['locations'])}")

if __name__ == "__main__":
    main()
