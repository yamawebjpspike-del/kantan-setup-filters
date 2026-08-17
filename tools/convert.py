#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EasyList（Adblock Plus 記法）を Safari コンテンツブロッカーの JSON に変換する。

【なぜこのスクリプトが存在するか】
Safari のコンテンツブロッカーは独自の JSON 形式しか受け付けない。
一方 EasyList は Adblock Plus 記法で書かれている。両者は 1 対 1 対応しないため、
Safari が理解できる部分だけを抽出して変換する必要がある。

【設計方針（開発計画書 v3 の 4.2 章 M を参照）】
1. 変換はここ（Mac / GitHub Actions 上）で行い、iOS アプリ内では行わない。
   → アプリ本体に依存ライブラリを持ち込まないため。
2. ルール数は 30,000 を上限とする。
   → Apple の公称上限は 150,000 だが、iPhone 12 / iOS 18 で 45,000 から
     読み込み失敗の報告がある。ターゲットは古い端末を使う高齢者なので保守的に。
3. コスメティックフィルタ（##selector）は v1 では変換しない。
   → ルール数を大きく消費するうえ、サイトの表示を壊すリスクが高い。
     高齢者は「表示が崩れた原因」を特定できないため、安全側に倒す。
4. 例外ルール（@@）は必ず全部残す。
   → 誤ブロックを防ぐためのルールなので、これを削ると壊れやすくなる。

