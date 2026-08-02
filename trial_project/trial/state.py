"""
言い訳裁判 - 画面をまたいで共有する状態

シンプルにメモリ上の1つの辞書(lobby_state)で管理しています。
サーバー(manage.py runserver)を再起動すると状態はリセットされます。
複数の裁判を同時開催したい場合は、部屋(room)ごとに状態を分ける改修が別途必要です。
"""

import random

def generate_access_code():
    return f"{random.randint(0, 9999):04d}"


DEFAULT_PHASES = [
    {"key": "defendant", "label": "被告人陳述", "icon": "ti-microphone"},
    {"key": "prosecutor", "label": "検察質問", "icon": "ti-shield-half-filled"},
    {"key": "defense", "label": "弁護士弁護", "icon": "ti-scale"},
]

ROLE_META = {
    "defendant": {
        "label": "被告人",
        "icon": "ti-user",
        "description": "堂々と弁明しよう",
        "accent": "danger",
    },
    "prosecutor": {
        "label": "検察官",
        "icon": "ti-shield-half-filled",
        "description": "被告人に鋭い質問を投げかけよう",
        "accent": "danger",
    },
    "defense": {
        "label": "弁護人",
        "icon": "ti-scale",
        "description": "被告人の味方になって弁護しよう",
        "accent": "accent",
    },
    "gallery": {
        "label": "傍聴席",
        "icon": "ti-users",
        "description": "コメントや異議ありで裁判を盛り上げよう",
        "accent": "accent",
    },
}


def make_initial_state():
    return {
        "access_code": "",  # ホストが開廷準備を始めるたびに新しく発行される4桁コード
        "participants": [],  # 参加者名の一覧（順番 = 参加した順）
        "case_name": "",
        "defendant": None,
        "phase_durations": {"defendant": 120, "prosecutor": 90, "defense": 90},
        "trial_started": False,
        "prosecutor": None,
        "defense": None,
        "role_map": {},  # 名前 -> role key
        "objection_count": 0,
        "comments": [],  # [{"name": ..., "text": ...}]
    }


lobby_state = make_initial_state()


def format_mmss(total_seconds):
    m, s = divmod(int(total_seconds), 60)
    return f"{m}:{s:02d}"


def parse_mmss_to_seconds(text, fallback=90):
    text = (text or "").strip()
    if ":" in text:
        try:
            m, s = text.split(":")
            return max(10, int(m) * 60 + int(s))
        except ValueError:
            return fallback
    try:
        return max(10, int(text))
    except ValueError:
        return fallback


def reset_for_new_round():
    """ホストが「ホストとして開廷する」を押すたびに、新しい部屋として作り直す。
    前回の参加者やコードは引き継がない。"""
    fresh = make_initial_state()
    fresh["access_code"] = generate_access_code()
    lobby_state.update(fresh)
    return lobby_state["access_code"]


def start_trial(case_name, defendant):
    """被告人以外の参加者から検察官・弁護人をガチャで抽選し、状態を確定する"""
    others = [p for p in lobby_state["participants"] if p != defendant]
    random.shuffle(others)
    prosecutor = others.pop() if others else None
    defense = others.pop() if others else None

    role_map = {defendant: "defendant"}
    if prosecutor:
        role_map[prosecutor] = "prosecutor"
    if defense:
        role_map[defense] = "defense"
    for p in lobby_state["participants"]:
        role_map.setdefault(p, "gallery")

    lobby_state.update(
        {
            "case_name": case_name,
            "defendant": defendant,
            "trial_started": True,
            "prosecutor": prosecutor,
            "defense": defense,
            "role_map": role_map,
            "objection_count": 0,
            "comments": [],
        }
    )
