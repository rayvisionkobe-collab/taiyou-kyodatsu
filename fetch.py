# ============================================================
# fetch.py v64 - Weathernews版（YouTube版ではありません）
# 実行したら最初に「Weathernews版 v64」と出ます。出なければ、古い fetch.py です
# - 画像は毎回取りに行く。詩だけ、POEM_SCHEDULE の時間に作る
# - 画像が取れなかった場所は、updated_at を古いままにする（新しいように見せない）
# - 東京は、元カメラ自体が 11/18 04:56 で止まっている（Weathernews側）
#   → その場合は、直接URLでも取れないので、赤いままが正しい
# - 那覇は、元は 11/19 05:29 で生きている。ページがJSでURLがHTMLにない場合、
#   直接URL（gvs.../1280/日時.jpg）を試すフォールバックを入れた
# ============================================================
import os, json, time, base64, datetime, requests, re
from pathlib import Path

print("Weathernews版 v64")

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
GEMINI_MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview"]

def load_locations():
    return [
        {"id": "kobe", "name": "神戸", "lat": 34.69, "lon": 135.19, "weathernews_id": "7CDDE9067E16", "page_url": "https://weathernews.jp/onebox/livecam/kinki/hyogo/7CDDE9067E16/"},
        {"id": "osaka", "name": "大阪", "lat": 34.69, "lon": 135.50, "weathernews_id": "7CDDE90683C1", "page_url": "https://weathernews.jp/onebox/livecam/kinki/osaka/7CDDE90683C1/"},
        {"id": "sapporo", "name": "札幌", "lat": 43.06, "lon": 141.35, "weathernews_id": "7CDDE9068F23", "page_url": "https://weathernews.jp/onebox/livecam/hokkaido/douou/7CDDE9068F23/"},
        {"id": "tokyo", "name": "東京", "lat": 35.68, "lon": 139.76, "weathernews_id": "7CDDE90689B1", "page_url": "https://weathernews.jp/onebox/livecam/kanto/tokyo/7CDDE90689B1/"},
        {"id": "sendai", "name": "仙台", "lat": 38.26, "lon": 140.87, "weathernews_id": "7CDDE905CDB1", "page_url": "https://weathernews.jp/onebox/livecam/tohoku/miyagi/7CDDE905CDB1/"},
        {"id": "nagoya", "name": "名古屋", "lat": 35.18, "lon": 136.90, "weathernews_id": "7CDDE906BBEF", "page_url": "https://weathernews.jp/onebox/livecam/chubu/aichi/7CDDE906BBEF/"},
        {"id": "hiroshima", "name": "広島", "lat": 34.39, "lon": 132.45, "weathernews_id": "7CDDE908C8DC", "page_url": "https://weathernews.jp/onebox/livecam/chugoku/hiroshima/7CDDE908C8DC/"},
        {"id": "fukuoka", "name": "福岡", "lat": 33.59, "lon": 130.40, "weathernews_id": "7CDDE906F156", "page_url": "https://weathernews.jp/onebox/livecam/kyushu/fukuoka/7CDDE906F156/"},
        {"id": "naha", "name": "那覇", "lat": 26.21, "lon": 127.68, "weathernews_id": "7CDDE9086CB8", "page_url": "https://weathernews.jp/onebox/livecam/okinawa/7CDDE9086CB8/"},
    ]


def _is_image(data: bytes) -> bool:
    # サイズだけでは、夜の暗い写真（小さい）とエラーHTML（小さい）を見分けられない
    # 中身の先頭で判断する：JPEG=FFD8, WebP=RIFF....WEBP, PNG=89PNG
    if not data or len(data) < 1000:
        return False
    if data[:2] == b"\xff\xd8":
        return True
    if data[:4] == b"RIFF" and b"WEBP" in data[:16]:
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    return False

