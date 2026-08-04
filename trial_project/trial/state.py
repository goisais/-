"""
言い訳裁判 - 画面をまたいで共有する状態

シンプルにメモリ上の1つの辞書(lobby_state)で管理しています。
サーバー(manage.py runserver)を再起動すると状態はリセットされます。
複数の裁判を同時開催したい場合は、部屋(room)ごとに状態を分ける改修が別途必要です。
"""

import random

def generate_access_code():
    return f"{random.randint(0, 9999):04d}"


# ---------- アカウント永続化(メール登録なしの匿名プロフィール) ----------
# ブラウザのlocalStorageに保存された匿名トークン(player_token)ごとに、
# 名前と永続ポイントを保持する。lobby_state(裁判ごとにリセットされる部屋の状態)とは
# 別物で、ホストが新しく開廷してもここは初期化しない。
# サーバーを再起動すると(lobby_stateと同じく)消える点は今のところ変わらない。
player_profiles = {}  # player_token(str) -> {"name": str, "points": int}


def get_or_create_profile(token, name):
    """このブラウザ(token)のプロフィールを取得。無ければ新規作成(ポイント0から)。
    名前は毎回の入室で最新のものに更新する(改名しても同じ持ち点を引き継げる)"""
    if not token:
        return None
    profile = player_profiles.get(token)
    if profile is None:
        profile = {"name": name, "points": 0}
        player_profiles[token] = profile
    else:
        profile["name"] = name
    return profile


def get_points(token):
    profile = player_profiles.get(token)
    return profile["points"] if profile else 0


def award_points(token, amount):
    """裁判終了後のランキング結果などで、永続ポイントを加算する"""
    profile = player_profiles.get(token)
    if profile:
        profile["points"] += amount
    return get_points(token)


DEFAULT_PHASES = [
    {"key": "defendant", "label": "被告人陳述", "icon": "ti-microphone"},
    {"key": "prosecutor", "label": "検察質問", "icon": "ti-shield-half-filled"},
    {"key": "defense", "label": "弁護士弁護", "icon": "ti-scale"},
]

MIN_PRISON_YEARS = 7
MAX_PRISON_YEARS = 30
LIFE_SENTENCE_CHANCE = 0.5  # 有罪(通常枠)のうち、約50%は無期懲役にする


def random_guilty_sentence():
    """有罪(通常枠)の刑罰をランダムに決める。無期懲役 or 懲役◯年(執行猶予つきのことも)"""
    if random.random() < LIFE_SENTENCE_CHANCE:
        return "無期懲役"
    years = random.randint(MIN_PRISON_YEARS, MAX_PRISON_YEARS)
    if random.random() < 0.5:
        return f"懲役{years}年（執行猶予付き）"
    return f"懲役{years}年"

# ごく稀に「歴史的大犯罪」演出（指名手配ポスター風）になる、有罪の中でも一番重い枠
WANTED_TITLES = [
    "史上最悪の大犯罪者",
    "歴史に刻まれた大罪人",
    "国家がざわついた大事件の主犯",
    "伝説級の言い訳犯罪者",
    "極悪指名手配犯",
]
WANTED_TIER_CHANCE = 0.5  # 有罪判決のうち、約50%がこの演出になる(通常枠と半々で交互っぽく出る)

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
        "host_name": "",  # ホストの名前（判決確定・次の審への進行などホスト限定操作の確認に使う）
        "participants": [],  # 参加者名の一覧（順番 = 参加した順）
        "player_tokens": {},  # 名前 -> player_token（永続ポイントの加算先を引くのに使う）
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
        "trial_round": 1,  # 1審/2審/3審
        "judge_name": None,  # 3審でも同数だったとき、強制的に判決を下す裁判長役の名前
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


def _draw_prosecutor_and_defense(defendant, prev_prosecutor=None, prev_defense=None):
    """被告人以外の参加者から検察官・弁護人をガチャで抽選する。
    ちょうど2人しか候補がいない(参加者が被告人含めて3人だけ)場合にランダム抽選すると
    「たまたま同じ組み合わせ」になることがあるので、前回の担当者2人がそのまま今回の
    候補2人と一致するときは、必ず入れ替える"""
    others = [p for p in lobby_state["participants"] if p != defendant]

    if len(others) == 2 and prev_prosecutor and prev_defense and set(others) == {prev_prosecutor, prev_defense}:
        return prev_defense, prev_prosecutor

    shuffled = others[:]
    random.shuffle(shuffled)
    prosecutor = shuffled.pop() if shuffled else None
    defense = shuffled.pop() if shuffled else None
    return prosecutor, defense


