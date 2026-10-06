# RAFT Incident Agent

Vue 3 + TypeScript + FastAPI로 만든 로컬 장애 진단 앱입니다. 사용자가 상황을 입력하면 Incident를 저장하고, 빠른 분류 → RAFT 검색 → 허용된 읽기 전용 도구 → Qwen 진단을 SSE Timeline과 Inspector에 반영합니다.

## 실행

먼저 Ollama를 실행하고 로컬 양자화 모델을 받습니다. 현재 개발 환경에는 `qwen3:14b-q4_K_M`이 설치되어 있습니다.

```bash
ollama pull qwen3:14b-q4_K_M
```

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

별도 터미널에서:

```bash
cd frontend
npm install
npm run dev
```

`http://127.0.0.1:5173/diagnose`를 엽니다. `npm run build`는 Vue 타입 검사와 배포용 빌드를 수행합니다. 데이터는 기본적으로 `backend/data/raft.sqlite3`에 저장됩니다.

첫 접속 시 인증번호를 요구합니다. 초기값은 `helpdesk`이며 서버의 `ACCESS_CODE` 환경 변수로 변경합니다. 데이터, Incident, 지식, 엑셀 API는 모두 서명된 HttpOnly 쿠키가 있어야 접근할 수 있습니다. 초기값은 공개 저장소에 알려지므로 실데이터를 넣기 전에 반드시 바꾸세요.

## 현재 동작

