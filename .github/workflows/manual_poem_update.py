"""
② 修正版 – 手動詩を、公開ページに差し替える
- 修正1: 改行が潰れて1行になっても、KYODATSU0: ... KYODATSU1: ... を全部拾う
- 修正2: poems を {kyodatsu:{0..3}, taiyou:{0..3}} の形で保存する
         taiyou は、今回貼らなかったら、元のまま残す (消さない)
- 修正3: 旧バグで壊れた data.json (poems がフラット、poem が1行) を、直す
"""
import json, re, sys, datetime, argparse
from pathlib import Path

def clean(s):
    s = (s or "").strip()
    s = s.replace("```", "").strip().strip('"').strip("'").strip()
    s = re.sub(r"\(\s*\d+\s*文字\s*\)", "", s)
    s = re.sub(r"【[^】]*】", "", s)
    s = re.sub(r"※.*$", "", s)
    s = re.sub(r"。\s*。+", "。", s)
    s = re.sub(r"、\s*、+", "、", s)
    return s.strip()

def parse_all(text):
    # 改行があっても、なくても、拾えるように、全体から正規表現で抜く
    # KYODATSU0: ... 次の KYODATSU1: まで、を1つとして抜く
    out = {"kyodatsu": {}, "taiyou": {}}
    if not text:
        return out
    # 改行をスペースにしない – そのまま、正規表現で、ヘッダーごとに区切る
    pat = re.compile(r"(KYODATSU|TAIYOU)\s*([0-3])\s*[:：]\s*", re.IGNORECASE)
    parts = pat.split(text)
    # parts = [前置き, "KYODATSU", "0", "詩...", "KYODATSU", "1", "詩...", ...]
    for i in range(1, len(parts)-2, 3):
        poet_raw, lvl, body = parts[i], parts[i+1], parts[i+2]
        poet = "kyodatsu" if poet_raw.upper() == "KYODATSU" else "taiyou"
        # body の末尾に、次のヘッダーが混ざってたら、既に split で切れてるので、OK
        # ただし、body に "KYODATSU" が残ってたら、切る
        body = body.strip()
        # body の中に、改行で別の文が入ってたら、最初の行だけ？ – 3番は長いので、全部残す
        # ただし、body の後ろに、説明文 (例: "以上です") が入ってたら、切る
        body = re.split(r"\n\s*(以上です|以上|おわり|---)", body)[0].strip()
        val = clean(body)
        if not val:
            continue
        # 0番は、20文字で切り捨て (28文字まで許す、元の fetch.py と同じ)
        if lvl == "0" and len(val) > 28:
            cut = val.find("。")
            if cut != -1 and cut < 28:
                val = val[:cut+1]
            else:
                val = val[:28] + "。"
        out[poet][lvl] = val
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", required=True)
    ap.add_argument("--poem-text", default="")
    # 個別入力 – 改行が潰れる問題を避けるため、1つずつも受け取る
    ap.add_argument("--kyodatsu0", default="")
    ap.add_argument("--kyodatsu1", default="")
    ap.add_argument("--kyodatsu2", default="")
    ap.add_argument("--kyodatsu3", default="")
    ap.add_argument("--taiyou0", default="")
    ap.add_argument("--taiyou1", default="")
    ap.add_argument("--taiyou2", default="")
    ap.add_argument("--taiyou3", default="")
    # 旧名 (poem0 など) も、互換で受け取る
    ap.add_argument("--poem0", default="")
    ap.add_argument("--poem1", default="")
    ap.add_argument("--poem2", default="")
    ap.add_argument("--poem3", default="")
    args = ap.parse_args()

    parsed = parse_all(args.poem_text)
    # 個別入力があれば、そちらを優先 (KYODATSU だけでも、TAIYOU だけでもOK)
    if args.kyodatsu0 or args.poem0: parsed["kyodatsu"]["0"] = clean(args.kyodatsu0 or args.poem0)
    if args.kyodatsu1 or args.poem1: parsed["kyodatsu"]["1"] = clean(args.kyodatsu1 or args.poem1)
    if args.kyodatsu2 or args.poem2: parsed["kyodatsu"]["2"] = clean(args.kyodatsu2 or args.poem2)
    if args.kyodatsu3 or args.poem3: parsed["kyodatsu"]["3"] = clean(args.kyodatsu3 or args.poem3)
    if args.taiyou0: parsed["taiyou"]["0"] = clean(args.taiyou0)
    if args.taiyou1: parsed["taiyou"]["1"] = clean(args.taiyou1)
    if args.taiyou2: parsed["taiyou"]["2"] = clean(args.taiyou2)
    if args.taiyou3: parsed["taiyou"]["3"] = clean(args.taiyou3)
    # 空を除く
    parsed["kyodatsu"] = {k:v for k,v in parsed["kyodatsu"].items() if v}
    parsed["taiyou"] = {k:v for k,v in parsed["taiyou"].items() if v}
    if not parsed["kyodatsu"] and not parsed["taiyou"]:
        print("ERROR: 詩が見つかりません。KYODATSU0: 〜 の形で貼ってください")
        sys.exit(1)
    print(f"parsed kyodatsu={parsed['kyodatsu']}")
    print(f"parsed taiyou={parsed['taiyou']}")

    data = {"updated_at": "", "locations": {}}
    if Path("data.json").exists():
        try:
            data = json.loads(Path("data.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    if "locations" not in data:
        data["locations"] = {}

    # 場所を探す
    target = None
    for k in data["locations"].keys():
        if k == args.place or args.place in k:
            target = k; break
    if not target:
        target = args.place

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
    entry = data["locations"].get(target, {})
    # 旧バグで壊れた poems (フラットな {KYODATSU0: ...}) は、捨てる
    old_poems = entry.get("poems", {})
    if not isinstance(old_poems, dict) or "kyodatsu" not in old_poems and "taiyou" not in old_poems:
        # フラット or 壊れてる → 一旦、空にして、今回の分だけ入れる
        # taiyou が消えた分は、次の自動生成で復活する (今回は、kyodatsu だけ更新する)
        print(f"warn: {target} poems was flat/broken, rebuilding. old keys={list(old_poems.keys()) if isinstance(old_poems, dict) else type(old_poems)}")
        old_poems = {}
    # 正しい形にそろえる
    new_poems = {}
    for poet in ["kyodatsu", "taiyou"]:
        old = old_poems.get(poet, {}) if isinstance(old_poems.get(poet), dict) else {}
        merged = dict(old)
        merged.update(parsed[poet])  # 今回貼った分だけ、上書き
        if merged:
            new_poems[poet] = merged
    entry["poems"] = new_poems
    # 旧バグの残り: poem (1行) と、KYODATSU0 などのフラットキーを、消す
    # これが残ってると、index.html が、poem を優先して、全部同じに見える
    entry.pop("poem", None)
    entry.pop("poemFull", None)
    for k in ["KYODATSU0","KYODATSU1","KYODATSU2","KYODATSU3","TAIYOU0","TAIYOU1","TAIYOU2","TAIYOU3"]:
        entry.pop(k, None)
    entry["model"] = "manual-gemini"
    entry["manual"] = True
    entry["updated_at"] = now
    data["locations"][target] = entry
    data["updated_at"] = now
    Path("data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"updated {target} poems={new_poems}")

if __name__ == "__main__":
    main()