def _build_role_map(defendant, prosecutor, defense):
    role_map = {defendant: "defendant"}
    if prosecutor:
        role_map[prosecutor] = "prosecutor"
    if defense:
        role_map[defense] = "defense"
    for p in lobby_state["participants"]:
        role_map.setdefault(p, "gallery")
    return role_map


def start_trial(case_name, defendant):
    """被告人以外の参加者から検察官・弁護人をガチャで抽選し、状態を確定する"""
    prosecutor, defense = _draw_prosecutor_and_defense(defendant)
    role_map = _build_role_map(defendant, prosecutor, defense)

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
            "trial_round": 1,
            "judge_name": None,
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


def _build_verdict_result(outcome):
    """outcome("guilty"/"innocent")を確定させて、有罪なら刑罰(・指名手配演出かどうか)も決める"""
    tier = "normal"
    sentence = None
    if outcome == "guilty":
        if random.random() < WANTED_TIER_CHANCE:
            tier = "wanted"
            sentence = random.choice(WANTED_TITLES)
        else:
            sentence = random_guilty_sentence()

    result = {"outcome": outcome, "sentence": sentence, "tier": tier}
    lobby_state["verdict_result"] = result
    lobby_state["voting_open"] = False
    return result


def determine_verdict():
    """投票を締め切って、有罪/無罪と（有罪なら）刑罰をランダムに決める。
    有罪の中でもごく稀に、指名手配ポスター風の「歴史的大犯罪」演出(tier="wanted")になる。
    同数(引き分け)の場合はNoneを返す。呼び出し側で次の審に進めるか、
    3審目なら裁判長を選ぶかを判断する"""
    votes = lobby_state["votes"]
    if votes["guilty"] == votes["innocent"]:
        return None
    outcome = "guilty" if votes["guilty"] > votes["innocent"] else "innocent"
    return _build_verdict_result(outcome)


def judge_decide_verdict(outcome):
    """3審でも同数だったとき、裁判長役に選ばれた人が代わりに判決を下す"""
    return _build_verdict_result(outcome)


# 2審・3審のフェーズ時間は毎回固定(ホストが設定した時間は1審だけに使う)
ROUND_PHASE_SECONDS = {2: 60, 3: 30}


def advance_to_next_round():
    """判決が同数だったとき、ホストが次の審に進める。検察官・弁護人を再抽選し、
    フェーズを最初から(2審=1分固定、3審=30秒固定)やり直す。"""
    lobby_state["trial_round"] += 1
    round_num = lobby_state["trial_round"]
    duration = ROUND_PHASE_SECONDS.get(round_num, 30)

    defendant = lobby_state["defendant"]
    prosecutor, defense = _draw_prosecutor_and_defense(
        defendant, lobby_state["prosecutor"], lobby_state["defense"]
    )
    role_map = _build_role_map(defendant, prosecutor, defense)

    lobby_state.update(
        {
            "prosecutor": prosecutor,
            "defense": defense,
            "role_map": role_map,
            "phase_durations": {"defendant": duration, "prosecutor": duration, "defense": duration},
            "phase_index": 0,
            "phase_remaining": duration,
            "gauges": {"nervousness": 50, "suspicion": 50},
            "voting_open": False,
            "votes": {"guilty": 0, "innocent": 0},
            "voters": [],
            "verdict_result": None,
        }
    )
    return {
        "round": round_num,
        "prosecutor": prosecutor,
        "defense": defense,
        "duration": duration,
        "role_map": role_map,
    }


def select_judge():
    """3審でも同数だったとき、被告人以外の参加者からランダムに裁判長を選ぶ"""
    candidates = [p for p in lobby_state["participants"] if p != lobby_state["defendant"]]
    judge = random.choice(candidates) if candidates else None
    lobby_state["judge_name"] = judge
    return judge
