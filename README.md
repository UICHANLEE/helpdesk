# Helpdesk RAFT — 로컬 장애 진단 앱

Vue 3 + TypeScript 화면과 FastAPI 서버를 이 컴퓨터에서 실행합니다. 질문, 상황, 진단 과정, 조치와 FAQ를 로컬 SQLite에 누적하고, 확인된 해결 사례를 다음 진단의 RAFT/RAG 근거로 검색합니다. Qwen3 14B Q4는 로컬 Ollama에서 실행합니다.

## 실행

```bash
ollama pull qwen3:14b-q4_K_M
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

다른 터미널에서:

```bash
cd frontend
npm install
npm run dev
```

`http://127.0.0.1:5173/diagnose`를 엽니다. 인증번호는 필요하지 않습니다. 백엔드는 루프백 주소에서 들어오는 요청만 허용합니다. 다른 기기에서 접속하도록 서버를 공개하지 마세요.

## 기록과 백업

- 모든 새 질문과 Incident 이벤트는 `backend/data/raft.sqlite3`에 저장됩니다. 기존 로컬 데이터는 그대로 유지됩니다.
- 사람이 근본 원인과 실제 성공한 조치를 확인해 해결 처리한 Incident와 게시된 FAQ를 다음 질문의 검색 근거로 사용합니다. 질문 기록의 누적과 모델 가중치 재학습은 별개입니다.
- 질문·상황·진단·조치·확인된 해결 결과를 한국 시간 기준 날짜별로 집계합니다. `backend/reports/data/YYYY-MM-DD.xlsx`에 업무 요약과 질문 로그 시트를 만듭니다. 화면의 **Daily Reports**에서 날짜별 확인과 다운로드가 가능합니다.
- 서버가 실행 중일 때 60초마다 SQLite의 일관된 복사본을 `backend/backups/raft-YYYY-MM-DD.sqlite3`에 갱신합니다. 이전 날짜의 백업은 보존합니다. **Daily Reports → 지금 백업**으로 즉시 복사할 수도 있습니다.
- SQLite 원본, 백업, 엑셀, 비밀키는 Git에서 제외됩니다. 컴퓨터 전체가 손상될 상황에 대비하려면 `backend/data`, `backend/backups`, `backend/reports/data`를 개인 백업 디스크에 함께 복사하세요.
- 엑셀 파일은 Google Sheets로 가져올 수 있습니다. 자동 Google Sheets 동기화는 로컬 전용 구성에 포함하지 않았습니다.

## 진단 연결

- Jev: `secrets/typesafe_api_key.txt`의 키로 TypeSafe API에 분류를 요청합니다. 이 호출에는 입력한 장애 내용이 전송됩니다. 호출 실패 시 규칙 기반 분류를 표시합니다.
- Qwen: 로컬 Ollama의 `qwen3:14b-q4_K_M`을 사용합니다. 모델을 실행할 수 없으면 규칙 기반 조치로 돌아갑니다.
- RAFT: 확인된 로컬 해결 사례와 FAQ에서 Top-3을 검색합니다. 외부 검색을 별도로 연결할 때만 `RAFT_SEARCH_URL`을 사용합니다.
- 점검 도구: `RAFT_TOOL_URLS` 환경 변수에 읽기 전용 점검 API를 등록하면 사용합니다. 미등록 도구는 실행되지 않은 것으로 표시합니다.
- 조치 승인/거절은 결정만 기록하며 실제 시스템 변경은 실행하지 않습니다.

## 주요 화면과 API

- `/diagnose`: 질문 입력과 진단
- `/incidents`: Incident 목록, 조사 과정, 확인된 해결 내용
- `/knowledge/raft`: 해결 사례·FAQ 검색
- `/faq`: 반복 오류와 FAQ 작성
- `/reports`: 일별 요약, 엑셀, 로컬 백업
- `GET /api/v1/reports/storage`: 저장소와 백업 상태
- `POST /api/v1/reports/backup`: 즉시 SQLite 백업

실제 DB/API/Kubernetes 점검 endpoint와 파일 첨부는 아직 연결되지 않았습니다. 앱 화면의 첨부 버튼은 비활성화되어 있습니다.
