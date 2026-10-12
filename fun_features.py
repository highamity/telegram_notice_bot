"""
Mini-games and entertainment features for Telegram Notice Bot:
1. Poker (5-card poker hand evaluation)
2. Daily Fortune (deterministic per user & date)
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_VALUES = {r: i for i, r in enumerate(RANKS, start=2)}  # 2: 2 ... A: 14
RANK_NAMES = {v: r for r, v in RANK_VALUES.items()}


@dataclass(frozen=True)
class Card:
    suit: str
    rank: str

    @property
    def value(self) -> int:
        return RANK_VALUES[self.rank]

    def __str__(self) -> str:
        return f"[{self.suit}{self.rank}]"


FULL_DECK: list[Card] = [Card(s, r) for s in SUITS for r in RANKS]


def evaluate_poker_hand(cards: Sequence[Card]) -> tuple[str, list[Card]]:
    """
    Evaluates a 5-card poker hand and returns (hand_name, sorted_cards).
    Sorted cards are arranged logically (pairs/trips first, then kickers).
    """
    if len(cards) != 5:
        raise ValueError("Poker hand must contain exactly 5 cards.")

    counts = Counter(c.value for c in cards)
    most_common = counts.most_common()
    vals = sorted([c.value for c in cards], reverse=True)

    is_unique_5 = len(set(vals)) == 5
    is_normal_straight = is_unique_5 and (vals[0] - vals[4] == 4)
    is_wheel_straight = is_unique_5 and (vals == [14, 5, 4, 3, 2])
    is_straight = is_normal_straight or is_wheel_straight
    is_flush = len(set(c.suit for c in cards)) == 1

    # Standard display ordering: by frequency desc, then value desc
    sorted_cards = sorted(cards, key=lambda c: (counts[c.value], c.value), reverse=True)

    if is_flush and is_straight:
        if vals == [14, 13, 12, 11, 10]:
            hand_name = "👑 로열 스트레이트 플러시 (Royal Straight Flush)"
        elif is_wheel_straight:
            hand_name = "🌟 백 스트레이트 플러시 (Back Straight Flush)"
            sorted_cards = sorted(cards, key=lambda c: (1 if c.value == 14 else c.value), reverse=True)
        else:
            hand_name = f"⚡ 스트레이트 플러시 (Straight Flush, {RANK_NAMES[vals[0]]} 하이)"
    elif most_common[0][1] == 4:
        four_rank = RANK_NAMES[most_common[0][0]]
        hand_name = f"🔥 포카드 (Four of a Kind, {four_rank} 4장)"
    elif most_common[0][1] == 3 and most_common[1][1] == 2:
        three_rank = RANK_NAMES[most_common[0][0]]
        two_rank = RANK_NAMES[most_common[1][0]]
        hand_name = f"🏠 풀 하우스 (Full House, {three_rank} & {two_rank})"
    elif is_flush:
        suit_name = cards[0].suit
        hand_name = f"🌊 플러시 (Flush, {suit_name} {RANK_NAMES[vals[0]]} 하이)"
    elif is_straight:
        if vals == [14, 13, 12, 11, 10]:
            hand_name = "⛰️ 마운틴 (Mountain / 10-A Straight)"
        elif is_wheel_straight:
            hand_name = "🚴 백스트레이트 (Back Straight / A-5 Wheel)"
            sorted_cards = sorted(cards, key=lambda c: (1 if c.value == 14 else c.value), reverse=True)
        else:
            hand_name = f"🎯 스트레이트 (Straight, {RANK_NAMES[vals[0]]} 하이)"
    elif most_common[0][1] == 3:
        trips_rank = RANK_NAMES[most_common[0][0]]
        hand_name = f"✨ 트리플 (Three of a Kind, {trips_rank} 3장)"
    elif most_common[0][1] == 2 and most_common[1][1] == 2:
        high_pair = RANK_NAMES[most_common[0][0]]
        low_pair = RANK_NAMES[most_common[1][0]]
        hand_name = f"✌️ 투 페어 (Two Pair, {high_pair} & {low_pair})"
    elif most_common[0][1] == 2:
        pair_rank = RANK_NAMES[most_common[0][0]]
        hand_name = f"🃏 원 페어 (One Pair, {pair_rank})"
    else:
        high_rank = RANK_NAMES[vals[0]]
        hand_name = f"🖐️ 하이 카드 (High Card, {high_rank} 탑)"

    return hand_name, sorted_cards


def draw_poker_hand() -> tuple[str, list[Card]]:
    """Draws 5 unique cards from a standard 52-card deck and evaluates them."""
    sampled = random.sample(FULL_DECK, 5)
    return evaluate_poker_hand(sampled)


def format_poker_result(user_name: str) -> str:
    """Draws a poker hand and returns a user-friendly message."""
    hand_name, cards = draw_poker_hand()
    cards_str = " ".join(str(c) for c in cards)
    return (
        f"🃏 [{user_name}]님의 포커 패:\n"
        f"{cards_str}\n\n"
        f"🏆 결과: {hand_name}"
    )


# Fortune message pool
FORTUNE_COMMENTS = [
    "생각지도 못한 곳에서 소소한 행복을 찾게 됩니다. 커피 한잔의 여유를 즐겨보세요! ☕",
    "말 한마디로 천 냥 빚을 갚는 날입니다. 주변에 따뜻한 칭찬을 건네보세요. 💬",
    "결정장애가 올 수 있는 날입니다. 직감을 믿고 첫 번째 생각을 밀고 나가세요! 🎯",
    "지출 유혹이 찾아올 수 있습니다. 장바구니 결제는 내일로 미뤄보세요. 💳",
    "주변 사람들에게 칭찬을 받거나 인정받을 기회가 생깁니다. 자신감을 가지세요! 👏",
    "에너지가 넘치는 날! 미뤄뒀던 귀찮은 일을 해치우기에 가장 좋은 타이밍입니다. 🚀",
    "맛있는 음식을 먹으면 피로가 싹 풀리는 날입니다. 맛있는 식사를 대접하세요. 🍲",
    "오타나 작은 실수가 생길 수 있으니 중요한 메시지는 전송 전 한 번 더 확인! 🔍",
    "오랜 지인이나 친구에게서 반가운 연락이 올 수 있습니다. 먼저 안부를 물어보세요. 📱",
    "오늘은 무리하지 말고 칼퇴 후 온전한 휴식을 취하는 것이 최고의 행운입니다. 🛌",
    "뜻밖의 횡재수가 있습니다! 지나가다 작은 복권을 사보거나 이벤트에 응모해보세요. 🎟️",
    "동료나 친구와의 협업이 아주 잘 풀리는 날입니다. 혼자 끙끙 앓지 마세요. 🤝",
    "새로운 아이디어가 샘솟는 날입니다. 떠오른 생각을 메모장에 적어두세요! 💡",
    "가벼운 산책이나 스트레칭이 큰 활력을 가져다줍니다. 잠시 햇볕을 쬐어보세요. ☀️",
    "마음의 여유가 필요한 날입니다. 서두르지 않아도 모든 일이 제자리를 찾습니다. 🧘",
    "웃으면 복이 옵니다! 사소한 일에도 유쾌하게 웃어넘겨보세요. 😄",
    "오늘 당신의 친절이 누군가에게 큰 힘이 됩니다. 선한 영향력을 발휘하세요. 🌿",
    "선택의 기로에서 고민된다면 평소에 안 해본 새로운 길을 선택해보세요! 🗺️",
    "작은 성취가 모여 큰 보람을 만듭니다. 오늘 할 일 하나를 깔끔히 끝내보세요. ✅",
    "좋은 음악이나 영상을 발견하게 될 운세입니다. 귀를 즐겁게 해주세요. 🎧",
]

FORTUNE_FOODS = [
    "제육볶음", "돈까스", "김치찌개", "초밥", "삼겹살",
    "짜장면", "짬뽕", "피자", "치킨", "국밥",
    "햄버거", "파스타", "떡볶이", "마라탕", "쌀국수",
    "샌드위치", "닭갈비", "갈비탕", "비빔밥", "칼국수",
    "보쌈/족발", "샐러드", "라멘", "카레", "냉면",
]

FORTUNE_COLORS = [
    "빨강 (Red)", "파랑 (Blue)", "노랑 (Yellow)", "초록 (Green)",
    "보라 (Purple)", "주황 (Orange)", "하늘색 (Sky Blue)",
    "핑크 (Pink)", "골드 (Gold)", "실버 (Silver)", "민트 (Mint)",
]


def get_daily_fortune(user_id: int, user_name: str, today_str: str) -> str:
    """
    Returns deterministic fortune results for the same user and day (KST).
    """
    seed_str = f"fortune:{today_str}:{user_id}"
    rng = random.Random(seed_str)

    score = rng.randint(55, 100)
    comment = rng.choice(FORTUNE_COMMENTS)
    food = rng.choice(FORTUNE_FOODS)
    color = rng.choice(FORTUNE_COLORS)
    lucky_num = rng.randint(1, 99)

    return (
        f"🍀 [{user_name}]님의 오늘의 운세 ({today_str})\n\n"
        f"• 🌟 행운 지수: {score}점\n"
        f"• 📜 오늘의 한마디: {comment}\n"
        f"• 🍽️ 행운의 메뉴: {food}\n"
        f"• 🎨 행운의 색상: {color}\n"
        f"• 🔢 행운의 숫자: {lucky_num}"
    )
