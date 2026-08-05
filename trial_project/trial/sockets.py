"""
言い訳裁判 - Socket.IOサーバー(python-socketio)

クライアント側(各テンプレートの<script>内)は普通のSocket.IOクライアント
(`const socket = io();`)のままで、サーバー側だけこのファイルで受け止める。
DjangoのWSGIアプリと同じポートで動くように、wsgi.pyでラップしている。

フェーズタイマーはサーバー側のバックグラウンドスレッドが1秒ごとに進行させ、
全員の画面に同じ残り時間・動揺度/あやしさ度を配信することで同期させている。
"""

import threading
import time

import socketio

from trial.state import (
    lobby_state,
    DEFAULT_PHASES,
    current_phase_key,
    random_walk,
    determine_verdict,
    advance_to_next_round,
    select_judge,
    judge_decide_verdict,
    place_bet as _place_bet,
)

LOBBY_ROOM = "lobby"
TRIAL_ROOM = "trial"

# 顔切り抜き画像(data URL)をSocket.IO経由で送るので、デフォルトの受信上限だと
# 弾かれることがある。少し余裕を持たせておく(だいたい数百KB〜1MB程度を想定)。
sio = socketio.Server(async_mode="threading", cors_allowed_origins="*", max_http_buffer_size=5_000_000)

# sid -> {"name": str, "role": str} 法廷配信画面に今いる人（WebRTCの接続相手探しに使う）
trial_peers = {}

_timer_thread = None
_timer_lock = threading.Lock()
_timer_generation = 0  # 新しい裁判が始まるたびに増やし、古いスレッドを止める目印にする


@sio.event
def connect(sid, environ):
    pass


@sio.event
def disconnect(sid):
    if sid in trial_peers:
        peer = trial_peers.pop(sid)
        sio.emit("trial_peer_left", {"sid": sid, "name": peer["name"], "role": peer["role"]}, room=TRIAL_ROOM)


@sio.event
def join_lobby(sid):
    """開廷準備画面・待機画面が、参加者リストの更新を受け取れるようにする"""
    sio.enter_room(sid, LOBBY_ROOM)
    sio.emit("participants_updated", {"participants": lobby_state["participants"]}, to=sid)


@sio.event
def join_trial(sid, data=None):
    sio.enter_room(sid, TRIAL_ROOM)
    name = (data or {}).get("name") or "匿名"
    role = lobby_state["role_map"].get(name, "gallery")
    trial_peers[sid] = {"name": name, "role": role}

    # 今いる全員を新しく入ってきた人に伝える（接続相手を見つけるため）
    others = [{"sid": s, **p} for s, p in trial_peers.items() if s != sid]
    sio.emit("trial_peer_list", {"peers": others}, to=sid)
    # 新しく入ってきた人を、既にいる全員に伝える
    sio.emit("trial_peer_joined", {"sid": sid, "name": name, "role": role}, room=TRIAL_ROOM, skip_sid=sid)

    # 現在のフェーズ・ゲージ・判決の状態を追いつかせる(ウォレット残高は本人の分だけ)
    sio.emit(
        "state_sync",
        {
            "phase_index": lobby_state["phase_index"],
            "phase_remaining": lobby_state["phase_remaining"],
            "gauges": lobby_state["gauges"],
            "voting_open": lobby_state["voting_open"],
            "votes": lobby_state["votes"],
            "wallet_balance": lobby_state["wallets"].get(name),
            "already_bet": name in lobby_state["bets"],
        },
        to=sid,
    )


@sio.event
def comment_send(sid, data):
    text = (data or {}).get("text", "").strip()
    if not text:
        return
    name = (data or {}).get("name") or "匿名"
    comment = {"name": name, "text": text}
    lobby_state["comments"].append(comment)
    sio.emit("comment_new", comment, room=TRIAL_ROOM)


@sio.event
def objection(sid):
    lobby_state["objection_count"] += 1
    sio.emit("objection_update", {"count": lobby_state["objection_count"]}, room=TRIAL_ROOM)


