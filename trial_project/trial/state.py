"""
言い訳裁判 - 画面をまたいで共有する状態

シンプルにメモリ上の1つの辞書(lobby_state)で管理しています。
サーバー(manage.py runserver)を再起動すると状態はリセットされます。
複数の裁判を同時開催したい場合は、部屋(room)ごとに状態を分ける改修が別途必要です。
"""

import random

def generate_access_code():
    return f"{random.randint(0, 9999):04d}"


# ---------- 投げ銭(妨害ギフト)素材 ----------
# 全部グリーンバック(緑背景)の動画。透過はここでは焼き込まず、配信画面側で
# キャンバスにフレームを描いてピクセル単位で緑を透明化する(Safariでもここまでの
# 経験上、動画自体にアルファチャンネルを持たせるより確実に動く)。
# 全素材 260x260 に統一済み(元の比率を保ったまま緑パディング)、音声あり。
GIFT_ASSETS = [f"gift_{i:02d}.mp4" for i in range(1, 16)]
GIFT_COST = 3  # 1回送るのに使う裁判内ポイント(傍聴席の10p持ち点のうち)


# ---------- アカウント永続化(メール登録なしの匿名プロフィール) ----------
# ブラウザのlocalStorageに保存された匿名トークン(player_token)ごとに、
# 名前と永続ポイントを保持する。lobby_state(裁判ごとにリセットされる部屋の状態)とは
# 別物で、ホストが新しく開廷してもここは初期化しない。
# サーバーを再起動すると(lobby_stateと同じく)消える点は今のところ変わらない。
player_profiles = {}  # player_token(str) -> {"name": str, "points": int}


GALLERY_ALLOCATION = 10  # 傍聴席に毎裁判平等に配当される「裁判内ポイント」


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


# ---------- ゲーム形式のお題テンプレ ----------
# 難易度は「弁護側(被告人+弁護人)にとってどれだけ不利か」の1本軸。
#   easy   = 弁護側有利(検察がアンダードッグ)
#   medium = 五分五分
#   hard   = 弁護側不利(被告人・弁護人がアンダードッグ)
# ここではスコアのボーナス計算には使わない(オッズは賭けの偏りで自然に決まるので)。
# 主に演出(お題発表画面での「難易度」表示)用のフレーバー情報。
CASE_TEMPLATES = [
    {
        "title": "電車寝坊で大遅刻事件",
        "charge": "部活の大事な大会の集合に1時間遅刻した",
        "situation": "大会当日の朝、集合時間になっても被告人が現れず、みんなが1時間待った。",
        "claim": "目覚まし全部鳴らしたのに寝過ごした。前日は準備で夜遅くまで頑張ってた。",
        "questions": ["本当に準備してた証拠はある?", "目覚ましを何個セットしてた?"],
        "difficulty": "easy",
    },
    {
        "title": "模試当日寝坊事件",
        "charge": "大事な模試の日に遅刻した",
        "situation": "模試当日、開始時刻を過ぎても被告人が会場に現れなかった。",
        "claim": "体調不良で薬を飲んだら熟睡してしまった。",
        "questions": ["体調不良なら病院の記録は?", "前日は何時に寝た?"],
        "difficulty": "easy",
    },
    {
        "title": "忘れ物で待ち合わせ大遅刻事件",
        "charge": "待ち合わせに家まで戻ったせいで大遅刻した",
        "situation": "待ち合わせの直前、被告人が突然「忘れ物を取りに戻る」と言って家に引き返した。",
        "claim": "相手のために大事なものを取りに戻っただけ。",
        "questions": ["その『大事なもの』を今すぐ見せられる?", "LINEで一言連絡はできたのでは?"],
        "difficulty": "easy",
    },
    {
        "title": "立ち話で遅刻事件",
        "charge": "友達との立ち話が長引いて約束の時間に遅刻した",
        "situation": "道端で友達に話しかけられ、そのまま長時間立ち話をしてしまい遅刻した。",
        "claim": "本当に切り上げようとしたけど、相手が話を続けた。",
        "questions": ["切り上げるタイミングは何度もあったのでは?", "その間スマホは触ってた?"],
        "difficulty": "easy",
    },
    {
        "title": "割り勘バックレ事件",
        "charge": "飲み会の会計時に『財布がない』と言ってその場を去った",
        "situation": "会計のタイミングで被告人が急に財布がないと言い出し、そのまま先に帰ってしまった。",
        "claim": "本当に財布を無くしていて、後で必ず払うつもりだった。",
        "questions": ["その後ちゃんと連絡して払ったのか?", "財布は本当に見つかったのか?"],
        "difficulty": "medium",
    },
    {
        "title": "借り物破損隠蔽事件",
        "charge": "友達から借りたものを壊したのに、しばらく黙っていた",
        "situation": "借りていたものが壊れていることに気づいていたが、返す直前まで何も言わなかった。",
        "claim": "気づいたのが返す直前で、パニックになって言い出せなかった。",
        "questions": ["気づいてからどれくらい黙ってた?", "隠そうとした形跡はある?"],
        "difficulty": "medium",
    },
    {
        "title": "課題未提出(アプリ不具合主張)事件",
        "charge": "期限までに課題を提出できなかった",
        "situation": "提出期限の直前、課題提出アプリがフリーズして提出できなかったと主張している。",
        "claim": "本当にやったし提出しようとした。スクショも撮ってある。",
        "questions": ["そのスクショ、いつ撮った?", "先生に事前連絡はした?"],
        "difficulty": "medium",
    },
    {
        "title": "犬が宿題を食べた事件",
        "charge": "宿題を提出できなかった",
        "situation": "宿題が未提出のまま提出期限を迎えた。",
        "claim": "本当に飼い犬が宿題を全部食べた。証拠は犬の口についた紙くず。",
        "questions": ["食べかすの写真はある?", "そんな大量の紙を犬が食べて無事なのか?"],
        "difficulty": "hard",
    },
    {
        "title": "UFO誘拐スピーチ欠席事件",
        "charge": "友人の結婚式のスピーチを完全にすっぽかした",
        "situation": "結婚式当日、スピーチの出番が来ても被告人は会場に現れず、一切連絡もなかった。",
        "claim": "前日の夜にUFOに連れ去られていて、気づいたら朝で連絡する余裕がなかった。",
        "questions": ["目撃者はいるのか?", "その間のスマホの履歴はどうなってる?"],
        "difficulty": "hard",
    },
    {
        "title": "異国突然出現事件",
        "charge": "大事な用事に3日間音信不通だった",
        "situation": "3日間まったく連絡が取れず、みんなが心配していたところ、突然帰ってきた。",
        "claim": "気づいたら知らない国の空港にいて、パスポートも財布もなかった。",
        "questions": ["どうやって帰ってきたのか?", "航空券の記録は?"],
        "difficulty": "hard",
    },
]

