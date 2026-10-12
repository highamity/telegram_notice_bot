"""
Unit tests for fun_features.py (Poker evaluation & Fortune).
"""

from fun_features import (
    Card,
    evaluate_poker_hand,
    get_daily_fortune,
    draw_poker_hand,
)


def test_poker_royal_straight_flush():
    cards = [
        Card("♠️", "10"),
        Card("♠️", "J"),
        Card("♠️", "Q"),
        Card("♠️", "K"),
        Card("♠️", "A"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "로열 스트레이트 플러시" in name, f"Expected Royal Flush, got {name}"


def test_poker_straight_flush():
    cards = [
        Card("♥️", "5"),
        Card("♥️", "6"),
        Card("♥️", "7"),
        Card("♥️", "8"),
        Card("♥️", "9"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "스트레이트 플러시" in name, f"Expected Straight Flush, got {name}"


def test_poker_back_straight_flush():
    cards = [
        Card("♦️", "A"),
        Card("♦️", "2"),
        Card("♦️", "3"),
        Card("♦️", "4"),
        Card("♦️", "5"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "백 스트레이트 플러시" in name, f"Expected Back Straight Flush, got {name}"


def test_poker_four_of_a_kind():
    cards = [
        Card("♣️", "9"),
        Card("♠️", "9"),
        Card("♥️", "9"),
        Card("♦️", "9"),
        Card("♠️", "K"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "포카드" in name, f"Expected Four of a Kind, got {name}"
    assert sorted_cards[0].rank == "9"
    assert sorted_cards[-1].rank == "K"


def test_poker_full_house():
    cards = [
        Card("♠️", "J"),
        Card("♥️", "J"),
        Card("♦️", "J"),
        Card("♣️", "4"),
        Card("♠️", "4"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "풀 하우스" in name, f"Expected Full House, got {name}"
    assert sorted_cards[0].rank == "J"
    assert sorted_cards[-1].rank == "4"


def test_poker_flush():
    cards = [
        Card("♠️", "2"),
        Card("♠️", "5"),
        Card("♠️", "8"),
        Card("♠️", "J"),
        Card("♠️", "K"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "플러시" in name and "스트레이트" not in name, f"Expected Flush, got {name}"


def test_poker_mountain():
    cards = [
        Card("♠️", "10"),
        Card("♥️", "J"),
        Card("♦️", "Q"),
        Card("♣️", "K"),
        Card("♠️", "A"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "마운틴" in name, f"Expected Mountain, got {name}"


def test_poker_back_straight():
    cards = [
        Card("♠️", "A"),
        Card("♥️", "2"),
        Card("♦️", "3"),
        Card("♣️", "4"),
        Card("♠️", "5"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "백스트레이트" in name, f"Expected Back Straight, got {name}"


def test_poker_straight():
    cards = [
        Card("♠️", "4"),
        Card("♥️", "5"),
        Card("♦️", "6"),
        Card("♣️", "7"),
        Card("♠️", "8"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "스트레이트" in name, f"Expected Straight, got {name}"


def test_poker_three_of_a_kind():
    cards = [
        Card("♠️", "8"),
        Card("♥️", "8"),
        Card("♦️", "8"),
        Card("♣️", "2"),
        Card("♠️", "5"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "트리플" in name, f"Expected Three of a Kind, got {name}"
    assert sorted_cards[0].rank == "8"


def test_poker_two_pair():
    cards = [
        Card("♠️", "K"),
        Card("♥️", "K"),
        Card("♦️", "3"),
        Card("♣️", "3"),
        Card("♠️", "7"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "투 페어" in name, f"Expected Two Pair, got {name}"


def test_poker_one_pair():
    cards = [
        Card("♠️", "A"),
        Card("♥️", "A"),
        Card("♦️", "4"),
        Card("♣️", "7"),
        Card("♠️", "9"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "원 페어" in name, f"Expected One Pair, got {name}"


def test_poker_high_card():
    cards = [
        Card("♠️", "A"),
        Card("♥️", "K"),
        Card("♦️", "8"),
        Card("♣️", "5"),
        Card("♠️", "2"),
    ]
    name, sorted_cards = evaluate_poker_hand(cards)
    assert "하이 카드" in name, f"Expected High Card, got {name}"


def test_draw_poker_hand():
    name, cards = draw_poker_hand()
    assert len(cards) == 5
    assert len(set(cards)) == 5  # No duplicates


def test_daily_fortune_determinism():
    res1 = get_daily_fortune(12345, "테스터", "2026-10-12")
    res2 = get_daily_fortune(12345, "테스터", "2026-10-12")
    assert res1 == res2, "Fortune must be identical for same user and day"

    res_different_day = get_daily_fortune(12345, "테스터", "2026-10-13")
    # Might technically match by 1 in 10000 chance, but seed differs
    assert "2026-10-13" in res_different_day

    res_different_user = get_daily_fortune(99999, "테스터", "2026-10-12")
    assert "테스터" in res_different_user


if __name__ == "__main__":
    test_poker_royal_straight_flush()
    test_poker_straight_flush()
    test_poker_back_straight_flush()
    test_poker_four_of_a_kind()
    test_poker_full_house()
    test_poker_flush()
    test_poker_mountain()
    test_poker_back_straight()
    test_poker_straight()
    test_poker_three_of_a_kind()
    test_poker_two_pair()
    test_poker_one_pair()
    test_poker_high_card()
    test_draw_poker_hand()
    test_daily_fortune_determinism()
    print("ALL TESTS PASSED SUCCESSFULLY!")
