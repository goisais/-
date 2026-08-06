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

フェーズの進行(自動切り替え・カウントダウン・ゲージ・投票)はtrial/sockets.pyの
サーバー側タイマーが管理していて、Socket.IO経由で全員に同じ状態を配信している。

まだ実装していない（次のフェーズ）:
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
    get_or_create_profile,
    get_points,
    start_trial_game_mode,
    pick_random_case_template,
    pick_random_defendant,
    DIFFICULTY_LABELS,
    GAME_MODE_PHASE_SECONDS,
)
from trial.sockets import notify_participants_updated, notify_trial_started, start_phase_timer


def index(request):
    return render(request, "login.html")


def enter(request):
    """名前入力 + ホスト/参加者の選択を受け取る共通の入り口"""
    if request.method != "POST":
        return redirect("index")

    username = (request.POST.get("username") or "").strip()
    role = request.POST.get("role")
    player_token = (request.POST.get("player_token") or "").strip()

    if not username:
        return redirect("index")

    # 同じ名前を禁止
    if username in lobby_state["participants"]:
        return render(
            request,
            "login.html",
            {
                "error": "その名前は既に使用されています。",
                "username": username,
            },
        )

    # メール登録などの手間をかけずに、ブラウザ紐付けの匿名トークンでポイントを
    # 持ち越せるようにする。トークンが無い(古いブラウザ等)場合は毎回0ポイント扱い
    get_or_create_profile(player_token, username)
    request.session["player_token"] = player_token

    if role == "host":
        # スプラトゥーンのレギュラー/ガチマッチみたいに、開廷する前に形式を選ぶ。
        # 自由形式(classic)=今まで通り、ゲーム形式(game)=お題抽選+ベットの新モード
        game_mode = (request.POST.get("mode") == "game")

        request.session["username"] = username
        request.session["is_host"] = True
        # ホストが「ホストとして開廷する」を押すたびに、新しい部屋(コード)として作り直す
        reset_for_new_round()
        lobby_state["host_name"] = username
        lobby_state["mode"] = "game" if game_mode else "classic"
        # ホスト自身も参加者の1人（被告人になれるし、待機画面の一覧にも出る）
        if username not in lobby_state["participants"]:
            lobby_state["participants"].append(username)
        lobby_state["player_tokens"][username] = player_token
        return redirect("host_setup_game" if game_mode else "host_setup")

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
    lobby_state["player_tokens"][username] = player_token
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
    start_phase_timer()
    return redirect("trial")


def host_setup_game(request):
    """ゲーム形式: ホストは被告人もお題も選ばない。参加者一覧を確認して
    「抽選して開廷する」を押すだけ(被告人・お題ともにランダム抽選)"""
    return render(
        request,
        "host_setup_game.html",
        {
            "participants": lobby_state["participants"],
            "access_code": lobby_state["access_code"],
        },
    )


def host_setup_game_start(request):
    if request.method != "POST":
        return redirect("host_setup_game")

    defendant = pick_random_defendant()
    if not defendant:
        return redirect("host_setup_game")

    case_template = pick_random_case_template()
    start_trial_game_mode(defendant, case_template)
    notify_trial_started()
    start_phase_timer()
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
            "my_points": get_points(request.session.get("player_token")),
        },
    )


def role_reveal(request):
    username = request.session.get("username")
    role_key = lobby_state["role_map"].get(username)
    if not username or not role_key:
        return redirect("index")
    role = {"key": role_key, **ROLE_META[role_key]}
    game_mode = lobby_state.get("mode") == "game"
    case_template = lobby_state.get("case_template") if game_mode else None
    context = {"role": role, "my_name": username, "game_mode": game_mode}
    if case_template:
        context["case_template"] = case_template
        context["difficulty_label"] = DIFFICULTY_LABELS.get(case_template.get("difficulty"), "")
    return render(request, "role_reveal.html", context)


def trial(request):
    state = lobby_state
    phases = []
    for i, ph in enumerate(DEFAULT_PHASES):
        duration = state["phase_durations"].get(ph["key"], 90)
        remaining = state["phase_remaining"] if i == state["phase_index"] else duration
        phases.append(
            {
                "label": ph["label"],
                "icon": ph["icon"],
                "key": ph["key"],
                "time": format_mmss(remaining),
                "duration": duration,
                "remaining_seconds": remaining,
                "active": i == state["phase_index"],
            }
        )

    my_name = request.session.get("username", "匿名")
    my_role = state["role_map"].get(my_name, "gallery")
    is_host = bool(request.session.get("is_host"))

    guilty = state["votes"]["guilty"]
    innocent = state["votes"]["innocent"]
    total_votes = guilty + innocent

    game_mode = state.get("mode") == "game"
    already_bet = my_name in state["bets"] if game_mode else False
    is_lawyer = my_role in ("prosecutor", "defense")
    objection_card_used = state.get("objection_card_used", {}).get(my_role, False) if is_lawyer else False

    return render(
        request,
        "trial.html",
        {
            "case_name": state["case_name"] or "裁判",
            "defendant_name": state["defendant"] or "未定",
            "phases": phases,
            "phase_index": state["phase_index"],
            "gauges": state["gauges"],
            "prosecutor": {"name": state["prosecutor"] or "未定"},
            "defense": {"name": state["defense"] or "未定"},
            "objection_count": state["objection_count"],
            "comments": state["comments"],
            "voting_open": state["voting_open"],
            "votes": state["votes"],
            "guilty_pct": round(guilty / total_votes * 100) if total_votes else 50,
            "innocent_pct": round(innocent / total_votes * 100) if total_votes else 50,
            "viewer_count": len(state["participants"]),
            "my_name": my_name,
            "my_role": my_role,
            "is_host": is_host,
            "trial_round": state["trial_round"],
            "judge_name": state["judge_name"],
            "game_mode": game_mode,
            "case_template": state.get("case_template"),
            "wallet_balance": state["wallets"].get(my_name),
            "bet_counts": state["bet_counts"],
            "already_bet": already_bet,
            "is_lawyer": is_lawyer,
            "objection_card_used": objection_card_used,
        },
    )


def verdict(request):
    """判決結果画面。有罪/無罪と（有罪なら）ランダムな刑罰、被告人の顔切り抜き画像を表示する。
    罰ゲーム用のコラ画像テンプレートは trial/static/trial/img/punishment_template.png に
    置くと自動で背景に使われる（無ければ顔写真だけ表示される）。"""
    state = lobby_state
    result = state["verdict_result"] or {"outcome": "innocent", "sentence": None, "tier": "normal"}
    my_name = request.session.get("username", "")
    return render(
        request,
        "verdict.html",
        {
            "case_name": state["case_name"] or "裁判",
            "defendant_name": state["defendant"] or "未定",
            "outcome": result["outcome"],
            "sentence": result["sentence"],
            "tier": result.get("tier", "normal"),
            "face_capture": state["defendant_face_capture"],
            "game_mode": state.get("mode") == "game",
            "ranking": state.get("ranking"),
            "my_name": my_name,
        },
    )
