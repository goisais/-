"""
言い訳裁判 - Socket.IOサーバー(python-socketio)

クライアント側(各テンプレートの<script>内)は普通のSocket.IOクライアント
(`const socket = io();`)のままで、サーバー側だけこのファイルで受け止める。
DjangoのWSGIアプリと同じポートで動くように、wsgi.pyでラップしている。
"""

import socketio

from trial.state import lobby_state

LOBBY_ROOM = "lobby"
TRIAL_ROOM = "trial"

sio = socketio.Server(async_mode="threading", cors_allowed_origins="*")


@sio.event
def connect(sid, environ):
    pass


@sio.event
def join_lobby(sid):
    """開廷準備画面・待機画面が、参加者リストの更新を受け取れるようにする"""
    sio.enter_room(sid, LOBBY_ROOM)
    sio.emit("participants_updated", {"participants": lobby_state["participants"]}, to=sid)


@sio.event
def join_trial(sid):
    sio.enter_room(sid, TRIAL_ROOM)


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


def notify_participants_updated():
    sio.emit("participants_updated", {"participants": lobby_state["participants"]}, room=LOBBY_ROOM)


def notify_trial_started():
    sio.emit("trial_started", {}, room=LOBBY_ROOM)
