# 텔레그램 공지 봇 (QNAP TS-251, Docker)

채팅방(또는 1:1)별로 짧은 공지를 **키워드 형태로 저장/조회**하는 봇입니다.  
데이터는 **SQLite 파일 1개**로 저장됩니다.

## 현재 동작

- 명령어는 `/` 대신 `!` 접두사를 사용합니다.
- 그룹에서도 **관리자 제한 없이 누구나 저장/삭제**할 수 있습니다.
- 키워드 조회는 `!키워드`처럼 입력하면 됩니다.

## 명령어

| 입력 | 설명 |
|------|------|
| `!기억 키 내용...` | 공지 저장 |
| (메시지에 답장 후) `!기억 키` | 답장한 메시지 본문 저장 |
| `!키` | 저장된 공지 조회 |
| `!목록` | 현재 채팅의 키 목록 조회 |
| `!삭제 키` | 저장된 공지 삭제 |

예시:

- `!기억 회식 이번 주 금요일 7시`
- `!회식`
- `!목록`
- `!삭제 회식`

## BotFather 설정 (중요)

그룹에서 `!기억`, `!목록`, `!키워드` 같은 일반 텍스트를 받으려면  
**Privacy Mode를 꺼야** 합니다.

1. [@BotFather](https://t.me/BotFather) 열기
2. `/setprivacy`
3. 봇 선택
4. `Disable`

## 봇 생성

1. [@BotFather](https://t.me/BotFather)에서 `/newbot`으로 봇 생성
2. 발급된 토큰 복사
3. 봇을 사용할 그룹에 초대

## QNAP에서 실행 (Docker)

```bash
cd telegram_notice_bot
docker build -t telegram-notice-bot .
docker run -d --name telegram-notice-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN="YOUR_TOKEN_HERE" \
  -v /share/Container/telegram_bot_data:/data \
  telegram-notice-bot
```

- 컨테이너 내부 DB 기본 경로: `/data/notices.db`
- 필요 시 환경변수 `NOTICE_DB_PATH`로 경로를 직접 지정할 수 있습니다.

컨테이너를 수정 코드로 다시 올릴 때:

```bash
docker build -t telegram-notice-bot .
docker stop telegram-notice-bot
docker rm telegram-notice-bot
docker run -d --name telegram-notice-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN="YOUR_TOKEN_HERE" \
  -v /share/Container/telegram_bot_data:/data \
  telegram-notice-bot
```

## 로컬 테스트 (Windows)

```bash
cd telegram_notice_bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
REM .env 파일에 TELEGRAM_BOT_TOKEN 입력
python bot.py
```

기본 DB 경로는 `bot.py` 옆의 `notices.db` 입니다.

## 보안 주의사항

- `.env` 파일과 토큰은 절대 커밋하지 마세요.
- 저장된 텍스트는 입력한 그대로 전송됩니다.

## 파일 구성

- `bot.py` : 봇 로직
- `storage.py` : SQLite 저장 로직
- `requirements.txt` : 의존성 목록
- `Dockerfile` : 컨테이너 빌드 설정
- `.env.example` : 환경변수 예시