@sio.event
def cast_vote(sid, data):
    """判決投票。被告人・検察官・弁護人は「自分が勝つ方」に入れられてしまうので
    投票できない(=傍聴席だけが投票できる)。さらに、有罪/無罪に賭けた人は
    その賭けが的中するように投票してしまえるので、賭けた人も投票できないようにする"""
    name = (data or {}).get("name") or "匿名"
    choice = (data or {}).get("choice")
    if choice not in ("guilty", "innocent"):
        return
    if not lobby_state["voting_open"]:
        return
    if lobby_state["role_map"].get(name) != "gallery":
        return  # 傍聴席以外(被告人・検察官・弁護人)は自分の裁判に投票できない
    if name in lobby_state["bets"]:
        return  # 賭けた人は投票できない(投票結果を自分の得のために操作できてしまうため)
    if name in lobby_state["voters"]:
        return
    lobby_state["voters"].append(name)
    lobby_state["votes"][choice] += 1
    sio.emit("verdict_update", {"votes": lobby_state["votes"]}, room=TRIAL_ROOM)


@sio.event
def place_bet(sid, data):
    """傍聴席が、有罪/無罪のどちらに賭けるか(掛け金つき)を決める。投票開始前まで。
    ここで賭けた人はcast_vote側で投票できなくなる(利益相反防止)"""
    name = (data or {}).get("name") or ""
    choice = (data or {}).get("choice")
    amount = (data or {}).get("amount")
    if not name:
        return
    ok, result = _place_bet(name, choice, amount)
    if ok:
        sio.emit(
            "bet_placed",
            {"name": name, "choice": choice, "amount": amount, "balance": result},
            room=TRIAL_ROOM,
        )
    else:
        sio.emit("bet_rejected", {"reason": result}, to=sid)


@sio.event
def skip_phase(sid, data=None):
    """自分の担当フェーズ中に、話し終わった本人がタイマーを早送りできるようにする。
    (被告人は被告人陳述だけ、検察官は検察質問だけ、弁護人は弁護士弁護だけスキップ可能)"""
    name = (data or {}).get("name") or ""
    if not lobby_state["trial_started"]:
        return
    idx = lobby_state["phase_index"]
    if not (0 <= idx < len(DEFAULT_PHASES)):
        return
    expected_role = DEFAULT_PHASES[idx]["key"]
    if lobby_state["role_map"].get(name) != expected_role:
        return  # 本人（そのフェーズの担当者）以外からは無視する
    _advance_phase()


def _is_host(name):
    return bool(name) and name == lobby_state.get("host_name")


@sio.event
def finalize_verdict(sid, data=None):
    """ホストが「判決を確定する」を押したときに呼ばれる。投票を締め切り、
    有罪/無罪と（有罪なら）刑罰をランダムに決めて、全員を判決ページへ誘導する。
    同数(引き分け)だった場合は、3審目までなら次の審に進めるようにし、
    3審目でも同数なら被告人以外からランダムに裁判長を選んで強制的に判決を下してもらう。"""
    name = (data or {}).get("name") or ""
    if not _is_host(name):
        return
    if not lobby_state["trial_started"]:
        return
    if lobby_state["verdict_result"] is not None:
        return  # 二重確定防止

    result = determine_verdict()
    if result is not None:
        sio.emit("verdict_finalized", result, room=TRIAL_ROOM)
        return

    # 同数だった場合
    round_num = lobby_state["trial_round"]
    if round_num < 3:
        sio.emit(
            "verdict_tied",
            {"round": round_num, "next_round": round_num + 1, "votes": lobby_state["votes"]},
            room=TRIAL_ROOM,
        )
    else:
        judge = select_judge()
        sio.emit("judge_selected", {"judge_name": judge, "votes": lobby_state["votes"]}, room=TRIAL_ROOM)


@sio.event
def start_next_round(sid, data=None):
    """同数だったときに、ホストが次の審(2審/3審)に進める。検察官・弁護人を再抽選し、
    フェーズを最初からやり直す(2審=1分固定, 3審=30秒固定)。"""
    name = (data or {}).get("name") or ""
    if not _is_host(name):
        return
    if not lobby_state["trial_started"]:
        return
    info = advance_to_next_round()
    sio.emit("round_started", info, room=TRIAL_ROOM)
    start_phase_timer()


@sio.event
def judge_decide(sid, data=None):
    """3審でも同数だったとき、裁判長役に選ばれた本人だけが判決を確定できる。"""
    name = (data or {}).get("name") or ""
    choice = (data or {}).get("choice")
    if not name or name != lobby_state.get("judge_name"):
        return  # 裁判長本人以外は無視
    if choice not in ("guilty", "innocent"):
        return
    if lobby_state["verdict_result"] is not None:
        return
    result = judge_decide_verdict(choice)
    sio.emit("verdict_finalized", result, room=TRIAL_ROOM)