- Quick Diagnose: 입력 후 Incident ID와 초기 진단을 바로 표시하며 SSE로 조사 결과를 갱신합니다.
- Incident Workspace: 저장된 이벤트 Timeline, 상태, 근거, 가설, 진단 Trace, Raw state를 표시합니다.
- Infrastructure: 각 읽기 전용 점검 도구의 연결 가능 여부를 표시합니다. 연결 가능 여부는 서비스 건강 상태를 뜻하지 않습니다.
- RAFT/RAG: 모든 새 질문과 진단을 지식 인덱스에 누적합니다. 사람이 확인한 원인과 성공한 조치로 해결 처리한 Incident 및 게시된 FAQ만 로컬 BM25 검색으로 Top-3을 뽑아 Qwen의 근거에 넣습니다. 외부 `RAFT_SEARCH_URL` 결과가 있으면 함께 사용합니다. 이는 검색 증강이며 모델 가중치를 재학습하지 않습니다.
- Daily Reports: 한국 시간 기준 질문·상황·제안된 조치·실제 성공한 조치를 일별로 집계합니다. 로컬 서버는 60초마다 `backend/reports/data/YYYY-MM-DD.xlsx`를 갱신합니다. Vercel에서는 Supabase의 기록을 바탕으로 다운로드 요청 시 엑셀을 생성합니다.
- FAQ Dashboard: 진단명과 영역별 반복 횟수를 표시하고 검증된 해결 사례를 FAQ로 게시합니다.
- Supabase: `supabase-violet-park` 프로젝트에 RAFT 전용 테이블을 만들었습니다. 로컬에서는 SQLite에 저장하고 변경 사항을 내구성 있는 outbox에 쌓아 서버 전용 키가 설정되면 원격에 재시도합니다. Vercel에서는 Supabase를 원본 저장소로 사용합니다.
- Jev: [TypeSafe System One](https://docs.typesafe.ai/api) Choice 질문으로 장애 영역·보조 영역·복잡도를 판단합니다. 키는 기본적으로 Git에서 제외된 `secrets/typesafe_api_key.txt`에서 읽습니다. 호출 실패 시 규칙 기반 분류를 사용하고 출처를 표시합니다.
- Qwen: 로컬 Ollama의 `qwen3:14b-q4_K_M`을 기본 모델로 사용합니다. `MEDIUM` 또는 `DEEP`에서 로컬 OpenAI 호환 API를 호출하며, 모델이 없거나 실패하면 규칙 기반 조치를 유지하고 실제 모델 판단으로 표시하지 않습니다.
- Tool: 허용 목록의 읽기 전용 POST endpoint만 호출합니다. 응답이 없으면 `unconfigured`로 남깁니다.
- Action 승인/거절은 결정만 기록합니다. 실제 시스템 변경은 실행하지 않습니다.

## 연결 설정

환경 변수는 백엔드 서버 프로세스에 지정합니다. 비밀 값은 프런트엔드에 넣지 마세요.

| 변수 | 형식 |
| --- | --- |
| `TYPESAFE_API_KEY` | Jev API 키 |
| `TYPESAFE_API_KEY_FILE` | Jev 키 파일 경로, 기본 `secrets/typesafe_api_key.txt` |
| `RAFT_SEARCH_URL` | 외부 RAFT 검색 POST URL |
| `RAFT_SEARCH_TOKEN` | 외부 검색 Bearer token, 선택 |
| `RAFT_TOOL_URLS` | 도구 이름을 URL에 매핑한 JSON 객체 |
| `RAFT_TOOL_TOKEN` | 도구 Bearer token, 선택 |
| `QWEN_BASE_URL` | OpenAI 호환 API 기본 URL, 기본 `http://127.0.0.1:11434/v1` |
| `QWEN_MODEL` | 서버의 실제 모델 ID, 기본값 `qwen3:14b-q4_K_M` |
| `QWEN_API_KEY` | Qwen Bearer token, 선택 |
| `RAFT_DB_PATH` | SQLite 파일 경로, 선택 |
| `RAFT_REPORT_DIR` | 일별 엑셀 저장 폴더, 기본 `backend/reports/data` |
| `SUPABASE_URL` | 기본 `https://opwzujhfsxqaivtbjewg.supabase.co` |
| `SUPABASE_SECRET_KEY` | 서버 전용 Supabase Secret API 키 |
| `SUPABASE_SECRET_KEY_FILE` | 기본 `secrets/supabase_secret_key.txt` |
| `ACCESS_CODE` | 초기 `helpdesk`; 운영에서는 변경 권장 |
| `ACCESS_SESSION_SECRET` | 쿠키 서명용 무작위 비밀 값, Vercel 필수 |
| `RAFT_STORAGE` | 로컬은 기본 SQLite, Vercel은 `supabase` 필수 |

Supabase Dashboard의 **Settings → API Keys**에서 Secret 키를 발급받아 `secrets/supabase_secret_key.txt`에 저장하고 파일 권한을 `600`으로 설정하세요. 키를 프런트엔드 환경 변수나 채팅에 넣지 마세요. `GET /api/v1/sync/status`로 대기 건수를, `POST /api/v1/sync/flush`로 즉시 동기화 결과를 확인할 수 있습니다. 원격 스키마는 [raft_schema.sql](supabase/raft_schema.sql)에 보관되어 있습니다.

`RAFT_SEARCH_URL`은 `{ "query": "...", "category": "DATABASE", "limit": 3 }`을 받으며 `{ "incidents": [{ "id": "INC-381", "title": "...", "summary": "..." }] }`를 반환해야 합니다.

`RAFT_TOOL_URLS` 예시는 `{"db_health":"http://127.0.0.1:9000/db/health"}`입니다. 도구 endpoint는 `{ "incident": { ... }, "tool": "db_health" }`를 받고 `{ "summary": "정상", ... }`을 반환해야 합니다. 실제 점검의 응답 구조와 권한은 운영 환경에 맞춰 연결해야 합니다.

## API

| Method | Path | 기능 |
| --- | --- | --- |
| POST | `/api/v1/diagnose` | Incident 생성과 분류 |
| GET | `/api/v1/incidents` | 목록 |
| GET | `/api/v1/incidents/{id}` | Incident |
| GET | `/api/v1/incidents/{id}/state` | 단일 상태 |
| GET | `/api/v1/incidents/{id}/events` | Timeline 기록 |
| GET | `/api/v1/incidents/{id}/stream` | SSE 이벤트 재생과 실시간 갱신 |
| PATCH | `/api/v1/incidents/{id}/status` | 운영자 상태 변경 |
| GET | `/api/v1/tools` | 도구 허용 목록 |
| POST | `/api/v1/tools/execute` | 읽기 전용 도구 수동 점검 |
| POST | `/api/v1/actions/{id}/approve` | 승인 기록 |
| POST | `/api/v1/actions/{id}/reject` | 거절 기록 |
| GET | `/api/v1/knowledge?query=...` | 검증된 사례·FAQ 검색, 지식 통계 |
| POST | `/api/v1/knowledge/faq` | 해결 사례에서 FAQ 게시 |
| GET | `/api/v1/reports/daily` | 일별 요약 목록 |
| GET | `/api/v1/reports/daily/{date}/xlsx` | 엑셀 다운로드 |
| GET | `/api/v1/sync/status` | Supabase 동기화 상태 |

## 남은 운영 연결

실제 RAFT 데이터와 DB/API/Kubernetes 점검 endpoint가 아직 제공되지 않아 해당 운영 호출을 검증하지 못했습니다. 스크린샷과 파일 첨부, 자동 조치 실행, FAISS 기반 dense 검색, 다단계 Agent Loop는 아직 구현되지 않았습니다. UI에서 첨부 버튼은 비활성화되어 있습니다.

운영 로그를 TypeSafe 또는 다른 외부 API로 보내기 전, 비밀정보 마스킹과 전송 정책을 적용하세요. 이 로컬 MVP는 `127.0.0.1` 바인딩을 전제로 합니다.

## Vercel 배포

루트 `vercel.json`은 Vue와 FastAPI를 하나의 Vercel Services 프로젝트로 빌드합니다. 클라우드에서는 로컬 SQLite와 Ollama가 지속 저장소·추론 서버로 동작하지 않으므로 Supabase와 아래 서버 환경 변수가 필요합니다. Vercel 환경은 Supabase 저장소를 자동으로 사용합니다.

| 환경 변수 | 필요성 |
| --- | --- |
| `RAFT_STORAGE=supabase` | 로컬에서 클라우드 저장소를 시험할 때 사용, Vercel에서는 자동 적용 |
| `SUPABASE_SECRET_KEY` | 기존 Supabase 프로젝트의 서버 전용 키 |
| `ACCESS_CODE` | 초기에는 `helpdesk`, 운영 전 변경 권장 |
| `ACCESS_SESSION_SECRET` | 긴 무작위 문자열, 필수 |
| `TYPESAFE_API_KEY` | Jev 분류를 사용하려면 필요 |
| `QWEN_BASE_URL`, `QWEN_MODEL`, `QWEN_API_KEY` | 클라우드에서 Qwen 추론을 원할 때만 설정. 이 컴퓨터의 Ollama는 Vercel에서 접근할 수 없음 |

서버 전용 키는 Vercel 환경 변수에만 넣고 Git에 커밋하지 않습니다. 키가 없으면 클라우드 API는 시작하지 않게 구성했습니다. 일별 엑셀은 Supabase 기록에서 요청 시 생성하므로 서버리스 파일시스템에 의존하지 않습니다. 로컬 SQLite의 기존 기록은 별도 동기화가 끝나야 클라우드에서도 보입니다.
