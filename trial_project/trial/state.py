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

GUILTY_SENTENCES = [
    "懲役3年（執行猶予つき）",
    "懲役10年",
    "無期懲役",
    "終身・罰ゲーム刑",
    "土下座100回の刑",
    "反省文3000字執筆の刑",
    "帰りのHRで公開謝罪の刑",
    "1週間キャラ変の刑",
    "みんなの前で一発ギャグの刑",
    "次の遅刻理由を3倍面白くする刑",
]

# ごく稀に「歴史的大犯罪」演出（指名手配ポスター風）になる、有罪の中でも一番重い枠
WANTED_TITLES = [
    "史上最悪の大犯罪者",
    "歴史に刻まれた大罪人",
    "国家がざわついた大事件の主犯",
    "伝説級の言い訳犯罪者",
    "極悪指名手配犯",
]
WANTED_TIER_CHANCE = 0.35  # 有罪判決のうち、約35%がこの演出になる

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
        "phase_index": -1,  # -1=未開廷、0=被告人陳述、1=検察質問、2=弁護士弁護、3=全フェーズ終了
        "phase_remaining": 0,  # 現在のフェーズの残り秒数
        "gauges": {"nervousness": 50, "suspicion": 50},
        "voting_open": False,
        "votes": {"guilty": 0, "innocent": 0},
        "voters": [],  # 投票済みの名前一覧（二重投票防止）
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
            "phase_index": 0,
            "phase_remaining": lobby_state["phase_durations"][DEFAULT_PHASES[0]["key"]],
            "gauges": {"nervousness": 50, "suspicion": 50},
            "voting_open": False,
            "votes": {"guilty": 0, "innocent": 0},
            "voters": [],
            "verdict_result": None,  # {"outcome": "guilty"/"innocent", "sentence": str|None, "tier": "normal"/"wanted"}
            "defendant_face_capture": None,  # 被告人の顔切り抜き画像(data URL文字列)
        }
    )


def current_phase_key():
    idx = lobby_state["phase_index"]
    if 0 <= idx < len(DEFAULT_PHASES):
        return DEFAULT_PHASES[idx]["key"]
    return None


def random_walk(current, spread=8):
    delta = random.randint(-spread, spread)
    return max(0, min(100, current + delta))


def determine_verdict():
    """投票を締め切って、有罪/無罪と（有罪なら）刑罰をランダムに決める。
    有罪の中でもごく稀に、指名手配ポスター風の「歴史的大犯罪」演出(tier="wanted")になる。"""
    votes = lobby_state["votes"]
    if votes["guilty"] == votes["innocent"]:
        outcome = random.choice(["guilty", "innocent"])
    else:
        outcome = "guilty" if votes["guilty"] > votes["innocent"] else "innocent"

    tier = "normal"
    sentence = None
    if outcome == "guilty":
        if random.random() < WANTED_TIER_CHANCE:
            tier = "wanted"
            sentence = random.choice(WANTED_TITLES)
        else:
            sentence = random.choice(GUILTY_SENTENCES)

    result = {"outcome": outcome, "sentence": sentence, "tier": tier}
    lobby_state["verdict_result"] = result
    lobby_state["voting_open"] = False
    return result