@sio.event
def leave_trial(sid, data=None):
    """傍聴席(役割なし)の人だけが退出できる。被告人・検察官・弁護人・ホストは
    裁判が終わるまで抜けられない。"""
    name = (data or {}).get("name") or ""
    if not name or _is_host(name):
        return
    if lobby_state["role_map"].get(name) != "gallery":
        return
    if name in lobby_state["participants"]:
        lobby_state["participants"].remove(name)
    lobby_state["role_map"].pop(name, None)
    if sid in trial_peers:
        peer = trial_peers.pop(sid)
        sio.emit("trial_peer_left", {"sid": sid, "name": peer["name"], "role": peer["role"]}, room=TRIAL_ROOM)
    sio.emit(
        "participant_left",
        {"name": name, "viewer_count": len(lobby_state["participants"])},
        room=TRIAL_ROOM,
    )


@sio.event
def face_capture(sid, data):
    """被告人陳述フェーズ終了1秒前に、被告人のブラウザ側で顔検出→切り抜きした
    画像(data URL)を受け取って保存する。罰ゲーム(コラ画像合成)で使う。"""
    image_data_url = (data or {}).get("image")
    if not image_data_url:
        return
    lobby_state["defendant_face_capture"] = image_data_url


# ---------- WebRTCのシグナリング中継 ----------
# サーバーはSDP/ICEの中身を理解する必要はなく、指定されたsidにそのまま転送するだけ。

@sio.event
def webrtc_offer(sid, data):
    target = (data or {}).get("to")
    if not target:
        return
    sio.emit("webrtc_offer", {"from": sid, "sdp": data.get("sdp")}, to=target)


@sio.event
def webrtc_answer(sid, data):
    target = (data or {}).get("to")
    if not target:
        return
    sio.emit("webrtc_answer", {"from": sid, "sdp": data.get("sdp")}, to=target)


@sio.event
def webrtc_ice_candidate(sid, data):
    target = (data or {}).get("to")
    if not target:
        return
    sio.emit("webrtc_ice_candidate", {"from": sid, "candidate": data.get("candidate")}, to=target)


def notify_participants_updated():
    sio.emit("participants_updated", {"participants": lobby_state["participants"]}, room=LOBBY_ROOM)


def notify_trial_started():
    sio.emit("trial_started", {}, room=LOBBY_ROOM)


# ---------- フェーズタイマー(サーバー主導のカウントダウン) ----------

def start_phase_timer():
    """開廷する が押されたときに呼び出す。前の裁判のタイマーは世代番号で自然に止まる。"""
    global _timer_thread, _timer_generation
    with _timer_lock:
        _timer_generation += 1
        my_generation = _timer_generation
        _timer_thread = threading.Thread(target=_run_phase_timer, args=(my_generation,), daemon=True)
        _timer_thread.start()


def _run_phase_timer(my_generation):
    while True:
        time.sleep(1)
        if my_generation != _timer_generation:
            return  # 新しい裁判が始まっている＝このスレッドはお役御免
        if not lobby_state["trial_started"]:
            return
        if not (0 <= lobby_state["phase_index"] < len(DEFAULT_PHASES)):
            return

        lobby_state["phase_remaining"] -= 1

        g = lobby_state["gauges"]
        g["nervousness"] = random_walk(g["nervousness"])
        g["suspicion"] = random_walk(g["suspicion"])

        if lobby_state["phase_remaining"] <= 0:
            _advance_phase()
        else:
            sio.emit(
                "phase_tick",
                {
                    "phase_index": lobby_state["phase_index"],
                    "remaining": lobby_state["phase_remaining"],
                    "gauges": lobby_state["gauges"],
                },
                room=TRIAL_ROOM,
            )


def _advance_phase():
    lobby_state["phase_index"] += 1
    if lobby_state["phase_index"] >= len(DEFAULT_PHASES):
        lobby_state["voting_open"] = True
        sio.emit("phase_ended", {"votes": lobby_state["votes"]}, room=TRIAL_ROOM)
        return

    key = current_phase_key()
    lobby_state["phase_remaining"] = lobby_state["phase_durations"][key]
    sio.emit(
        "phase_changed",
        {
            "phase_index": lobby_state["phase_index"],
            "remaining": lobby_state["phase_remaining"],
            "gauges": lobby_state["gauges"],
        },
        room=TRIAL_ROOM,
    )
