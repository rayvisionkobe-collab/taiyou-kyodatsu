"""
① 緊急用プロンプトを、自動で作る
- config.json の locations を読む
- Open-Meteo (キー不要) で、今の天気を取る
- emergency/emergency_prompt_<id>.txt を、場所ごとに作る
- GitHub Actions で、1時間に1回、自動実行する
"""
import json, datetime, urllib.request
from pathlib import Path

def get_weather(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,precipitation,wind_speed_10m,weather_code&timezone=Asia%2FTokyo"
        with urllib.request.urlopen(url, timeout=15) as r:
            j = json.loads(r.read().decode())
        c = j.get("current", {})
        temp = c.get("temperature_2m", 0)
        # 簡易: 最高・最低は、今の気温で代用 (緊急用なので、厳密でなくてOK)
        code = c.get("weather_code", 0)
        w = "晴れ" if code in (0,1) else "曇り" if code in (2,3) else "雨" if code in (45,48,51,53,55,61,63,65,80,81,82) else "雪" if code in (71,73,75,77,85,86) else "曇り"
        precip = c.get("precipitation", 0)
        wind = c.get("wind_speed_10m", 0)
        # 体感は、プロンプトで使わない (数字を入れないため) – 天気文は、Gemini用に、元の形で
        return f"{w} {temp:.0f}℃ / {temp:.0f}℃ 降水{precip:.0f}mm 風{wind:.0f}m"
    except Exception as e:
        print(f"weather fail: {e}")
        return "曇り 17℃ / 16℃ 降水0mm 風2m"

def time_slot(hour):
    if 5 <= hour <= 9:
        return "朝"
    if 10 <= hour <= 15:
        return "昼"
    if 16 <= hour <= 19:
        return "夕方"
    return "夜"

def main():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    slot = time_slot(now.hour)
    tmpl = Path("emergency_prompt_template.txt").read_text(encoding="utf-8")
    # config.json がなければ、神戸だけ
    locs = []
    if Path("config.json").exists():
        try:
            cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))
            locs = cfg.get("locations", [])
        except Exception:
            pass
    if not locs:
        locs = [{"id": "kobe", "name": "神戸"}]
    Path("emergency").mkdir(exist_ok=True)
    for loc in locs:
        # name から、場所名だけ抜く (例: "舞子ビラ・明石海峡大橋" → "神戸" にしたい場合は、idで対応)
        # id が kobe系なら、神戸、それ以外は name の最初の2文字を使う簡易処理
        # config.json の name が "神戸空港" なら、"神戸"、"東京スカイツリー" なら、"東京"
        raw_name = loc.get("name", "神戸")
        place = raw_name[:2] if len(raw_name) >= 2 else raw_name
        # id に合わせる: kobe → 神戸, tokyo → 東京, など
        id_map = {"kobe": "神戸", "maiko": "神戸", "kobe_air": "神戸", "kobe_airport": "神戸",
                  "tokyo": "東京", "sapporo": "札幌", "fukuoka": "福岡", "naha": "那覇", "fuji": "富士"}
        place = id_map.get(loc.get("id", ""), place)
        lat = loc.get("lat", 34.68); lon = loc.get("lon", 135.19)
        weather = get_weather(lat, lon) + f" {place}"
        # 天気文の最後に、場所を付ける (元の例: "曇 17℃ / 16℃ 降水0mm 風2m 神戸")
        prompt = tmpl.replace("{place}", place).replace("{weather}", weather).replace("{time_slot}", slot)
        out = Path(f"emergency/emergency_prompt_{loc.get('id','kobe')}.txt")
        out.write_text(prompt, encoding="utf-8")
        print(f"wrote {out} – {place} / {weather} / {slot}")

if __name__ == "__main__":
    main()