DIFFICULTY_LABELS = {"easy": "易", "medium": "中", "hard": "難"}


def pick_random_case_template():
    return dict(random.choice(CASE_TEMPLATES))


def pick_random_defendant():
    if not lobby_state["participants"]:
        return None
    return random.choice(lobby_state["participants"])


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
        "wallets": {},  # 傍聴席の名前 -> 裁判内ポイント残高(毎裁判10pからスタート)
        "bets": {},  # 傍聴席の名前 -> [{"choice": "guilty"/"innocent", "amount": int}, ...] (複数回OK)
        "bet_counts": {"guilty": 0, "innocent": 0},  # 賭けられた「件数」(金額は見せない、ブラフ用)
        "mode": "classic",  # "classic"(今までの自由形式) or "game"(ユーモア王選手権むけの新モード)
        "case_template": None,  # ゲーム形式で抽選されたお題(タイトル・罪状・状況・言い分・難易度)
        "ranking": None,  # ゲーム形式の判決確定時に計算される、その裁判のランキング結果
        "objection_card_used": {"prosecutor": False, "defense": False},  # ゲーム形式の異議ありカード(1裁判1回)
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


def _init_gallery_wallets(role_map):
    """傍聴席(役職なし)の全員に、毎裁判平等にGALLERY_ALLOCATION(=10p)を配当する。
    このポイントは、有罪/無罪への賭けと投げ銭妨害の両方に使う「裁判内だけの持ち点」で、
    次の裁判には持ち越さない(持ち越すのはランキング結果でもらえる永続ポイントの方)"""
    return {name: GALLERY_ALLOCATION for name, role in role_map.items() if role == "gallery"}


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
            "wallets": _init_gallery_wallets(role_map),
            "bets": {},
            "bet_counts": {"guilty": 0, "innocent": 0},
        }
    )


GAME_MODE_PHASE_SECONDS = 60  # ゲーム形式は全フェーズ1分固定(お題の難易度に関わらず)


