"""
言い訳裁判 - ビュー

画面一覧:
  /                    ログイン画面（名前入力 + ホスト/参加者選択）
  /enter               ↑のフォーム送信先。名前と役割をセッションに保存する
  /host/setup          ホスト側: 開廷準備画面（裁判名・被告人・参加者・タイマー設定）
  /host/setup/start    ↑のフォーム送信先。ガチャを回して裁判を開始する
  /join/waiting        参加者側: 待機画面
  /role-reveal         開廷時: 役割発表画面
  /trial               法廷配信画面（ホスト/参加者共通の1画面）

まだ実装していない（次のフェーズ）:
  - フェーズの自動切り替え・全員同期のカウントダウン
  - 本物の同時接続数としての視聴者数
  - ラスト30秒だけ投票を開放する仕組み
  - 罰ゲーム演出（カメラ撮影 → コラ画像生成）
"""

from django.shortcuts import render, redirect

from trial.state import (
    lobby_state,
    DEFAULT_PHASES,
    ROLE_META,
    format_mmss,
    parse_mmss_to_seconds,
    start_trial,
    reset_for_new_round,
)
from trial.sockets import notify_participants_updated, notify_trial_started


def index(request):
    return render(request, "login.html")


def enter(request):
    """名前入力 + ホスト/参加者の選択を受け取る共通の入り口"""
    if request.method != "POST":
        return redirect("index")

    username = (request.POST.get("username") or "").strip()
    role = request.POST.get("role")

    if not username:
        return redirect("index")

    if role == "host":
        request.session["username"] = username
        request.session["is_host"] = True
        # ホストが「ホストとして開廷する」を押すたびに、新しい部屋(コード)として作り直す
        reset_for_new_round()
        return redirect("host_setup")

    # 参加者として参加する場合は、招待コードの一致を確認する
    entered_code = (request.POST.get("access_code") or "").strip()
    if not entered_code:
        return render(
            request,
            "login.html",
            {"error": "コード入力しないと参加できません", "username": username},
        )
    if not lobby_state["access_code"] or entered_code != lobby_state["access_code"]:
        return render(
            request,
            "login.html",
            {"error": "コードが違います。ホストに確認してください", "username": username},
        )

    request.session["username"] = username
    request.session["is_host"] = False
    if username not in lobby_state["participants"]:
        lobby_state["participants"].append(username)
        # 既にホスト側の開廷準備画面が開かれていれば、そちらへリアルタイムで反映
        notify_participants_updated()
    return redirect("join_waiting")


def host_setup(request):
    phases = []
    for ph in DEFAULT_PHASES:
        duration = lobby_state["phase_durations"][ph["key"]]
        phases.append({**ph, "duration_display": format_mmss(duration)})

    return render(
        request,
        "host_setup.html",
        {
            "participants": lobby_state["participants"],
            "phases": phases,
            "access_code": lobby_state["access_code"],
        },
    )


def host_setup_start(request):
    if request.method != "POST":
        return redirect("host_setup")

    case_name = (request.POST.get("case_name") or "裁判").strip()
    defendant = request.POST.get("defendant")

    if not defendant or defendant not in lobby_state["participants"]:
        return redirect("host_setup")

    durations = {}
    for ph in DEFAULT_PHASES:
        raw = request.POST.get(f"phase_{ph['key']}", "")
        durations[ph["key"]] = parse_mmss_to_seconds(raw, fallback=lobby_state["phase_durations"][ph["key"]])
    lobby_state["phase_durations"] = durations

    start_trial(case_name, defendant)
    notify_trial_started()
    return redirect("trial")


def join_waiting(request):
    if "username" not in request.session:
        return redirect("index")
    return render(
        request,
        "waiting_room.html",
        {
            "my_name": request.session["username"],
            "participants": lobby_state["participants"],
        },
    )


def role_reveal(request):
    username = request.session.get("username")
    role_key = lobby_state["role_map"].get(username)
    if not username or not role_key:
        return redirect("index")
    role = {"key": role_key, **ROLE_META[role_key]}
    return render(request, "role_reveal.html", {"role": role})


def trial(request):
    state = lobby_state
    active_key = "defendant"
    phases = []
    for ph in DEFAULT_PHASES:
        duration = state["phase_durations"].get(ph["key"], 90)
        phases.append(
            {
                "label": ph["label"],
                "icon": ph["icon"],
                "key": ph["key"],
                "time": format_mmss(duration),
                "progress": 0,
                "active": ph["key"] == active_key,
            }
        )

    return render(
        request,
        "trial.html",
        {
            "case_name": state["case_name"] or "裁判",
            "defendant_name": state["defendant"] or "未定",
            "phases": phases,
            "gauges": {"nervousness": 50, "suspicion": 50},
            "excuse_text": "ここに被告人の発言が表示されます",
            "prosecutor": {"name": state["prosecutor"] or "未定"},
            "defense": {"name": state["defense"] or "未定"},
            "objection_count": state["objection_count"],
            "comments": state["comments"],
            "verdict": {"guilty": 50, "innocent": 50},
            "viewer_count": len(state["participants"]),
            "my_name": request.session.get("username", "匿名"),
        },
    )
