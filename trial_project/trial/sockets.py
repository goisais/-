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

    # 現在のフェーズ・ゲージ・判決の状態を追いつかせる
    sio.emit(
        "state_sync",
        {
            "phase_index": lobby_state["phase_index"],
            "phase_remaining": lobby_state["phase_remaining"],
            "gauges": lobby_state["gauges"],
            "voting_open": lobby_state["voting_open"],
            "votes": lobby_state["votes"],
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
    name = (data or {}).get("name") or "匿名"
    choice = (data or {}).get("choice")
    if choice not in ("guilty", "innocent"):
        return
    if not lobby_state["voting_open"]:
        return
    if name in lobby_state["voters"]:
        return
    lobby_state["voters"].append(name)
    lobby_state["votes"][choice] += 1
    sio.emit("verdict_update", {"votes": lobby_state["votes"]}, room=TRIAL_ROOM)


@sio.event
def finalize_verdict(sid, data=None):
    """ホストが「判決を確定する」を押したときに呼ばれる。投票を締め切り、
    有罪/無罪と（有罪なら）刑罰をランダムに決めて、全員を判決ページへ誘導する。"""
    if not lobby_state["trial_started"]:
        return
    if lobby_state["verdict_result"] is not None:
        return  # 二重確定防止
    result = determine_verdict()
    sio.emit("verdict_finalized", result, room=TRIAL_ROOM)


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
