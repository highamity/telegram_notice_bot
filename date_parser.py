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


def _tokenize(text: str) -> list[str]:
    """Split text into tokens while keeping quoted strings together."""
    pattern = r'"([^"]*)"|\'([^\']*)\'|(\S+)'
    tokens = []
    for m in re.finditer(pattern, text.strip()):
        d_q, s_q, word = m.groups()
        if d_q is not None:
            tokens.append(f'"{d_q}"')
        elif s_q is not None:
            tokens.append(f"'{s_q}'")
        elif word:
            tokens.append(word)
    return tokens


def _is_quoted(tok: str) -> bool:
    return len(tok) >= 2 and (
        (tok.startswith('"') and tok.endswith('"'))
        or (tok.startswith("'") and tok.endswith("'"))
    )


def _clean_token(tok: str) -> str:
    if _is_quoted(tok):
        return tok[1:-1]
    return tok


def _join_tokens(tokens: list[str]) -> str:
    return " ".join(_clean_token(t) for t in tokens).strip()


def _match_relative_date(text: str, today: date) -> date | None:
    if _is_quoted(text):
        return None
    s = text.strip()
    if s == "오늘":
        return today
    if s == "내일":
        return today + timedelta(days=1)
    if s == "모레":
        return today + timedelta(days=2)
    if s == "어제":
        return today - timedelta(days=1)
    return None


class _DateTimeCandidate:
    def __init__(
        self,
        target_date: date,
        target_time: time | None,
        is_numeric_date: bool,
        tokens_consumed: int,
        from_front: bool,
    ):
        self.target_date = target_date
        self.target_time = target_time
        self.is_numeric_date = is_numeric_date
        self.tokens_consumed = tokens_consumed
        self.from_front = from_front


def _try_extract_from_front(tokens: list[str], now: datetime, today: date) -> _DateTimeCandidate | None:
    if not tokens:
        return None

    # Check relative date first (1 token)
    rel_d = _match_relative_date(tokens[0], today)
    if rel_d is not None:
        target_date = rel_d
        is_numeric = False
        date_len = 1
    else:
        target_date = None
        is_numeric = True
        date_len = 0
        for n_tok in (3, 2, 1):
            if len(tokens) >= n_tok:
                candidate = " ".join(tokens[:n_tok])
                d = _match_date_pattern(candidate, now)
                if d is not None:
                    target_date = d
                    date_len = n_tok
                    break
        if target_date is None:
            return None

    remaining = tokens[date_len:]
    target_time = None
    time_len = 0
    for n_tok in (3, 2, 1):
        if len(remaining) >= n_tok:
            candidate = " ".join(remaining[:n_tok])
            t = _match_time_pattern(candidate)
            if t is not None:
                target_time = t
                time_len = n_tok
                break

    return _DateTimeCandidate(
        target_date=target_date,
        target_time=target_time,
        is_numeric_date=is_numeric,
        tokens_consumed=date_len + time_len,
        from_front=True,
    )


def _try_extract_from_back(tokens: list[str], now: datetime, today: date) -> _DateTimeCandidate | None:
    if not tokens:
        return None

    max_len = min(len(tokens), 6)
    best_candidate: _DateTimeCandidate | None = None

    for total_len in range(1, max_len + 1):
        suffix = tokens[-total_len:]

        # Case 1: [Date] [Time]
        for split_idx in range(1, total_len):
            d_tokens = suffix[:split_idx]
            t_tokens = suffix[split_idx:]

            d_str = " ".join(d_tokens)
            t_str = " ".join(t_tokens)

            rel_d = _match_relative_date(d_str, today)
            if rel_d is not None:
                d = rel_d
                is_num = False
            else:
                d = _match_date_pattern(d_str, now)
                is_num = True

            t = _match_time_pattern(t_str)

            if d is not None and t is not None:
                cand = _DateTimeCandidate(
                    target_date=d,
                    target_time=t,
                    is_numeric_date=is_num,
                    tokens_consumed=total_len,
                    from_front=False,
                )
                if best_candidate is None or (cand.is_numeric_date and not best_candidate.is_numeric_date):
                    best_candidate = cand

        # Case 2: Only [Date] (no time)
        d_str = " ".join(suffix)
        rel_d = _match_relative_date(d_str, today)
        if rel_d is not None:
            d = rel_d
            is_num = False
        else:
            d = _match_date_pattern(d_str, now)
            is_num = True

        if d is not None and best_candidate is None:
            best_candidate = _DateTimeCandidate(
                target_date=d,
                target_time=None,
                is_numeric_date=is_num,
                tokens_consumed=total_len,
                from_front=False,
            )

    return best_candidate


