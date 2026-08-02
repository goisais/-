"""
言い訳裁判 - Flaskアプリのエントリーポイント

画面一覧:
  /                 ログイン画面（名前入力 + ホスト/参加者選択）
  /host/setup       ホスト側: 開廷準備画面（裁判名・被告人・参加者・タイマー設定）
  /join/waiting      参加者側: 待機画面
  /role-reveal       開廷時: 役割発表画面
  /trial             法廷配信画面（ホスト/参加者共通の1画面）

このファイルはまず画面遷移が確認できるダミーデータでの実装です。
実際のガチャ抽選・タイマー同期・ライブ映像・コメントのリアルタイム配信は
別途 WebSocket（Flask-SocketIO など）や配信基盤と組み合わせて実装してください。
"""

from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def login():
    """名前入力 + ホスト/参加者を選ぶログイン画面"""
    return render_template("login.html")


@app.route("/host/setup")
def host_setup():
    """ホスト側: 裁判名・被告人・参加者・フェーズ時間を設定する画面"""
    # TODO: 実際は参加者リストをDB/セッションから取得する
    participants = [
        {"name": "もちゅ", "initial": "も", "role": "defendant"},
        {"name": "なつ", "initial": "な", "role": None},
        {"name": "しんちゃん", "initial": "し", "role": None},
    ]
    others = [
        {"name": "じゅーはる", "initial": "じ"},
        {"name": "だいきんぐ", "initial": "だ"},
    ]
    phases = [
        {"key": "defendant", "label": "被告人陳述", "icon": "ti-microphone", "duration": "2:00"},
        {"key": "prosecutor", "label": "検察質問", "icon": "ti-shield-half-filled", "duration": "1:30"},
        {"key": "defense", "label": "弁護士弁護", "icon": "ti-scale", "duration": "1:30"},
    ]
    return render_template(
        "host_setup.html",
        participants=participants,
        others=others,
        phases=phases,
    )


@app.route("/join/waiting")
def waiting_room():
    """参加者側: ホストが開廷するまでの待機画面"""
    case_name = "電車寝坊事件"
    joined = [
        {"name": "もちゅ", "initial": "も", "is_you": False},
        {"name": "なつ", "initial": "な", "is_you": False},
        {"name": "しんちゃん", "initial": "し", "is_you": False},
        {"name": "じゅーはる", "initial": "じ", "is_you": False},
        {"name": "だいきんぐ", "initial": "だ", "is_you": True},
    ]
    return render_template(
        "waiting_room.html",
        case_name=case_name,
        joined=joined,
        joined_count=len(joined),
        capacity=6,
    )


@app.route("/role-reveal")
def role_reveal():
    """開廷と同時にガチャで決まった自分の役割を見せる画面"""
    # TODO: 実際はサーバー側のガチャ抽選結果をここに渡す
    my_role = {
        "key": "prosecutor",
        "label": "検察官",
        "icon": "ti-shield-half-filled",
        "description": "被告人に鋭い質問を投げかけよう",
        "accent": "danger",
    }
    return render_template("role_reveal.html", role=my_role)


@app.route("/trial")
def trial():
    """法廷配信画面。ホストと視聴者で共通のレイアウト"""
    case_name = "電車寝坊事件"
    phases = [
        {"label": "被告人陳述", "icon": "ti-microphone", "time": "01:24", "progress": 42, "active": True},
        {"label": "検察質問", "icon": "ti-shield-half-filled", "time": "1:30", "progress": 0, "active": False},
        {"label": "弁護士弁護", "icon": "ti-scale", "time": "1:30", "progress": 0, "active": False},
    ]
    gauges = {"nervousness": 73, "suspicion": 58}
    excuse_text = "電車が来たと思ったら反対方向でした"
    prosecutor = {"name": "なつ", "initial": "な"}
    defense = {"name": "しんちゃん", "initial": "し"}
    objection_count = 128
    comments = [
        {"name": "もちゅ", "text": "反対方向はさすがに草"},
        {"name": "じゅーはる", "text": "証拠の写真出して"},
        {"name": "だいきんぐ", "text": "それ先週も言ってた"},
    ]
    verdict = {"guilty": 64, "innocent": 36}
    return render_template(
        "trial.html",
        case_name=case_name,
        phases=phases,
        gauges=gauges,
        excuse_text=excuse_text,
        prosecutor=prosecutor,
        defense=defense,
        objection_count=objection_count,
        comments=comments,
        verdict=verdict,
        viewer_count=482,
    )


if __name__ == "__main__":
    app.run(debug=True)
