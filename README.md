# 放課後Connect

高校生向けの匿名掲示板です。勉強・部活・進路・雑談の投稿、キーワード検索、コメント、共感、解決済み、画像添付に対応します。

## Mac で起動する

Python 3.13 を使用します。プロジェクトフォルダーをターミナルで開き、次を実行します。

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app:create_app run
```

ブラウザーで [ローカル版](http://127.0.0.1:5000/) を開きます。Azure の接続設定が空なら `instance/board.sqlite3` に投稿と画像が保存されます。ローカル起動ごとに生成するセッションキーを固定したい場合は、`FLASK_SECRET_KEY` をローカルの環境変数に設定します。

```sh
python -m unittest discover -s tests -v
```

## Azure に公開する

1. このプロジェクト専用のリソースグループ、Storage アカウント、Linux App Service を作成します。ストレージにテーブル `HoukagoConnectBoard` と非公開の Blob コンテナー `houkagoconnect-images` を作ります。
2. App Service の環境変数に `AZURE_STORAGE_CONNECTION_STRING` と `FLASK_SECRET_KEY` を設定します。セッションキーは `python3 -c 'import secrets; print(secrets.token_hex(32))'` などで生成します。 `SCM_DO_BUILD_DURING_DEPLOYMENT=true` も設定します。
3. Linux の Python 3.13 を選び、起動コマンドを `gunicorn --bind 0.0.0.0:8000 --workers 2 'app:create_app()'` に設定し、HTTPS のみを有効にします。
4. GitHub に公開リポジトリを作り、`main` をプッシュします。Azure 側は GitHub の OIDC フェデレーションを `repo:所有者/HoukagoConnect:ref:refs/heads/main` に設定し、資格情報に対象 App Service の Website Contributor ロールを付与します。GitHub Actions に変数 `AZURE_WEBAPP_NAME` とシークレット `AZURE_CLIENT_ID`、`AZURE_TENANT_ID`、`AZURE_SUBSCRIPTION_ID` を設定します。
5. Actions の **Test and deploy** を実行し、公開トップページと `/health` を確認します。さらに画像付き投稿・コメント・共感・解決済みを公開サイトで確認し、提出する URL を `requirements.md` に記入します。

[Azure の Python アプリ設定](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python) · [GitHub Actions から App Service にデプロイする方法](https://learn.microsoft.com/azure/app-service/deploy-github-actions)

## 保存と操作

投稿、コメント、共感、解決済みを Azure Table の区画ごとに保存します。共感はセッション ID を行キーとして重複を防ぎます。投稿者は同じブラウザーのセッションから解決済みを設定できます。画像は 5 MB まで受け付け、JPEG に再エンコードして位置情報などのメタデータを除去します。画像は非公開コンテナーからアプリ経由で表示します。入力本文は HTML として描画せず、フォームには CSRF 対策を適用します。

匿名の判定はブラウザーのセッションに基づきます。端末変更、Cookie 削除、セッション期限切れ後は、以前の投稿者としての操作はできません。検索は小規模な課題掲示板を想定し、投稿を読み込んで照合します。