def parse_schedule_input(raw_text: str) -> tuple[datetime, str]:
    """
    Parse text from '!일정 <date/time...> <content...>' or '!일정 <content...> <date/time...>'.
    Returns (remind_at_kst, content).
    Raises DateParseError with a user-friendly message on error.
    """
    text = (raw_text or "").strip()
    if not text:
        raise DateParseError("일정의 날짜와 내용을 입력해주세요. (예: !일정 9/20 14:00 회의 또는 !일정 회의 9/20 14:00)")

    now = get_now_kst()
    today = now.date()

    tokens = _tokenize(text)
    if not tokens:
        raise DateParseError("일정 내용을 입력해주세요.")

    cand_front = _try_extract_from_front(tokens, now, today)
    cand_back = _try_extract_from_back(tokens, now, today)

    front_valid = cand_front is not None and cand_front.tokens_consumed < len(tokens)
    back_valid = cand_back is not None and cand_back.tokens_consumed < len(tokens)

    if not front_valid and not back_valid:
        raise DateParseError(
            "날짜 또는 내용을 인식하지 못했습니다.\n"
            "지원 형식 예시:\n"
            "• !일정 9/20 14:00 팀 회의 (또는 !일정 팀 회의 9/20 14:00)\n"
            "• !일정 내일 10:00 치과 (또는 !일정 치과 내일 10:00)\n"
            "• !일정 2026-09-20 세미나"
        )

    chosen: _DateTimeCandidate
    if front_valid and not back_valid:
        chosen = cand_front
    elif back_valid and not front_valid:
        chosen = cand_back
    else:
        # Both valid: apply smart precedence
        # 1. Exact numeric date beats relative date (e.g. "내일 치과 9/20 14:00")
        if cand_back.is_numeric_date and not cand_front.is_numeric_date:
            chosen = cand_back
        elif cand_front.is_numeric_date and not cand_back.is_numeric_date:
            chosen = cand_front
        # 2. Explicit time beats omitted time
        elif cand_back.target_time is not None and cand_front.target_time is None:
            chosen = cand_back
        elif cand_front.target_time is not None and cand_back.target_time is None:
            chosen = cand_front
        else:
            chosen = cand_front

    if chosen.from_front:
        content_tokens = tokens[chosen.tokens_consumed:]
    else:
        content_tokens = tokens[:-chosen.tokens_consumed]

    content = _join_tokens(content_tokens)
    if not content:
        raise DateParseError("일정 내용을 입력해주세요.")

    target_date = chosen.target_date
    if chosen.target_time is not None:
        target_time = chosen.target_time
        time_specified = True
    else:
        target_time = time(9, 0)
        time_specified = False

    remind_dt = datetime.combine(target_date, target_time, tzinfo=KST)

    # Check if remind_dt is in the past
    if remind_dt <= now:
        if target_date == today and not time_specified:
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
    Parse text from '!디데이 <name> <date>' or '!디데이 <date> <name>'.
    Returns (name, target_date).
    """
    tokens = _tokenize(raw_text)
    if len(tokens) < 2:
        raise DateParseError(
            "사용법: !디데이 <이름> <날짜> (또는 !디데이 <날짜> <이름>)\n"
            "예: !디데이 수능 2026-11-19 (또는 !디데이 2026-11-19 수능)\n"
            "예: !디데이 결혼 2020-05-10 (또는 !디데이 2020-05-10 결혼)"
        )

    now = get_now_kst()
    today = now.date()

    # Try matching date at front (lengths 3, 2, 1)
    front_date = None
    front_len = 0
    front_is_numeric = False
    for k in (3, 2, 1):
        if len(tokens) > k:
            sub = " ".join(tokens[:k])
            rel = _match_relative_date(sub, today)
            if rel is not None:
                front_date = rel
                front_len = k
                front_is_numeric = False
                break
            d = _match_date_pattern(sub, now, allow_past_year_inference=True)
            if d is not None:
                front_date = d
                front_len = k
                front_is_numeric = True
                break

    # Try matching date at back (lengths 3, 2, 1)
    back_date = None
    back_len = 0
    back_is_numeric = False
    for k in (3, 2, 1):
        if len(tokens) > k:
            sub = " ".join(tokens[-k:])
            rel = _match_relative_date(sub, today)
            if rel is not None:
                back_date = rel
                back_len = k
                back_is_numeric = False
                break
            d = _match_date_pattern(sub, now, allow_past_year_inference=True)
            if d is not None:
                back_date = d
                back_len = k
                back_is_numeric = True
                break

    if front_date is not None and back_date is not None:
        if back_is_numeric and not front_is_numeric:
            name = _join_tokens(tokens[:-back_len])
            target_date = back_date
        elif front_is_numeric and not back_is_numeric:
            name = _join_tokens(tokens[front_len:])
            target_date = front_date
        else:
            # Default: name at front, date at back
            name = _join_tokens(tokens[:-back_len])
            target_date = back_date
    elif front_date is not None:
        name = _join_tokens(tokens[front_len:])
        target_date = front_date
    elif back_date is not None:
        name = _join_tokens(tokens[:-back_len])
        target_date = back_date
    else:
        raise DateParseError(
            "날짜를 인식하지 못했습니다.\n"
            "예: !디데이 수능 2026-11-19 (또는 !디데이 2026-11-19 수능)\n"
            "예: !디데이 결혼 2020-05-10"
        )

    if not name:
        raise DateParseError("디데이/기념일 이름을 입력해주세요.")

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
