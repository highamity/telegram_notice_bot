# Telegram Notice Bot 작업 안내

## 프로젝트 개요

텔레그램 채팅별 공지 메모를 키-값으로 저장하는 작은 Python 봇이다. 사용자는 일반 텍스트 `!` 명령으로 공지를 저장, 조회, 목록 확인, 삭제한다. 데이터는 SQLite 한 파일에 영속화되며 QNAP을 포함한 Docker 환경에서 실행하는 것이 주요 배포 방식이다.

## 구성과 실행 흐름

- `bot.py`: 애플리케이션 진입점이다. `.env`를 읽고 `TELEGRAM_BOT_TOKEN`을 검증한 뒤 `python-telegram-bot`의 polling 앱을 시작한다. `!`로 시작하는 텍스트를 처리하며, 백그라운드 태스크 `reminder_worker`를 가동해 도래한 일정을 자동 발송한다.
- `storage.py`: `NoticeStore`를 제공한다. `notices`, `schedules`, `ddays` 테이블을 관리한다. SQLite 작업은 스레드 락으로 보호하고 `asyncio.to_thread()`로 비동기 핸들러에서 호출한다.
- `date_parser.py`: 다양한 날짜/시간 포맷(`9/20`, `9월20일`, `2026-09-20`, `오늘/내일`) 파싱, 연도/시간 생략 처리(KST 기준) 및 디데이/경과일(당일=1일) 계산을 담당한다.
- `Dockerfile`: Python 3.12 slim 이미지에서 앱을 실행한다. 컨테이너 기본 DB 위치는 `/data/notices.db`다.
- `.env.example`: 필요한 `TELEGRAM_BOT_TOKEN`과 선택적인 `NOTICE_DB_PATH` 예시다.
- `README.md`: 사용자 명령, BotFather Privacy Mode 설정, 로컬 실행과 Docker 배포 절차의 기준 문서다.

메시지 처리 순서는 `bot.py`의 `on_bang_message()`가 담당한다. `!기억`은 저장, `!목록`은 키 목록, `!삭제`는 삭제, `!일정`은 일정 등록/조회, `!일정삭제`는 일정 삭제, `!디데이` 및 `!기념일`은 디데이/기념일 등록/목록, `!디데이삭제` 및 `!기념일삭제`는 삭제로 분기하고, 나머지 `!키`는 공지 또는 디데이를 조회한다. 저장과 조회는 항상 `chat.id`를 포함하므로 채팅 간 데이터가 공유되면 안 된다.

## 개발 규칙

- 사용자에게 보이는 명령과 안내 문구는 한국어 사용 흐름을 유지하고, 변경 시 `README.md`의 명령 표와 예시도 함께 갱신한다.
- `!기억`의 인라인 저장 및 답장 저장 동작, 여러 줄 본문, `!키` 조회, `!목록`, `!삭제`, `!일정`, `!디데이`, `!기념일`을 깨지 않도록 한다.
- 디데이/기념일 계산 시 과거 날짜는 시작 당일을 1일로 계산한다.
- 매년 반복 기념일은 과거일, 키워드(생일, 생신, 결혼, 기념일, 주년 등), 또는 `!기념일` 명령어로 자동 판별하여 매년 해당 날짜 오전 09:00 KST에 자동 알림을 발송한다.
- 텔레그램 메시지는 최대 길이를 넘을 수 있으므로 긴 공지 응답은 `_reply_long()`을 통해 나눠 전송한다.
- DB 스키마 또는 쿼리를 바꿀 때에는 기존 `notices.db`가 있는 배포를 고려한다. 채팅 범위(`chat_id`)와 `(chat_id, key)` 고유성은 유지한다.
- 동기 SQLite 호출을 텔레그램의 async 핸들러에서 직접 실행하지 않는다. `NoticeStore`의 락 및 `asyncio.to_thread()` 패턴을 유지한다.
- `.env`, 봇 토큰, `*.db` 파일은 절대 커밋하거나 로그에 노출하지 않는다. `.env.example`에는 값이 아닌 형식만 둔다.
- 의존성을 추가하거나 버전 제약을 바꾸면 `requirements.txt`와 Docker 빌드가 함께 작동하는지 확인한다.

## 검증

Python 코드 변경 후 최소한 아래를 실행한다.

```powershell
python -m py_compile bot.py storage.py date_parser.py
python test_date_parser.py
python test_storage.py
python test_bot_handlers.py
python test_chat_isolation.py
```

봇 동작을 수동 확인할 때는 `.env.example`을 `.env`로 복사해 실제 토큰을 로컬에만 설정하고 `python bot.py`를 실행한다. 실제 토큰을 공유하거나 커밋하지 않는다.

Docker 관련 변경 후에는 다음 빌드로 Dockerfile과 의존성 설치를 확인한다.

```powershell
docker build -t telegram-notice-bot .
```
