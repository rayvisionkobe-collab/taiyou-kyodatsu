"""
① 修正版 v3 – 緊急用プロンプトを、自動で作る
- 場所ごとに、2つ作る
  emergency/emergency_prompt_<id>_kyodatsu.txt
  emergency/emergency_prompt_<id>_taiyou.txt
- 旧ファイル (emergency_prompt_<id>.txt) は、虚脱版として、残す (互換)
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
        code = c.get("weather_code", 0)
        w = "晴れ" if code in (0,1) else "曇り" if code in (2,3) else "雨" if code in (45,48,51,53,55,61,63,65,80,81,82) else "雪" if code in (71,73,75,77,85,86) else "曇り"
        precip = c.get("precipitation", 0)
        wind = c.get("wind_speed_10m", 0)
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
    # テンプレを読む – 新しい2つがなければ、旧1つを使う
    tmpl_k = None
    tmpl_t = None
    if Path("emergency_prompt_template_kyodatsu.txt").exists():
        tmpl_k = Path("emergency_prompt_template_kyodatsu.txt").read_text(encoding="utf-8")
    elif Path("emergency_prompt_template.txt").exists():
        tmpl_k = Path("emergency_prompt_template.txt").read_text(encoding="utf-8")
    if Path("emergency_prompt_template_taiyou.txt").exists():
        tmpl_t = Path("emergency_prompt_template_taiyou.txt").read_text(encoding="utf-8")
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
        raw_name = loc.get("name", "神戸")
        place = raw_name[:2] if len(raw_name) >= 2 else raw_name
        id_map = {"kobe": "神戸", "maiko": "神戸", "kobe_air": "神戸", "kobe_airport": "神戸",
                  "tokyo": "東京", "sapporo": "札幌", "fukuoka": "福岡", "naha": "那覇", "fuji": "富士"}
        place = id_map.get(loc.get("id", ""), place)
        lat = loc.get("lat", 34.68); lon = loc.get("lon", 135.19)
        weather = get_weather(lat, lon) + f" {place}"
        lid = loc.get("id", "kobe")
        if tmpl_k:
            out_k = Path(f"emergency/emergency_prompt_{lid}_kyodatsu.txt")
            out_k.write_text(tmpl_k.replace("{place}", place).replace("{weather}", weather).replace("{time_slot}", slot), encoding="utf-8")
            # 互換: 旧ファイル名も、虚脱版で作る
            out_old = Path(f"emergency/emergency_prompt_{lid}.txt")
            out_old.write_text(tmpl_k.replace("{place}", place).replace("{weather}", weather).replace("{time_slot}", slot), encoding="utf-8")
            print(f"wrote {out_k} – {place} / {weather} / {slot}")
        if tmpl_t:
            out_t = Path(f"emergency/emergency_prompt_{lid}_taiyou.txt")
            out_t.write_text(tmpl_t.replace("{place}", place).replace("{weather}", weather).replace("{time_slot}", slot), encoding="utf-8")
            print(f"wrote {out_t} – {place} / {weather} / {slot}")

if __name__ == "__main__":
    main()
