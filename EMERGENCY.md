# 緊急用 – Gemini手動生成 → 公開ページ差し替え

自動生成がうまくいかないときの、緊急手順です。

## 流れ (2ステップ)

```
1. プロンプトをコピー → Geminiに貼る → 詩をもらう
2. 詩を貼って、Actionsを実行 → 公開ページの詩が差し替わる
```

## ① プロンプトをもらう

`emergency/` の中に、場所ごとのプロンプトがあります。

```
emergency/emergency_prompt_kobe.txt
emergency/emergency_prompt_tokyo.txt
...
```

1時間に1回、自動で作り直されます (天気・時間帯が入ってます)。
GitHubでそのファイルを開いて、[ Copy ] → Geminiに貼ってください。

なければ、`Actions → Generate Emergency Prompt → Run workflow` で、今すぐ作れます。

## ② 詩を差し替える

1. GitHub → [ Actions ] → [ Manual Poem Update ] → [ Run workflow ]
2. `place` を選ぶ (例: kobe)
3. `poem_text` に、Geminiの出力をそのまま貼る

```
KYODATSU0: 神戸の曇り空、肌寒い夕方でも灯りは温かい
KYODATSU1: 神戸の街に灰色の曇りが降りる、肌寒い心拍に似た夜の予感
...
```

4. [ Run workflow ] を押す
5. 1〜2分待つ → 公開ページを開き直す → 詩が差し替わってます

※ 次の自動生成 (30分ごと) で、上書きされます。緊急時だけ使ってください。
※ 失敗したら、もう一度、同じ手順で貼り直せます。

## プロンプト (テンプレ)

`emergency_prompt_template.txt` が、元のテンプレです。
`generate_emergency_prompt.py` が、天気・時間帯を入れて、場所ごとに作ります。