【ライセンス】
出力される JSON は EasyList の二次的著作物であり、
Creative Commons Attribution-ShareAlike 3.0 Unported のもとで配布する。
出典: The EasyList authors (https://easylist.to/)
"""

import argparse
import json
import re
import sys
import urllib.request

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

EASYLIST_URL = "https://easylist.to/easylist/easylist.txt"

# Safari のルール数上限。公称 150,000 だが実運用の失敗報告を踏まえて保守的に設定。
DEFAULT_LIMIT = 30_000

# Adblock Plus のリソース種別 → Safari の resource-type
# Safari が受け付けるのは以下の 9 種類のみ:
#   document, image, style-sheet, script, font, raw, svg-document, media, popup
RESOURCE_TYPE_MAP = {
    "script": "script",
    "image": "image",
    "stylesheet": "style-sheet",
    "font": "font",
    "media": "media",
    "subdocument": "document",
    "document": "document",
    "xmlhttprequest": "raw",
    "websocket": "raw",
    "other": "raw",
    "object": "raw",
    "object-subrequest": "raw",
    "ping": "raw",
    "beacon": "raw",
    "popup": "popup",
}

# Safari に等価物がなく、含まれていたらルールごと捨てるオプション。
# これらを無理に変換すると、意図しない挙動になる。
UNSUPPORTED_OPTIONS = {
    "csp", "removeparam", "redirect", "redirect-rule", "replace",
    "generichide", "elemhide", "genericblock", "specifichide",
    "empty", "mp4", "inline-script", "inline-font", "app",
    "denyallow", "method", "header", "to", "from", "badfilter",
    "stealth", "cookie", "network", "permissions", "urltransform",
}

# 無視してよいオプション（変換に影響しない）
IGNORED_OPTIONS = {"important", "all", "popunder"}


# ---------------------------------------------------------------------------
# 変換ロジック
# ---------------------------------------------------------------------------

def escape_for_url_filter(text: str) -> str:
    """
    Safari の url-filter は限定的な正規表現しか解釈しない。
    正規表現として意味を持つ文字をエスケープする。
    """
    # 注意: / はエスケープしない。正規表現上の意味を持たず、
    # エンジンによっては未知のエスケープとしてエラーになるため。
    # | は Safari が選択（alternation）を解釈しない可能性があるので必ずエスケープする。
    return re.sub(r"([.+?^${}()\[\]\\|*])", r"\\\1", text)


def pattern_to_url_filter(pattern: str):
    """
    Adblock Plus のパターンを Safari の url-filter（正規表現）に変換する。
    変換できない場合は None を返す。

    対応する記法:
      ||example.com^   ドメインアンカー
      |http://...      先頭アンカー
      ...|             末尾アンカー
      *                ワイルドカード
      ^                セパレータ
      /regex/          生の正規表現（そのまま渡す）
    """
    # 生の正規表現はそのまま使う。ただし Safari が解釈できるとは限らないので慎重に。
    if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
        return pattern[1:-1]

    result = ""
    i = 0
    n = len(pattern)

    # 先頭のアンカー処理
    if pattern.startswith("||"):
        # ドメインアンカー。
        # スキームとサブドメインを許容し、ドメイン直後にセパレータが来ることを要求する。
        # 末尾のセパレータ要求がないと example.com が example.com.evil.com に
        # 誤マッチするため、これは重要。
        result += r"^https?://([^/]+\.)?"
        i = 2
    elif pattern.startswith("|"):
        result += "^"
        i = 1

    # 末尾のアンカー
    end_anchor = False
    if pattern.endswith("|") and not pattern.endswith(r"\|"):
        n -= 1
        end_anchor = True

    while i < n:
        ch = pattern[i]
        if ch == "*":
            result += ".*"
        elif ch == "^":
            # セパレータ文字。英数字・ドット・ハイフン・アンダースコア・% 以外にマッチ。
            # 文字列の終端にもマッチすべきだが Safari では表現しにくいので近似する。
            result += r"[^a-zA-Z0-9._%-]"
        else:
            result += escape_for_url_filter(ch)
        i += 1

    if end_anchor:
        result += "$"

    if not result:
        return None
    return result


def parse_options(option_string: str):
    """
    $ 以降のオプション文字列を解析する。
    変換できないオプションが含まれていたら None を返す（ルールごと破棄）。
    """
    opts = {
        "resource_types": set(),
        "excluded_resource_types": set(),
        "load_type": None,          # "third-party" / "first-party"
        "if_domain": [],
        "unless_domain": [],
        "case_sensitive": False,
    }

    for raw in option_string.split(","):
        raw = raw.strip()
        if not raw:
            continue

        negated = raw.startswith("~")
        name = raw[1:] if negated else raw

        # domain=a.com|~b.com の形式
        if name.startswith("domain="):
            for d in name[len("domain="):].split("|"):
                d = d.strip().lower()
                if not d:
                    continue
                if d.startswith("~"):
                    # Safari の unless-domain は先頭に * を付けるとサブドメインも含む
                    opts["unless_domain"].append("*" + d[1:])
                else:
                    opts["if_domain"].append("*" + d)
            continue

        if name == "third-party":
            opts["load_type"] = "first-party" if negated else "third-party"
            continue

        if name == "match-case":
            opts["case_sensitive"] = True
            continue

        if name in IGNORED_OPTIONS:
            continue

        if name in RESOURCE_TYPE_MAP:
            if negated:
                opts["excluded_resource_types"].add(RESOURCE_TYPE_MAP[name])
            else:
                opts["resource_types"].add(RESOURCE_TYPE_MAP[name])
            continue

        # オプション名の前半だけで判定（csp=... など値付きに対応）
        base = name.split("=")[0]
        if base in UNSUPPORTED_OPTIONS:
            return None

        # 未知のオプションは安全側に倒して破棄する
        return None

    # ~script のような否定だけが指定された場合、それ以外の全種別を対象にする
    if opts["excluded_resource_types"] and not opts["resource_types"]:
        all_types = set(RESOURCE_TYPE_MAP.values())
        opts["resource_types"] = all_types - opts["excluded_resource_types"]

    return opts


def convert_line(line: str):
    """
    EasyList の 1 行を Safari のルール 1 個に変換する。
    変換できない行は None を返す。
    戻り値: (rule_dict, is_exception, priority)
    """
    line = line.strip()

    # コメント・空行
    if not line or line.startswith("!") or line.startswith("["):
        return None

    # コスメティックフィルタは v1 では扱わない（設計方針 3 を参照）
    if "##" in line or "#@#" in line or "#?#" in line or "#$#" in line:
        return None

    is_exception = line.startswith("@@")
    if is_exception:
        line = line[2:]

    # オプション部分を切り出す
    pattern = line
    options = None
    dollar = line.rfind("$")
    # 正規表現リテラル内の $ は除外する
    if dollar > 0 and not (line.startswith("/") and line.endswith("/")):
        pattern = line[:dollar]
        options = parse_options(line[dollar + 1:])
        if options is None:
            return None

    url_filter = pattern_to_url_filter(pattern)
    if not url_filter:
        return None

    # 極端に短いパターンは何にでもマッチしてしまい危険なので捨てる
    if len(pattern.strip("|^*")) < 3:
        return None

    trigger = {"url-filter": url_filter}

    if options:
        # url-filter-is-case-sensitive の既定値は false なので、
        # true のときだけ書き出す。30,000 件では 1MB 以上の差になる。
        if options["case_sensitive"]:
            trigger["url-filter-is-case-sensitive"] = True
        if options["resource_types"]:
            trigger["resource-type"] = sorted(options["resource_types"])
        if options["load_type"]:
            trigger["load-type"] = [options["load_type"]]
        if options["if_domain"]:
            trigger["if-domain"] = options["if_domain"]
        if options["unless_domain"]:
            trigger["unless-domain"] = options["unless_domain"]

    action = {"type": "ignore-previous-rules" if is_exception else "block"}

    # 優先度: ドメインアンカー（||）のルールを最優先で残す。
    # 大手広告配信ドメインを丸ごと止めるルールが最も効果が高く、破壊率が低いため。
    priority = 0
    if pattern.startswith("||"):
        priority = 2
    elif "*" not in pattern:
        priority = 1

    return {"trigger": trigger, "action": action}, is_exception, priority


# ---------------------------------------------------------------------------
# 検証
# ---------------------------------------------------------------------------

def validate(rules, limit, min_rules=1000):
    """
    出力前の検証。壊れた JSON をコミットしないための安全装置。
    問題があれば例外を投げる。
    """
    if not isinstance(rules, list):
        raise ValueError("出力がリストではありません")

    if len(rules) == 0:
        raise ValueError("ルールが 0 件です。取得か変換に失敗しています")

    if len(rules) > limit:
        raise ValueError(f"ルール数が上限を超えています: {len(rules)} > {limit}")

    # 最低限これだけは無いとおかしい、という下限。
    # EasyList の取得に失敗して空に近い出力になるのを検出する。
    if len(rules) < min_rules:
        raise ValueError(f"ルール数が少なすぎます: {len(rules)} 件")

    for i, r in enumerate(rules):
        if "trigger" not in r or "action" not in r:
            raise ValueError(f"ルール {i} の形式が不正です")
        if "url-filter" not in r["trigger"]:
            raise ValueError(f"ルール {i} に url-filter がありません")
        # 正規表現として成立するか確認
        try:
            re.compile(r["trigger"]["url-filter"])
        except re.error as e:
            raise ValueError(f"ルール {i} の url-filter が不正です: {e}")

    # 例外ルールは必ず block ルールより後ろにある必要がある。
    # Safari の ignore-previous-rules は「それより前のルール」しか打ち消せないため。
    seen_exception = False
    for r in rules:
        if r["action"]["type"] == "ignore-previous-rules":
            seen_exception = True
        elif seen_exception:
            raise ValueError("block ルールが例外ルールより後ろにあります")


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="EasyList を Safari コンテンツブロッカー JSON に変換する"
    )
    parser.add_argument("--url", default=EASYLIST_URL,
                        help="取得元のフィルタリスト URL")
    parser.add_argument("--input", default=None,
                        help="URL の代わりにローカルファイルを読む（テスト用）")
    parser.add_argument("--output", default="docs/blocklist.json",
                        help="出力先の JSON ファイル")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"ルール数の上限（既定: {DEFAULT_LIMIT}）")
    parser.add_argument("--min-rules", type=int, default=1000,
                        help="この件数を下回ったら失敗扱いにする（取得失敗の検出用）")
    args = parser.parse_args()

    # 1. フィルタリストを取得
    if args.input:
        with open(args.input, encoding="utf-8", errors="replace") as f:
            text = f.read()
        print(f"読み込み: {args.input}")
    else:
        print(f"取得中: {args.url}")
        req = urllib.request.Request(
            args.url,
            headers={"User-Agent": "kantan-setup-filters/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as res:
            text = res.read().decode("utf-8", errors="replace")

    lines = text.splitlines()
    print(f"読み込んだ行数: {len(lines):,}")

    # 2. 変換
    blocks = []      # (priority, rule)
    exceptions = []
    skipped = 0

    for line in lines:
        converted = convert_line(line)
        if converted is None:
            skipped += 1
            continue
        rule, is_exception, priority = converted
        # 正規表現として成立しないものはここで落とす
        try:
            re.compile(rule["trigger"]["url-filter"])
        except re.error:
            skipped += 1
            continue
        if is_exception:
            exceptions.append(rule)
        else:
            blocks.append((priority, rule))

    print(f"変換できたブロックルール: {len(blocks):,}")
    print(f"変換できた例外ルール:     {len(exceptions):,}")
    print(f"変換できずに捨てた行:     {skipped:,}")

    # 3. 上限に収める
    # 例外ルールは誤ブロック防止のため全部残し、ブロックルール側を削る。
    room = args.limit - len(exceptions)
    if room < 0:
        raise SystemExit("例外ルールだけで上限を超えています。limit を見直してください")

    # 優先度の高い順（ドメインアンカー優先）に並べ替えてから切る
    blocks.sort(key=lambda x: -x[0])
    kept = [r for _, r in blocks[:room]]
    dropped = len(blocks) - len(kept)
    if dropped > 0:
        print(f"上限に収めるため {dropped:,} 件のブロックルールを削除しました")

    # 例外ルールは必ず最後に置く（ignore-previous-rules の仕様）
    rules = kept + exceptions

    # 4. 検証してから書き出す
    validate(rules, args.limit, args.min_rules)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, separators=(",", ":"))

    import os
    size_mb = os.path.getsize(args.output) / 1024 / 1024
    print(f"書き出し完了: {args.output}")
    print(f"ルール数: {len(rules):,} 件 / サイズ: {size_mb:.2f} MB")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
