"""
② 手動で作った詩を、公開ページに差し替える
- 入力: place (例: kobe) + poem_text (Geminiの出力、そのまま)
- 処理: KYODATSU0〜3 を抜く → クリーニング → data.json を更新
- クリーニング: (19文字) / 【】 / ※ / ``` / 。。 を、消す
"""
import json, re, sys, datetime
from pathlib import Path

def clean_poem(s):
    s = (s or "").strip()
    # コードブロック・引用符を消す
    s = s.replace("```", "").strip().strip('"').strip("'").strip()
    # (19文字) みたいな注釈を消す
    s = re.sub(r"\(\s*\d+\s*文字\s*\)", "", s)
    s = re.sub(r"【[^】]*】", "", s)
    s = re.sub(r"※.*$", "", s)
    # 。。 → 。
    s = re.sub(r"。\s*。+", "。", s)
    s = re.sub(r"、\s*、+", "、", s)
    # 先頭の KYODATSU0: などを、消し忘れ対策
    s = re.sub(r"^KYODATSU\d+\s*[:：]\s*", "", s)
    # 0番は、20文字を超えたら、切り捨てる
    return s.strip()

def parse_poem_text(text):
    # KYODATSU0: 〜 の行を、抜く
    poems = {}
    # まず、行ごとに分ける
    for line in (text or "").splitlines():
        m = re.match(r"\s*KYODATSU\s*(\d)\s*[:：]\s*(.+)", line.strip())
        if m:
            poems[f"KYODATSU{m.group(1)}"] = clean_poem(m.group(2))
    # 1行にまとまってる場合 (カンマ区切りなど) にも、対応
    if not poems:
        # KYODATSU0: ... KYODATSU1: ... が、1行に並んでる場合
        parts = re.split(r"KYODATSU\s*(\d)\s*[:：]\s*", text or "")
        # parts = ["", "0", "詩...", "1", "詩...", ...]
        for i in range(1, len(parts)-1, 2):
            poems[f"KYODATSU{parts[i]}"] = clean_poem(parts[i+1])
    # 0番だけ、20文字で切り捨て
    if "KYODATSU0" in poems and len(poems["KYODATSU0"]) > 20:
        poems["KYODATSU0"] = poems["KYODATSU0"][:20]
    return poems

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", required=True, help="例: kobe / tokyo / maiko")
    ap.add_argument("--poem-text", default="", help="Geminiの出力、そのまま")
    ap.add_argument("--poem0", default="")
    ap.add_argument("--poem1", default="")
    ap.add_argument("--poem2", default="")
    ap.add_argument("--poem3", default="")
    args = ap.parse_args()

    poems = parse_poem_text(args.poem_text)
    # 個別入力があれば、そちらを優先
    if args.poem0: poems["KYODATSU0"] = clean_poem(args.poem0)
    if args.poem1: poems["KYODATSU1"] = clean_poem(args.poem1)
    if args.poem2: poems["KYODATSU2"] = clean_poem(args.poem2)
    if args.poem3: poems["KYODATSU3"] = clean_poem(args.poem3)
    if not poems:
        print("ERROR: 詩が見つかりません。KYODATSU0: 〜 の形で貼ってください")
        sys.exit(1)
    print(f"parsed: {poems}")

    # data.json を読む
    data = {"updated_at": "", "locations": {}}
    if Path("data.json").exists():
        try:
            data = json.loads(Path("data.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    if "locations" not in data:
        data["locations"] = {}

    # 場所を探す – id が一致すれば、それ。なければ、name に place が含まれるもの
    target_key = None
    for k in data["locations"].keys():
        if k == args.place or args.place in k:
            target_key = k; break
    if not target_key:
        # config.json から、idを探す
        if Path("config.json").exists():
            try:
                cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))
                for loc in cfg.get("locations", []):
                    if loc.get("id") == args.place:
                        target_key = loc.get("id"); break
            except Exception:
                pass
    if not target_key:
        target_key = args.place

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
    entry = data["locations"].get(target_key, {})
    # 両方の形で、保存 – 旧 (poem) と、新 (poems / KYODATSU0〜3)
    joined = "\n".join([poems.get(f"KYODATSU{i}", "") for i in range(4) if poems.get(f"KYODATSU{i}")])
    entry.update({
        "poem": joined,
        "poemFull": joined,
        "poems": poems,
        "KYODATSU0": poems.get("KYODATSU0", ""),
        "KYODATSU1": poems.get("KYODATSU1", ""),
        "KYODATSU2": poems.get("KYODATSU2", ""),
        "KYODATSU3": poems.get("KYODATSU3", ""),
        "model": "manual-gemini",
        "manual": True,
        "updated_at": now,
    })
    data["locations"][target_key] = entry
    data["updated_at"] = now
    Path("data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"updated {target_key} in data.json")

if __name__ == "__main__":
    main()
