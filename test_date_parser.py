"""Unit test for date_parser.py."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from date_parser import (
    KST,
    DateParseError,
    calculate_dday_info,
    detect_repeat_yearly,
    format_dday_notification,
    parse_dday_input,
    parse_schedule_input,
)


def test_dday_calculation():
    today = date(2026, 9, 16)

    # 1. Day of event (wedding/birth today) -> MUST BE 1일째!
    badge, desc = calculate_dday_info(date(2026, 9, 16), today)
    assert badge == "D-Day", f"Expected D-Day for today, got {badge}"

    # 2. Yesterday -> MUST BE 2일째!
    badge, desc = calculate_dday_info(date(2026, 9, 15), today)
    assert badge == "2일째", f"Expected 2일째, got {badge}"
    assert desc == "2026-09-15"

    # 3. 2020-05-10 wedding -> 2321일째, 6주년, 2020-05-10!
    badge, desc = calculate_dday_info(date(2020, 5, 10), today, repeat_yearly=True)
    assert badge == "2321일째", f"Expected 2321일째, got {badge}"
    assert desc == "6주년, 2020-05-10"

    # 4. Future event (2026-11-19) -> D-64
    badge, desc = calculate_dday_info(date(2026, 11, 19), today)
    assert badge == "D-64", f"Expected D-64, got {badge}"
    assert "64일 남음" in desc

    print("PASS: test_dday_calculation")


def test_dday_input_parsing():
    name, d = parse_dday_input("결혼 2020-05-10")
    assert name == "결혼"
    assert d == date(2020, 5, 10)

    name, d = parse_dday_input("아기 2025.12.01")
    assert name == "아기"
    assert d == date(2025, 12, 1)

    name, d = parse_dday_input("수능 2026년 11월 19일")
    assert name == "수능"
    assert d == date(2026, 11, 19)

    # Bidirectional tests (<date> <name>)
    name, d = parse_dday_input("2026-11-19 수능")
    assert name == "수능"
    assert d == date(2026, 11, 19)

    name, d = parse_dday_input("2020-05-10 결혼")
    assert name == "결혼"
    assert d == date(2020, 5, 10)

    # Edge cases: "내일치과", quotes
    name, d = parse_dday_input("내일치과 2026-10-01")
    assert name == "내일치과"
    assert d == date(2026, 10, 1)

    name, d = parse_dday_input('2026-10-01 "내일 치과"')
    assert name == "내일 치과"
    assert d == date(2026, 10, 1)

    print("PASS: test_dday_input_parsing")


def test_schedule_input_parsing():
    # Various formats
    dt, content = parse_schedule_input("9/20 14:00 팀 회의")
    assert dt.month == 9 and dt.day == 20 and dt.hour == 14 and dt.minute == 0
    assert content == "팀 회의"

    dt, content = parse_schedule_input("9월20일 14시 30분 중간 점검")
    assert dt.month == 9 and dt.day == 20 and dt.hour == 14 and dt.minute == 30
    assert content == "중간 점검"

    dt, content = parse_schedule_input("9.20 오후 3시 회식")
    assert dt.month == 9 and dt.day == 20 and dt.hour == 15 and dt.minute == 0
    assert content == "회식"

    dt, content = parse_schedule_input("9월 20일 세미나")  # Time omitted -> 09:00
    assert dt.month == 9 and dt.day == 20 and dt.hour == 9 and dt.minute == 0
    assert content == "세미나"

    dt, content = parse_schedule_input("2026-09-25 18:00 저녁 약속")
    assert dt.year == 2026 and dt.month == 9 and dt.day == 25 and dt.hour == 18
    assert content == "저녁 약속"

    dt, content = parse_schedule_input("내일 10:00 치과")
    assert dt.hour == 10 and dt.minute == 0
    assert content == "치과"

    # Bidirectional tests
    dt, content = parse_schedule_input("팀 회의 9/20 14:00")
    assert dt.month == 9 and dt.day == 20 and dt.hour == 14 and dt.minute == 0
    assert content == "팀 회의"

    dt, content = parse_schedule_input("치과 방문 내일 10:00")
    assert dt.hour == 10 and dt.minute == 0
    assert content == "치과 방문"

    # Edge cases: "내일치과", "오늘병원"
    dt, content = parse_schedule_input("내일치과 9/20 14:00")
    assert dt.month == 9 and dt.day == 20 and dt.hour == 14 and dt.minute == 0
    assert content == "내일치과"

    dt, content = parse_schedule_input("오늘병원 내일 10:00")
    assert dt.hour == 10 and dt.minute == 0
    assert content == "오늘병원"

    # Edge case: "내일 치과" with space where numeric date 9/20 takes precedence
    dt, content = parse_schedule_input("내일 치과 9/20 14:00")
    assert dt.month == 9 and dt.day == 20 and dt.hour == 14 and dt.minute == 0
    assert content == "내일 치과"

    # Edge case: Quote protection
    dt, content = parse_schedule_input('"내일 치과" 내일 10:00')
    assert dt.hour == 10 and dt.minute == 0
    assert content == "내일 치과"

    # Time omitted bidirectional
    dt, content = parse_schedule_input("팀 회의 9/20")
    assert dt.month == 9 and dt.day == 20 and dt.hour == 9 and dt.minute == 0
    assert content == "팀 회의"

    print("PASS: test_schedule_input_parsing")


def test_anniversary_detection_and_formatting():
    today = date(2026, 9, 16)

    # 1. Past date -> automatically repeating anniversary
    assert detect_repeat_yearly("결혼", date(2020, 5, 10), today) is True

    # 2. Future date with keyword '생일' -> repeating anniversary
    assert detect_repeat_yearly("철수생일", date(2026, 10, 25), today) is True
    assert detect_repeat_yearly("어머니 생신", date(2026, 12, 1), today) is True

    # 3. Future date without keyword -> 1-time goal
    assert detect_repeat_yearly("수능", date(2026, 11, 19), today) is False
    assert detect_repeat_yearly("프로젝트 오픈", date(2026, 10, 1), today) is False

    # 4. Explicit !기념일 command -> always repeating
    assert detect_repeat_yearly("프로젝트", date(2026, 10, 1), today, is_anniversary_cmd=True) is True

    # 5. Format notification message
    # Wedding 4th anniversary
    msg = format_dday_notification("결혼", date(2020, 5, 10), repeat_yearly=True, today=date(2024, 5, 10))
    assert "4주년" in msg
    assert "1462일째" in msg

    # Suneung D-Day
    msg_suneung = format_dday_notification("수능", date(2026, 11, 19), repeat_yearly=False, today=date(2026, 11, 19))
    assert "D-Day" in msg_suneung

    print("PASS: test_anniversary_detection_and_formatting")


if __name__ == "__main__":
    test_dday_calculation()
    test_dday_input_parsing()
    test_schedule_input_parsing()
    test_anniversary_detection_and_formatting()
    print("ALL TESTS PASSED!")
