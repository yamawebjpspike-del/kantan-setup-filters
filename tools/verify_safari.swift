import Foundation
import WebKit

// 作ったルールを Safari が本当に読み込めるか、Mac の上で確かめる道具。
//
// ■ なぜ必要か
//
// Safari の url-filter が解するのは正規表現のごく一部だけで、
// 解せない書き方が **1 行でも** 混ざるとルールセット全体が読み込まれない。
// 一部が効かなくなるのではなく、全部が効かなくなる。
// しかも iPhone 側は黙って何もしないだけなので、気づけない。
//
// 実際、上限を 3 万から 6 万に上げたときに
// `\w{30,}` と `(club|bid|xyz|…)` の 2 種類が引っかかった（2026-08-19）。
// 3 万件のときは、たまたまその行が入っていなかっただけだった。
//
// WKContentRuleListStore は Safari が使うのと同じ組み立て機なので、
// ここを通れば実機でも読み込める。
//
// ■ 使い方
//
//     xcrun --sdk macosx swiftc -O tools/verify_safari.swift -o /tmp/verify
//     /tmp/verify docs/blocklist.json
//
// ■ GitHub Actions では動かない
//
// WebKit は macOS にしか無いため、週次の自動変換では確かめられない。
// **変換のしかたを変えたときは、必ず手元でこれを通してから push すること。**
let path = CommandLine.arguments[1]
let json = try! String(contentsOfFile: path, encoding: .utf8)

let start = Date()
var done = false
var failure: String?

WKContentRuleListStore.default().compileContentRuleList(
    forIdentifier: "check-\(UUID().uuidString)",
    encodedContentRuleList: json
) { list, error in
    if let error { failure = String(describing: error) }
    else if list == nil { failure = "リストが nil で返ってきた" }
    done = true
}

while !done && Date().timeIntervalSince(start) < 300 {
    RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.1))
}

if !done { print("TIMEOUT"); exit(2) }
if let failure { print("FAILED: \(failure)"); exit(1) }
print(String(format: "OK  %.1f 秒", Date().timeIntervalSince(start)))
