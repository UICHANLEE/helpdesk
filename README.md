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
- [SMC-Helpdesk Google Sheet](https://docs.google.com/spreadsheets/d/1DxtdDGSBx5L8FbHWsd8hATeQj24_Wyfd_GG1dNuf21E/edit)에 질문 로그, 일별 요약, FAQ를 기록합니다. Codex 자동화가 매일 16:50(컴퓨터 현지 시간)에 동기화하고, **Daily Reports → 지금 업로드**로 즉시 반영할 수도 있습니다. Incident ID·날짜·FAQ ID를 각각 고유 키로 사용해 재실행해도 중복 행을 만들지 않습니다. 로컬 SQLite가 원본이며, Google Sheet는 공유·열람용 복사본입니다.
- 동기화에 사용할 행은 `.venv/bin/python -m backend.sheets.snapshot`으로 확인할 수 있습니다. 질문·상황·조치에 민감 정보가 있다면 Google Sheet 공유 설정을 확인하세요.

### 수동 업로드 연결

앱 서버에는 Codex의 Google 연결 권한이 전달되지 않습니다. 링크가 있는 사용자에게 편집 권한을 주어도 Google Sheets API는 별도 인증을 요구합니다. 이 대화에서 **지금 업로드**라고 요청하면 연결된 Google 계정으로 바로 반영할 수 있습니다. 앱 화면의 버튼을 사용하려면 별도의 Google 서비스 계정이 필요합니다.

1. Google Cloud에서 Sheets API를 활성화하고 서비스 계정의 JSON 키를 만듭니다.
2. 키 파일을 이 저장소의 `secrets/google-service-account.json`에 저장합니다. 다른 경로를 쓰려면 `RAFT_GOOGLE_SERVICE_ACCOUNT_FILE` 환경 변수를 지정합니다. `secrets/`는 Git에서 제외됩니다.
3. 대상 Sheet의 **공유**에서 JSON의 `client_email` 주소에 **편집자** 권한이 있는지 확인합니다. 앱의 Daily Reports에도 이 주소가 표시됩니다.
4. Daily Reports를 새로고침한 뒤 **지금 업로드**를 누릅니다. 버튼은 새 행만 추가하고 값이 바뀐 기존 행만 갱신하며, 업로드 후 다시 읽어 확인합니다. 질문 원문을 수식으로 실행하지 않도록 값은 `RAW`로 씁니다.

`GET /api/v1/reports/sheets/status`와 `POST /api/v1/reports/sheets/sync`가 같은 기능을 제공합니다. Google 권한이 없으면 로컬 데이터는 그대로 남습니다.

## 현재 RAG 저장소

- SQLite의 `incidents`에 원본 질문과 상태, `events`에 조사 흐름, `knowledge`에 질문·상황·진단·조치의 검색용 복사본, `faq`에 게시된 답변을 저장합니다.
- 검색 시 `knowledge` 중 **운영자가 해결을 확인한 행**과 게시된 FAQ를 모아 BM25 점수를 그때 계산합니다. 한국어는 연속된 두 글자 단위도 색인합니다. Top-3이 Qwen 판단 문맥으로 들어갑니다.
- 현재는 임베딩 벡터, 영속적인 벡터 인덱스, FAISS 또는 pgvector가 없습니다. 따라서 'VDB'라기보다 **SQLite 원본 + 즉석 BM25 검색**입니다. 미해결 질문은 기록·빈발 오류 집계에는 남지만 검증된 답변으로 검색되지는 않습니다.

## 진단 연결

- Jev: `secrets/typesafe_api_key.txt`의 키로 TypeSafe API에 분류를 요청합니다. 이 호출에는 입력한 장애 내용이 전송됩니다. 호출 실패 시 규칙 기반 분류를 표시합니다.
- Qwen: 로컬 Ollama의 `qwen3:14b-q4_K_M`을 사용합니다. 모델을 실행할 수 없으면 규칙 기반 조치로 돌아갑니다.
- RAFT: 확인된 로컬 해결 사례와 FAQ에서 Top-3을 검색합니다. 외부 검색을 별도로 연결할 때만 `RAFT_SEARCH_URL`을 사용합니다.
- 점검 도구: `RAFT_TOOL_URLS` 환경 변수에 읽기 전용 점검 API를 등록하면 사용합니다. 미등록 도구는 실행되지 않은 것으로 표시합니다.
- 조치 승인/거절은 결정만 기록하며 실제 시스템 변경은 실행하지 않습니다.

## 진단 Trace와 근거

- 새 Incident에는 `TR-<Incident ID>` 형식의 Trace ID가 붙습니다. Jev 분류, RAFT 검색, 읽기 전용 Tool, Qwen 판단의 이벤트에 단계 ID·상태·소요 시간을 기록합니다. 오류 이벤트에는 실패한 단계가 남습니다.
- Incident 화면의 **Evidence** 탭은 진단 주장과 참고한 검색·점검 이벤트를 연결합니다. 자동 진단은 **미검증**으로 표시하고, 운영자가 원인과 실제 성공한 조치를 기록한 경우에만 별도의 **운영자 확인** 주장을 만듭니다. 유사 사례나 점검 결과를 원인의 자동 입증으로 취급하지 않습니다.
- `GET /api/v1/incidents/{incident_id}/trace`와 `GET /api/v1/traces/{trace_id}`는 저장된 이벤트를 Trace → Span → Evidence → Claim 그래프로 보여주고 Tool 실패·미연결 개수와 가장 느린 단계를 계산합니다. 상단 검색에서 Trace ID를 입력하면 해당 Incident로 이동합니다. 기존 Incident는 원래 이벤트를 보존하며, 새 Trace 연결이 없는 부분은 채워 넣지 않습니다.
- 현재 Qwen 연결은 전체 판단 시간과 모델명을 기록합니다. 토큰 수·TTFT·모델 세부 버전, RAFT 문서 버전, 재시도·루프 수는 원천 응답에서 얻을 수 있을 때 추가해야 합니다. 값이 없으면 추정해서 기록하지 않습니다.

## 주요 화면과 API

- `/diagnose`: 질문 입력과 진단
- `/incidents`: Incident 목록, 조사 과정, 확인된 해결 내용
- `/knowledge/raft`: 해결 사례·FAQ 검색
- `/faq`: 반복 오류와 FAQ 작성
- `/reports`: 일별 요약, 엑셀, 로컬 백업
- `GET /api/v1/reports/storage`: 저장소와 백업 상태
- `POST /api/v1/reports/backup`: 즉시 SQLite 백업

실제 DB/API/Kubernetes 점검 endpoint와 파일 첨부는 아직 연결되지 않았습니다. 앱 화면의 첨부 버튼은 비활성화되어 있습니다.