def start_trial_game_mode(defendant, case_template):
    """ゲーム形式の裁判開始。自由形式のstart_trial()とほぼ同じ流れだが、
    フェーズ時間は毎回1分固定、mode="game"、抽選されたお題(case_template)を保持する。
    自由形式のstart_trial()自体は一切変更していない"""
    prosecutor, defense = _draw_prosecutor_and_defense(defendant)
    role_map = _build_role_map(defendant, prosecutor, defense)
    duration = GAME_MODE_PHASE_SECONDS

    lobby_state.update(
        {
            "mode": "game",
            "case_name": case_template["title"],
            "case_template": case_template,
            "defendant": defendant,
            "trial_started": True,
            "prosecutor": prosecutor,
            "defense": defense,
            "role_map": role_map,
            "objection_count": 0,
            "comments": [],
            "phase_durations": {"defendant": duration, "prosecutor": duration, "defense": duration},
            "phase_index": 0,
            "phase_remaining": duration,
            "gauges": {"nervousness": 50, "suspicion": 50},
            "voting_open": False,
            "votes": {"guilty": 0, "innocent": 0},
            "voters": [],
            "verdict_result": None,
            "defendant_face_capture": None,
            "trial_round": 1,
            "judge_name": None,
            "wallets": _init_gallery_wallets(role_map),
            "bets": {},
            "bet_counts": {"guilty": 0, "innocent": 0},
            "objection_card_used": {"prosecutor": False, "defense": False},
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


def place_bet(name, choice, amount):
    """傍聴席が、有罪/無罪どちらかに賭ける。1裁判で何度でも・両方に分けて賭けられる
    (被告人に3p、検察に5p、みたいな両建てもOK)。金額は隠すが、賭けた「件数」は
    bet_countsでリアルタイムに増える(ブラフ用)。
    判決を決める投票と同じ人が同じ裁判で両方やると「自分が得する方に投票する」が
    できてしまうので、1回でも賭けた人は投票できないようにする(cast_vote側でチェック)。
    戻り値: (成功したか, エラーメッセージ or 更新後の残高)"""
    if choice not in ("guilty", "innocent"):
        return False, "invalid_choice"
    if lobby_state["role_map"].get(name) != "gallery":
        return False, "not_gallery"  # 役職がある人は裁判内ウォレットを持たない
    if lobby_state["voting_open"]:
        return False, "betting_closed"  # 投票が始まったら賭けは締め切り
    if name in lobby_state["voters"]:
        return False, "already_voted"  # 投票した人はもう賭けられない
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return False, "invalid_amount"
    balance = lobby_state["wallets"].get(name, 0)
    if amount <= 0 or amount > balance:
        return False, "insufficient_balance"

    lobby_state["wallets"][name] = balance - amount
    lobby_state["bets"].setdefault(name, []).append({"choice": choice, "amount": amount})
    lobby_state["bet_counts"][choice] = lobby_state["bet_counts"].get(choice, 0) + 1
    return True, lobby_state["wallets"][name]


def _resolve_bets(outcome):
    """(自由形式で使う、素朴な清算方式)的中者にはamountの2倍を払い戻す。
    1人1回しか賭けない前提の古い形式で使う。ゲーム形式は_resolve_bets_pari_mutuelを使う"""
    for name, bets in lobby_state["bets"].items():
        for bet in bets:
            if bet["choice"] == outcome:
                lobby_state["wallets"][name] = lobby_state["wallets"].get(name, 0) + bet["amount"] * 2


def _random_sentence_and_tier(outcome):
    """outcome("guilty"/"innocent")から、刑罰(・指名手配演出かどうか)をランダムに決める。
    自由形式・ゲーム形式どちらの判決確定処理からも共通で使う"""
    tier = "normal"
    sentence = None
    if outcome == "guilty":
        if random.random() < WANTED_TIER_CHANCE:
            tier = "wanted"
            sentence = random.choice(WANTED_TITLES)
        else:
            sentence = random_guilty_sentence()
    return sentence, tier


def _build_verdict_result(outcome):
    """(自由形式で使う)outcomeを確定させて、有罪なら刑罰も決める。賭けの清算は
    素朴な2倍方式(_resolve_bets)。ゲーム形式は_build_verdict_result_game_modeを使う"""
    sentence, tier = _random_sentence_and_tier(outcome)

    _resolve_bets(outcome)

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
            "wallets": _init_gallery_wallets(role_map),
            "bets": {},
            "bet_counts": {"guilty": 0, "innocent": 0},
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


# =====================================================================
# ゲーム形式(ユーモア王選手権むけの新モード)専用のロジック。
# 自由形式(今までの、ホストが被告人・時間を決める形式)のコードは一切変更していない。
# ゲーム形式は2審・3審に進まない。同数決着になっても、投票→賭けの傾向→運の順に
# フォールバックして必ずその場で判決を出す。
# =====================================================================

def _bet_pool_totals():
    """有罪/無罪それぞれに、全員の賭け金がいくら集まっているかを合計する
    (オッズ計算・タイの時のフォールバック判定に使う。表には金額そのものは出さない)"""
    totals = {"guilty": 0, "innocent": 0}
    for bets in lobby_state["bets"].values():
        for bet in bets:
            totals[bet["choice"]] += bet["amount"]
    return totals


def determine_verdict_game_mode():
    """ゲーム形式の判決決定。優先順位は
    1. 投票が割れていれば、多数決で決定(今まで通り、傍聴席の中でも賭けていない人だけの投票)
    2. 投票が同数(全員が賭けに回って0-0になるケースを含む)なら、賭け総額が多い方で決定
       (「みんなの財布が向いてる方」。これも運ではなく集合知)
    3. それすら完全に同額(あるいは無投票・無賭け)なら、最後だけ運で決める
    賭けの清算はパリミュチュエル方式(_resolve_bets_pari_mutuel)で行う"""
    votes = lobby_state["votes"]
    if votes["guilty"] != votes["innocent"]:
        outcome = "guilty" if votes["guilty"] > votes["innocent"] else "innocent"
        decided_by = "vote"
    else:
        pools = _bet_pool_totals()
        if pools["guilty"] != pools["innocent"]:
            outcome = "guilty" if pools["guilty"] > pools["innocent"] else "innocent"
            decided_by = "bet_pool"
        else:
            outcome = random.choice(["guilty", "innocent"])
            decided_by = "coin_flip"

    result = _build_verdict_result_game_mode(outcome)
    result["decided_by"] = decided_by
    return result


def _resolve_bets_pari_mutuel(outcome):
    """判決確定時に、傍聴席の賭けをパリミュチュエル(オッズ)方式で清算する。
    負けた側の賭け金の合計を、勝った側の人たちで自分の賭け金の比率に応じて山分けする。
    不人気な方(集まった金額が少ない方)に賭けて当てるほど高配当になる。
    賭けた時点で残高からamountを引いてあるので、ここでは勝ち分だけを払い戻す"""
    pools = _bet_pool_totals()
    winning_pool = pools[outcome]
    losing_pool = pools["innocent" if outcome == "guilty" else "guilty"]

    if winning_pool <= 0:
        return  # 勝った側に誰も賭けていなければ、山分けする相手がいない

    for name, bets in lobby_state["bets"].items():
        stake = sum(b["amount"] for b in bets if b["choice"] == outcome)
        if stake <= 0:
            continue
        payout = stake + (stake / winning_pool) * losing_pool
        lobby_state["wallets"][name] = lobby_state["wallets"].get(name, 0) + round(payout)


def _build_verdict_result_game_mode(outcome):
    """ゲーム形式の判決確定処理。_build_verdict_result(自由形式用)とほぼ同じだが、
    賭けの清算がパリミュチュエル方式になる点だけが違う"""
    sentence, tier = _random_sentence_and_tier(outcome)

    _resolve_bets_pari_mutuel(outcome)

    result = {"outcome": outcome, "sentence": sentence, "tier": tier}
    lobby_state["verdict_result"] = result
    lobby_state["voting_open"] = False
    return result


# 役職者(被告人・検察官・弁護人)の裁判内スコア。勝った側は20p、負けた側は5p
# (参加賞)。検察官/弁護人が「異議ありカード」を使って勝った場合は18pに割引く
# (カードという強い武器を使った分のハンデ)。カード未実装の間はcard_used=Falseのまま
COURT_ROLE_WIN_SCORE = 20
COURT_ROLE_WIN_SCORE_WITH_CARD = 18
COURT_ROLE_LOSE_SCORE = 5

# 各役職が「勝ち」とみなされるのはどちらの判決が出た時か
_FAVORABLE_OUTCOME = {
    "defendant": "innocent",
    "defense": "innocent",
    "prosecutor": "guilty",
}

# 異議ありカード: 検察官・弁護人がそれぞれ1裁判に1回だけ使える。相手の「持ち時間」
# (=相手が担当するフェーズ)から一気に20秒奪う。奪う対象のフェーズは固定:
#   検察官のカード → 弁護士弁護フェーズ(phase_index=2)の残り時間を削る
#   弁護人のカード → 検察質問フェーズ(phase_index=1)の残り時間を削る
# 被告人陳述フェーズ(phase_index=0)からは奪えない(被告人はどちらの「相手」でもないため)
OBJECTION_CARD_STEAL_SECONDS = 20
_OBJECTION_CARD_TARGET_PHASE = {"prosecutor": 2, "defense": 1}


def use_objection_card(name, role):
    """検察官/弁護人が異議ありカードを使う。成功したら(True, 奪った秒数)、
    失敗したら(False, 理由文字列)を返す。ゲーム形式以外・役職不一致・使用済み・
    相手のフェーズ中でない場合は失敗する。残り時間が1秒未満にはならないようにする"""
    if lobby_state.get("mode") != "game":
        return False, "not_game_mode"
    if role not in ("prosecutor", "defense"):
        return False, "invalid_role"
    if lobby_state["role_map"].get(name) != role:
        return False, "not_your_role"
    used = lobby_state.setdefault("objection_card_used", {"prosecutor": False, "defense": False})
    if used.get(role):
        return False, "already_used"
    target_phase = _OBJECTION_CARD_TARGET_PHASE[role]
    if lobby_state["phase_index"] != target_phase:
        return False, "not_opponent_turn"

    steal = min(OBJECTION_CARD_STEAL_SECONDS, max(0, lobby_state["phase_remaining"] - 1))
    lobby_state["phase_remaining"] -= steal
    used[role] = True
    return True, steal


# 投げ銭(妨害ギフト)のタイミング制限。被告人陳述フェーズ(自分の裁判)中は最初の40秒は
# 送れず、残り20秒(=経過40秒以降)だけ解禁する。検察質問・弁護士弁護フェーズ中は
# タイミング無制限。フェーズが進んでいない/終わっている場合は送れない
GIFT_LOCKED_REMAINING_THRESHOLD = 20  # 被告人陳述フェーズは残りがこの秒数以下になるまで送れない


def send_gift(name, gift_index):
    """傍聴席が自分の裁判内ポイントを使って、妨害ギフト動画を送る。
    金額はGIFT_COST固定。成功したら(True, 送信後の残高)、失敗したら(False, 理由)を返す"""
    if lobby_state.get("mode") != "game":
        return False, "not_game_mode"
    if lobby_state["role_map"].get(name) != "gallery":
        return False, "not_gallery"
    if not isinstance(gift_index, int) or not (0 <= gift_index < len(GIFT_ASSETS)):
        return False, "invalid_gift"

    phase_index = lobby_state["phase_index"]
    if phase_index == 0:
        if lobby_state["phase_remaining"] > GIFT_LOCKED_REMAINING_THRESHOLD:
            return False, "defendant_statement_locked"
    elif phase_index not in (1, 2):
        return False, "no_active_phase"

    balance = lobby_state["wallets"].get(name, 0)
    if balance < GIFT_COST:
        return False, "insufficient_balance"

    lobby_state["wallets"][name] = balance - GIFT_COST
    return True, lobby_state["wallets"][name]

# 傍聴席全員(役職者以外)の最終順位に応じて付与する永続ポイント。
# 同じスコアの人は同じ順位・同じ永続ポイントになる(例:1位が2人ならどちらも10p)
RANKING_REWARDS = [10, 6, 3]  # 1位, 2位, 3位。4位以降は0p


def _court_role_score(role, outcome):
    card_used = lobby_state.get("objection_card_used", {}).get(role, False)
    won = _FAVORABLE_OUTCOME.get(role) == outcome
    if not won:
        return COURT_ROLE_LOSE_SCORE
    return COURT_ROLE_WIN_SCORE_WITH_CARD if card_used else COURT_ROLE_WIN_SCORE


def compute_game_mode_ranking(outcome):
    """判決確定後に、被告人・検察官・弁護人・傍聴席全員を同じ物差し(裁判内スコア)で
    並べてランキングを出し、上位者に永続ポイント(RANKING_REWARDSの10/6/3、
    4位以下は0)を付与する。同スコアの人は同順位・同ポイントになる。
    戻り値: [{"name", "role", "score", "rank"}, ...] （スコア降順）"""
    entries = []
    for role in ("defendant", "prosecutor", "defense"):
        name = lobby_state.get(role)
        if name:
            entries.append({"name": name, "role": role, "score": _court_role_score(role, outcome)})

    for name, balance in lobby_state["wallets"].items():
        entries.append({"name": name, "role": "gallery", "score": balance})

    entries.sort(key=lambda e: e["score"], reverse=True)

    # 同スコアなら同順位にする(例: 20, 20, 14, 10 → 順位は 1, 1, 2, 3)
    rank = 0
    prev_score = None
    for entry in entries:
        if entry["score"] != prev_score:
            rank += 1
            prev_score = entry["score"]
        entry["rank"] = rank
        reward = RANKING_REWARDS[rank - 1] if rank <= len(RANKING_REWARDS) else 0
        entry["bonus_points"] = reward
        token = lobby_state["player_tokens"].get(entry["name"])
        if token:
            award_points(token, reward)

    lobby_state["ranking"] = entries
    return entries
