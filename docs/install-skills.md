# skillsの導入（任意）

確認日：2026-10-22。通常のChatGPTで使い始める場合は、[共通指示](../prompts/secretary-instructions.md)と[場面別プロンプト](../prompts/)だけで構いません。

skillは、AIに繰り返し使わせる手順をまとめたものです。このリポジトリには、実行コードを含まない4つのSKILL.mdがあります。

| skill | 使う場面 |
| --- | --- |
| `task-triage` | 今日の優先順位、期限の競合、未担当の仕事 |
| `inbox-to-actions` | メールから依頼・質問・期限を取り出す |
| `japanese-business-writing` | 自然な日本語、敬語、返信の確認 |
| `handoff-check` | 不在前の引き継ぎ、引受確認 |

単独skillの対応環境はChatGPTデスクトップアプリ、Codex CLI、IDE拡張です。Webやモバイルにもインストールして配布するには、別途プラグインとしてパッケージ化する方法があります。本リポジトリは初版では単独skillsを提供しています。[公式のBuild skills](https://learn.chatgpt.com/docs/build-skills)

## 方法A：Codexに導入を頼む

対応するCodex環境で、次を入力します。これはターミナルのコマンドではなく、Codexへの依頼文です。

```text
$skill-installer
https://github.com/amu815/ai-secretary-kit の次の4つを、ローカルのskillsとして導入してください。
skills/task-triage
skills/inbox-to-actions
skills/japanese-business-writing
skills/handoff-check
同名の既存skillがある場合は、上書きする前に差分を示してください。
```

内容を確認してから導入します。見つからない場合はCodexを再起動し、スキル一覧で名前を確認してください。他のリポジトリからの導入は公式にも案内されています。[公式の導入方法](https://learn.chatgpt.com/docs/build-skills#install-curated-skills-for-local-use)

## 方法B：フォルダをコピーする

GitHubの **Code → Download ZIP** でダウンロードして展開します。`skills/` の中にある4つのフォルダを、使いたいローカルプロジェクトの `.agents/skills/` にコピーします。同名フォルダがある場合は内容を比較してから更新してください。

```text
使いたいプロジェクト/
└── .agents/
    └── skills/
        ├── task-triage/SKILL.md
        ├── inbox-to-actions/SKILL.md
        ├── japanese-business-writing/SKILL.md
        └── handoff-check/SKILL.md
```

全プロジェクトで使う場合の探索先は `~/.agents/skills/` です。隠しフォルダを扱う操作に不慣れなら方法Aを使います。現行の探索先は[公式のLocal skills](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)で確認できます。

## 使って確かめる

Codexでは `$`、ChatGPTの対応環境では `@` からskillを選びます。たとえばCodexで次のように依頼します。

```text
$task-triage
examples/first-day.md の架空の予定について、今日の順番と確認事項を提案してください。
```

そのファイルを開けない環境では本文を貼り付けます。[受入シナリオ](../evals/scenarios.md)で期限や未確認事項の扱いも試してください。skillを導入しても、メールの自動送受信や予定表との連携は追加されません。
