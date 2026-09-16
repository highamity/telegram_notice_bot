"""
Date and time parsing utilities for telegram notice_bot.
Supports various Korean date/time formats, relative dates (오늘/내일/모레),
omitted years, and omitted times.
All calculations are based on KST (Asia/Seoul).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


class DateParseError(Exception):
    """Raised when date/time cannot be parsed."""
    pass


def get_now_kst() -> datetime:
    """Return current datetime in KST."""
    return datetime.now(KST)


def parse_schedule_input(raw_text: str) -> tuple[datetime, str]:
    """
    Parse text from '!일정 <date/time...> <content...>'.
    Returns (remind_at_kst, content).
    Raises DateParseError with a user-friendly message on error.
    """
    text = (raw_text or "").strip()
    if not text:
        raise DateParseError("일정의 날짜와 내용을 입력해주세요. (예: !일정 9/20 14:00 회의)")

    now = get_now_kst()
    today = now.date()

    tokens = text.split()
    if not tokens:
        raise DateParseError("일정 내용을 입력해주세요.")

    # We will try to match date and optional time from the beginning of tokens
    # First token could be relative date: 오늘, 내일, 모레
    target_date: date | None = None
    tokens_consumed = 0

    first = tokens[0]
    if first == "오늘":
        target_date = today
        tokens_consumed = 1
    elif first == "내일":
        target_date = today + timedelta(days=1)
        tokens_consumed = 1
    elif first == "모레":
        target_date = today + timedelta(days=2)
        tokens_consumed = 1

    if target_date is None:
        # Try matching date pattern from the first 1 or 2 tokens (e.g. "9월" "20일" or "2026년" "9월" "20일")
        # Combine first 1~3 tokens to test
        for n_tok in (3, 2, 1):
            if len(tokens) >= n_tok:
                candidate = " ".join(tokens[:n_tok])
                d = _match_date_pattern(candidate, now)
                if d is not None:
                    target_date = d
                    tokens_consumed = n_tok
                    break

    if target_date is None:
        raise DateParseError(
            "날짜를 인식하지 못했습니다.\n"
            "지원 형식 예시:\n"
            "• 9/20, 9.20, 9월20일\n"
            "• 2026-09-20, 2026.09.20\n"
            "• 오늘, 내일, 모레"
        )

    remaining_tokens = tokens[tokens_consumed:]
    if not remaining_tokens:
        raise DateParseError("일정 내용을 입력해주세요. (예: !일정 9/20 회의)")

    # Now check for optional time in remaining_tokens
    target_time: time | None = None
    time_tokens_consumed = 0

    for n_tok in (2, 1):
        if len(remaining_tokens) >= n_tok:
            candidate = " ".join(remaining_tokens[:n_tok])
            t = _match_time_pattern(candidate)
            if t is not None:
                target_time = t
                time_tokens_consumed = n_tok
                break

    if target_time is not None:
        content_tokens = remaining_tokens[time_tokens_consumed:]
    else:
        # Time omitted: default to 09:00
        content_tokens = remaining_tokens
        default_hour, default_minute = 9, 0
        target_time = time(default_hour, default_minute)

    content = " ".join(content_tokens).strip()
    if not content:
        raise DateParseError("일정 내용을 입력해주세요.")

    remind_dt = datetime.combine(target_date, target_time, tzinfo=KST)

    # Check if remind_dt is in the past
    if remind_dt <= now:
        if target_date == today and time_tokens_consumed == 0:
            raise DateParseError(
                "오늘 오전 9시가 이미 지났으므로 시간을 함께 입력해주세요.\n"
                f"예: !일정 오늘 {now.hour + 1}:00 {content}"
            )
        raise DateParseError(
            f"입력한 시각({remind_dt.strftime('%Y-%m-%d %H:%M')})이 이미 지난 시각입니다."
        )

    return remind_dt, content


def parse_dday_input(raw_text: str) -> tuple[str, date]:
    """
    Parse text from '!디데이 <name> <date...>'.
    Returns (name, target_date).
    """
    parts = (raw_text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        raise DateParseError("사용법: !디데이 <이름> <날짜>\n예: !디데이 수능 2026-11-19\n예: !디데이 결혼 2020-05-10")

    name = parts[0].strip()
    date_str = parts[1].strip()

    now = get_now_kst()
    today = now.date()

    # Relative dates
    if date_str == "오늘":
        return name, today
    if date_str == "내일":
        return name, today + timedelta(days=1)
    if date_str == "어제":
        return name, today - timedelta(days=1)

    target_date = _match_date_pattern(date_str, now, allow_past_year_inference=True)
    if target_date is None:
        raise DateParseError(
            "날짜를 인식하지 못했습니다.\n"
            "예: 2020-05-10, 2026.11.19, 9/20, 9월 20일"
        )

    return name, target_date


ANNIVERSARY_KEYWORDS = ("생일", "생신", "결혼", "기념일", "주년", "돌", "백일")


def detect_repeat_yearly(
    name: str,
    target_date: date,
    today: date | None = None,
    is_anniversary_cmd: bool = False,
) -> bool:
    """
    Determine if this dday should repeat yearly:
    1. If registered via !기념일 -> True
    2. If target date is in the past -> True (e.g. wedding 2020-05-10)
    3. If name contains anniversary keywords (생일, 생신, 결혼, 기념일, 주년 등) -> True
    4. Otherwise (e.g. 수능 2026-11-19) -> False (1-time goal)
    """
    if is_anniversary_cmd:
        return True

    if today is None:
        today = get_now_kst().date()

    if target_date < today:
        return True

    clean_name = name.lower()
    for kw in ANNIVERSARY_KEYWORDS:
        if kw in clean_name:
            return True

    return False


def format_dday_notification(
    name: str,
    target_date: date,
    repeat_yearly: bool,
    today: date | None = None,
) -> str:
    """Format notification message when a D-Day or Anniversary is due."""
    if today is None:
        today = get_now_kst().date()

    if repeat_yearly:
        years = today.year - target_date.year
        elapsed_days = (today - target_date).days + 1
        if years > 0:
            return f"🎉 [기념일 알림]\n오늘은 '{name}' {years}주년입니다! ({elapsed_days}일째)"
        elif target_date == today:
            return f"🎉 [기념일 알림]\n오늘은 '{name}' 당일입니다! (1일째)"
        else:
            return f"🎉 [기념일 알림]\n오늘은 '{name}'입니다!"
    else:
        return f"⏰ [디데이 알림]\n오늘은 '{name}' D-Day입니다!"


def calculate_dday_info(
    target_date: date,
    today: date | None = None,
    repeat_yearly: bool = False,
) -> tuple[str, str]:
    """
    Calculate D-Day or Anniversary string according to Korean conventions.
    - Future: D-N (N일 남음)
    - Today: D-Day (오늘!)
    - Past: N일째 (D+M) where Day 1 = start date.
    Returns (short_badge, description).
    """
    if today is None:
        today = get_now_kst().date()

    if target_date > today:
        diff = (target_date - today).days
        return f"D-{diff}", f"{diff}일 남음"
    elif target_date == today:
        return "D-Day", "오늘!"
    else:
        # Past: Day 1 is the target_date itself
        elapsed_days = (today - target_date).days + 1
        years = today.year - target_date.year
        date_str = target_date.strftime("%Y-%m-%d")
        if repeat_yearly and years > 0:
            desc = f"{years}주년, {date_str}"
        else:
            desc = date_str
        return f"{elapsed_days}일째", desc



def _match_date_pattern(text: str, now: datetime, allow_past_year_inference: bool = False) -> date | None:
    """Try various date regexes."""
    s = text.strip()

    # Pattern 1: YYYY[-./년\s]+M[-./월\s]+D일?
    m = re.match(r"^(\d{4})[-./년\s]+(\d{1,2})[-./월\s]+(\d{1,2})일?$", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    # Pattern 2: M[-./월\s]+D일? (Year omitted)
    m = re.match(r"^(\d{1,2})[-./월\s]+(\d{1,2})일?$", s)
    if m:
        try:
            month = int(m.group(1))
            day = int(m.group(2))
            year = now.year
            d = date(year, month, day)
            # For schedule: if already passed this year, roll over to next year
            if not allow_past_year_inference and d < now.date():
                d = date(year + 1, month, day)
            return d
        except ValueError:
            return None

    return None


def _match_time_pattern(text: str) -> time | None:
    """Try various time regexes."""
    s = text.strip()

    # Pattern 1: HH:MM
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        try:
            h, minute = int(m.group(1)), int(m.group(2))
            if 0 <= h <= 23 and 0 <= minute <= 59:
                return time(h, minute)
        except ValueError:
            pass

    # Pattern 2: (오전|오후)? H시 (M분)? or (오전|오후) H:M
    m = re.match(r"^(오전|오후)?\s*(\d{1,2})(?:시(?:\s*(\d{1,2})분?)?|:(\d{2}))?$", s)
    if m:
        period = m.group(1)
        raw_h = int(m.group(2))
        minute_str = m.group(3) or m.group(4)
        minute = int(minute_str) if minute_str else 0

        if not (0 <= minute <= 59):
            return None

        h = raw_h
        if period == "오후":
            if h < 12:
                h += 12
        elif period == "오전":
            if h == 12:
                h = 0

        if 0 <= h <= 23:
            return time(h, minute)

    return None