def _try_direct_guess(camera_id, out_path):
    """index.html と同じ直接URLを、10分刻みで直近1時間分試す"""
    now_jst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    for back in (0, 10, 20, 30, 40, 50, 60):
        tt = now_jst - datetime.timedelta(minutes=back)
        tt = tt.replace(minute=(tt.minute // 10) * 10, second=0, microsecond=0)
        ts = tt.strftime("%Y%m%d%H%M00")
        for size in ("1280", "640"):
            for ext in ("jpg", "webp"):
                guess = f"https://gvs.weathernews.jp/livecam/{camera_id}/{size}/{ts}.{ext}"
                try:
                    rr = requests.get(guess, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                    if rr.status_code == 200 and _is_image(rr.content):
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
                if rr.status_code == 200 and _is_image(rr.content):
                    Path(out_path).write_bytes(rr.content)
                    return True, "ok"
                print(f"  image download fail {rr.status_code} len={len(rr.content)} ctype={rr.headers.get('Content-Type')} head={rr.content[:30]!r} -> 時刻をずらして再試行")
                # ページの URL の時刻を、10分ずつ 60分前までずらして試す
                # 例: .../20261119185800.webp -> .../20261119184800.webp
                m_ts = re.search(r'(20\d{12})', img_url)
                if m_ts:
                    base_ts = datetime.datetime.strptime(m_ts.group(1), "%Y%m%d%H%M%S")
                    for back in (10, 20, 30, 40, 50, 60):
                        tt2 = base_ts - datetime.timedelta(minutes=back)
                        ts2 = tt2.strftime("%Y%m%d%H%M00")
                        url2 = img_url[:m_ts.start()] + ts2 + img_url[m_ts.end():]
                        try:
                            rr2 = requests.get(url2, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                            if rr2.status_code == 200 and _is_image(rr2.content):
                                Path(out_path).write_bytes(rr2.content)
                                print(f"  retry ok {url2}")
                                return True, "retry-ts"
                            print(f"  retry fail {ts2} len={len(rr2.content)} ctype={rr2.headers.get('Content-Type')} head={rr2.content[:30]!r}")
                        except Exception:
                            pass
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


def _call_gemini_for_levels(api_key, b64, place_name, slot_ja, slot_ban, levels, models, temp, max_tok):
    lv_str = "、".join(levels)
    lv_desc = {"0": "0=からっと1行", "1": "1=ほどよく2行", "2": "2=こいめ3行", "3": "3=仙人級 長め1段落"}
    lv_line = " / ".join([lv_desc[lv] for lv in levels])
    prompt = "この画像は" + place_name + "のライブカメラの空と風景です。今は" + slot_ja + "です。" + slot_ban + "。画像をよく見て、中原中也風（kyodatsu）と宮沢賢治風（taiyou）の詩を、日本語で作ってください。\n"
    prompt += "条件：\n"
    prompt += "- 今回は濃淡 " + lv_line + " だけ作る\n"
    prompt += "- 1行目は空や雲や光の様子を具体的に\n"
    prompt += "- 2行目以降は風や音や気配を感じる言葉を\n"
    prompt += "- 天気の言葉（晴れ・曇り・雨・風など）を1つだけ入れる\n"
    prompt += "- 説明文やタイトルは不要。JSONだけを返す\n"
    prompt += '- 返却形式は必ずこの形：{"kyodatsu": {"0": "...", "1": "..."}, "taiyou": {"0": "...", "1": "..."}} のように、今回の濃淡だけを入れる\n'
    for model in models:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent?key=" + api_key
            payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}], "generationConfig": {"temperature": temp, "maxOutputTokens": max_tok}}
            r = requests.post(url, json=payload, timeout=60)
            if r.status_code == 404:
                print("  gemini " + model + " 404 " + place_name + ": 次へ")
                continue
            if r.status_code == 429:
                print("  gemini " + model + " 429 " + place_name + ": 20秒待って次へ")
                time.sleep(20)
                continue
            if r.status_code == 503:
                print("  gemini " + model + " 503 " + place_name + ": 5秒待って次へ")
                time.sleep(5)
                continue
            if r.status_code != 200:
                print("  gemini " + model + " status " + str(r.status_code) + ": " + r.text[:300])
                continue
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            m = re.search(r'\{.*\}', text, re.S)
            if m:
                text = m.group(0)
            j = json.loads(text)
            ok = 0
            for poet in ("kyodatsu", "taiyou"):
                for lv in levels:
                    if j.get(poet, {}).get(lv):
                        ok += 1
            print("  gemini ok " + place_name + " model=" + model + " levels=" + lv_str + " parsed=" + str(ok) + "/" + str(len(levels)*2) + " temp=" + str(temp))
            if ok >= len(levels):
                return j, model
        except Exception as e:
            print("  gemini fail " + place_name + " model=" + model + " levels=" + lv_str + ": " + str(e))
            continue
    return None, "fail"


def generate_senjin(image_path, place_name, lat, lon, slot="morning"):
    """仙人級（3）だけを、Gemini 3.8 優先で作る。私が作りたいときに、作りたい都市だけ。"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "fallback-no-key"
    try:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    except Exception as e:
        print(f"  senjin image fail {e}")
        return None, "fallback-no-image"
    slot_ja = {"morning": "朝（6〜10時）", "noon": "昼（11〜15時）", "evening": "夕方（18〜20時）"}.get(slot, slot)
    slot_ban = {"morning": "夕暮れ・夕方・夕日・黄昏・宵・日暮れ・夕焼けなどの夕方の言葉は、絶対に使わない", "noon": "夕暮れ・夕方・夕日・黄昏・朝日・朝霧・夜明けなどの朝夕の言葉は、絶対に使わない", "evening": "朝日・朝霧・夜明け・朝の光などの朝の言葉は、絶対に使わない"}.get(slot, "")
    SENJIN_MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3-flash-preview"]
    j, m = _call_gemini_for_levels(api_key, b64, place_name, slot_ja, slot_ban, ["3"], SENJIN_MODELS, 0.95, 1200)
    if j is None:
        return None, "fail"
    _rep = {"morning": {"夕暮れ": "夜明け", "夕方": "朝", "夕日": "朝日", "黄昏": "夜明け", "宵": "朝", "日暮れ": "夜明け", "夕焼け": "朝焼け"}, "noon": {"夕暮れ": "昼", "夕方": "昼", "夕日": "昼の光", "黄昏": "昼", "夜明け": "朝", "朝日": "昼の光"}, "evening": {"朝日": "夕日", "朝霧": "夕霧", "夜明け": "夕暮れ", "朝の光": "夕の光"}}.get(slot, {})
    for _poet in ("kyodatsu", "taiyou"):
        _txt = j.get(_poet, {}).get("3", "") or ""
        for _k, _v in _rep.items():
            if _k in _txt:
                _txt = _txt.replace(_k, _v)
        if _poet not in j:
            j[_poet] = {}
        j[_poet]["3"] = _txt
    return j, m

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
    SHORT_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3-flash-preview"]  # v64：普段は 3.8 なし
    LONG_MODELS = ["gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]  # v64：普段は 3.8 なし
    _s = SHORT_MODELS[loc_index % len(SHORT_MODELS):] + SHORT_MODELS[:loc_index % len(SHORT_MODELS)]
    _l = LONG_MODELS[loc_index % len(LONG_MODELS):] + LONG_MODELS[:loc_index % len(LONG_MODELS)]
    # v63：短い（0,1）は Lite / temp 0.6 / 500、長い（2,3）は Flash / temp 0.95 / 1200
    # 下の既存ループは使わず、ここで2回呼んで合成する
    slot_ja_tmp = {"morning": "朝（6〜10時）", "noon": "昼（11〜15時）", "evening": "夕方（18〜20時）"}.get(slot, slot)
    slot_ban_tmp = {"morning": "夕暮れ・夕方・夕日・黄昏・宵・日暮れ・夕焼けなどの夕方の言葉は、絶対に使わない", "noon": "夕暮れ・夕方・夕日・黄昏・朝日・朝霧・夜明けなどの朝夕の言葉は、絶対に使わない", "evening": "朝日・朝霧・夜明け・朝の光などの朝の言葉は、絶対に使わない"}.get(slot, "")
    _short_j, _short_m = _call_gemini_for_levels(api_key, b64, place_name, slot_ja_tmp, slot_ban_tmp, ["0", "1"], _s, 0.6, 500)
    _long_j, _long_m = _call_gemini_for_levels(api_key, b64, place_name, slot_ja_tmp, slot_ban_tmp, ["2"], _l, 0.85, 800)  # v64：普段は 2 まで。3 は作らない
    if _short_j is None and _long_j is None:
        return fallback_poems(place_name, lat, lon), "fallback-all-fail"
    _merged = {"kyodatsu": {}, "taiyou": {}}
    for _poet in ("kyodatsu", "taiyou"):
        for _lv in ("0", "1"):
            if _short_j and _short_j.get(_poet, {}).get(_lv):
                _merged[_poet][_lv] = _short_j[_poet][_lv]
        for _lv in ("2",):  # v64：3 はここでは作らない
            if _long_j and _long_j.get(_poet, {}).get(_lv):
                _merged[_poet][_lv] = _long_j[_poet][_lv]
    # 欠けた分は、ある方で補う（片方だけ成功しても、全部空にしない）
    for _poet in ("kyodatsu", "taiyou"):
        for _lv in ("0", "1", "2", "3"):
            if _lv not in _merged[_poet] or not _merged[_poet][_lv]:
                _fb = fallback_poems(place_name, lat, lon)
                _merged[_poet][_lv] = _fb[_poet][_lv]
    # 禁止ワード置き換え（v61 と同じ）
    _rep = {"morning": {"夕暮れ": "夜明け", "夕方": "朝", "夕日": "朝日", "黄昏": "夜明け", "宵": "朝", "日暮れ": "夜明け", "夕焼け": "朝焼け"}, "noon": {"夕暮れ": "昼", "夕方": "昼", "夕日": "昼の光", "黄昏": "昼", "夜明け": "朝", "朝日": "昼の光"}, "evening": {"朝日": "夕日", "朝霧": "夕霧", "夜明け": "夕暮れ", "朝の光": "夕の光"}}.get(slot, {})
    for _poet in ("kyodatsu", "taiyou"):
        for _lv in ("0", "1", "2", "3"):
            _txt = _merged[_poet][_lv] or ""
            for _k, _v in _rep.items():
                if _k in _txt:
                    _txt = _txt.replace(_k, _v)
            _merged[_poet][_lv] = _txt
    return _merged, (_short_m + "+" + _long_m)
    models = GEMINI_MODELS[loc_index % len(GEMINI_MODELS):] + GEMINI_MODELS[:loc_index % len(GEMINI_MODELS)]
    # 時間帯を Gemini に伝えないと、朝の低い太陽を夕日と間違える
    slot_ja = {"morning": "朝（6〜10時）", "noon": "昼（11〜15時）", "evening": "夕方（18〜20時）"}.get(slot, slot)
    slot_ban = {"morning": "夕暮れ・夕方・夕日・黄昏・宵・日暮れ・夕焼けなどの夕方の言葉は、絶対に使わない", "noon": "夕暮れ・夕方・夕日・黄昏・朝日・朝霧・夜明けなどの朝夕の言葉は、絶対に使わない", "evening": "朝日・朝霧・夜明け・朝の光などの朝の言葉は、絶対に使わない"}.get(slot, "")
    prompt = f"""この画像は{place_name}のライブカメラの空と風景です。今は{slot_ja}です。{slot_ban}。画像をよく見て、中原中也風（kyodatsu）と宮沢賢治風（taiyou）の詩を、日本語で作ってください。
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
            # 時間帯の禁止ワード：捨てずに、朝の言葉に置き換える
            # v60 は捨ててたので、全モデルが捨てられて、古い詩のまま（全く同じ文面）になった
            _rep = {"morning": {"夕暮れ":"夜明け","夕方":"朝","夕日":"朝日","黄昏":"夜明け","宵":"朝","日暮れ":"夜明け","夕焼け":"朝焼け"}, "noon": {"夕暮れ":"昼","夕方":"昼","夕日":"昼の光","黄昏":"昼","夜明け":"朝","朝日":"昼の光"}, "evening": {"朝日":"夕日","朝霧":"夕霧","夜明け":"夕暮れ","朝の光":"夕の光"}}.get(slot, {})
            _fixed = 0
            for poet in ("kyodatsu", "taiyou"):
                for lv in ("0", "1", "2", "3"):
                    _txt = j.get(poet, {}).get(lv, "") or ""
                    for _k, _v in _rep.items():
                        if _k in _txt:
                            _txt = _txt.replace(_k, _v)
                            _fixed += 1
                    j[poet][lv] = _txt
            if _fixed:
                print(f"  gemini {model} 禁止ワード {_fixed}件を置き換え {place_name} slot={slot}")
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
    print(f"now JST {now} hour={hour} FORCE_POEM={os.environ.get('FORCE_POEM')}")
    old = {}
    if Path("data.json").exists():
        try:
            old = json.loads(Path("data.json").read_text(encoding="utf-8"))
        except Exception as e:
            print(f"old data.json read fail: {e}")
            old = {}
    old_locs = old.get("locations", {}) if isinstance(old, dict) else {}
    data = {"updated_at": now, "locations": {}}
    # --- v62 根本修正：FORCE はスケジュールを無視する ---
    _force = os.environ.get("FORCE_POEM", "").lower() in ("1", "true", "yes")
    _force_slot = os.environ.get("FORCE_SLOT", "").strip()  # morning / noon / evening
    _force_city = os.environ.get("FORCE_CITY", "").strip()  # kobe だけ、など
    sched = POEM_SCHEDULE.get(hour)
    if hour in BUSY_HOURS and not _force:
        print(f"BUSY_HOUR {hour}: 詩は作らない（画像だけ）")
        sched = None
    if _force:
        print(f"FORCE_POEM=1: スケジュールを無視して生成します slot={_force_slot or '(時間から決める)'} city={_force_city or '(全部)'}")
        # FORCE のときは、時間から slot を決める（FORCE_SLOT があれば、それを優先）
        if _force_slot in ("morning", "noon", "evening"):
            _slot = _force_slot
        elif 6 <= hour <= 10:
            _slot = "morning"
        elif 11 <= hour <= 17:
            _slot = "noon"
        elif 18 <= hour <= 20:
            _slot = "evening"
        else:
            _slot = "morning" if hour < 12 else ("noon" if hour < 18 else "evening")
        # 全都市を対象にする（FORCE_CITY があれば絞るのは、後のループで）
        sched = {"slot": _slot, "targets": [l["id"] for l in load_locations()]}
    for loc_index, loc in enumerate(load_locations()):
        key = loc["id"]
        name = loc["name"]
        out = f"images/{key}.jpg"
        existing = old_locs.get(key, {})
        ok, status = fetch_weathernews(loc["weathernews_id"], out, loc["page_url"])
        do_gen = False
        slot = None
        _skip_reason = ""
        if _force_city and key != _force_city:
            _skip_reason = f"FORCE_CITY={_force_city} のため、対象外"
        elif sched and key in sched["targets"]:
            slot = sched["slot"]
            if existing.get("poem_date") == now[:10] and existing.get("poem_slot") == slot and existing.get("poems") and not _force:
                _skip_reason = f"poem already {now[:10]} {slot} -> keep（生成しません）"
                do_gen = False
            else:
                do_gen = True
        else:
            if not sched:
                _skip_reason = f"hour={hour} は POEM_SCHEDULE にない → 生成しません（これが今までの根本原因）"
            else:
                _skip_reason = f"key={key} は今の targets={sched.get('targets')} にない → 生成しません"
        if not do_gen:
            print(f"{key}: SKIP {_skip_reason}")
        # 既存の詩に禁止ワードが入ってたら、FORCE なしでも作り直す（自己修復）
        if not do_gen and existing.get("poems") and existing.get("poem_slot") in ("morning", "noon", "evening"):
            _ban2 = {"morning": ["夕暮れ","夕方","夕日","黄昏","夕焼け"], "noon": ["夕暮れ","夕方","夕日","黄昏"], "evening": ["朝日","夜明け"]}.get(existing.get("poem_slot"), [])
            _all = ""
            for _p in ("kyodatsu", "taiyou"):
                for _lv in ("0","1","2","3"):
                    _all += existing["poems"].get(_p, {}).get(_lv, "") or ""
            if any(w in _all for w in _ban2):
                print(f"{key}: SELF-HEAL 既存の詩に禁止ワードあり → 作り直します")
                do_gen = True
                slot = existing.get("poem_slot")
                _skip_reason = ""
        if do_gen:
            print(f"{key}: poem slot={slot} gen...")
            poems, model = generate_poems(out, name, loc.get("lat"), loc.get("lon"), loc_index=loc_index, slot=slot)
            # v64：普段は仙人級を作らないので、既存の 3 を残す
            if existing.get("poems"):
                for _p in ("kyodatsu", "taiyou"):
                    _old3 = existing["poems"].get(_p, {}).get("3")
                    if _old3:
                        poems[_p]["3"] = _old3
            # v64：仙人級オンデマンド — FORCE_SENJIN=1 のときだけ、3 を 3.8 優先で作る
            if os.environ.get("FORCE_SENJIN", "").lower() in ("1", "true", "yes"):
                _fc = os.environ.get("FORCE_CITY", "").strip()
                if not _fc or _fc == key:
                    _ss = os.environ.get("FORCE_SLOT", "").strip() or slot
                    print(f"{key}: SENJIN on-demand slot={_ss} model=3.8優先")
                    _sj, _sm = generate_senjin(out, name, loc.get("lat"), loc.get("lon"), slot=_ss)
                    if _sj:
                        for _p in ("kyodatsu", "taiyou"):
                            if _sj.get(_p, {}).get("3"):
                                poems[_p]["3"] = _sj[_p]["3"]
                        model = model + "+" + _sm + "(senjin)"
                    else:
                        print(f"{key}: SENJIN fail -> 既存の 3 を残す")
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
