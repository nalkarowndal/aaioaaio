# P0–P4 구현·회귀 QA 상태 (2026-11-12)

## 소스 출처 및 주의사항

- GitHub `nalkarowndal/aaioaaio` 최초 확인 시 빈 저장소(main 설정만 있고 commit/PR 없음)였으므로 기존 PR을 병합할 수 없었습니다.
- 접근 가능한 `ais.zip`의 2026-11-10 소스와 기존 P0 통합 키트를 기반으로 복원한 **대체 작업본**입니다. 사용자가 이전에 검토한 최신 `aaiai(1).zip`의 실제 바이트는 접근할 수 없어 완전 동일성을 검증할 수 없습니다.
- 서비스 프레임워크 Streamlit + Python + Groq OpenAI-compatible API 및 다크 오로라·보라/시안 팔레트를 유지했습니다.
- 원본 ZIP의 `.streamlit/secrets.toml`과 각종 IDE/캐시 파일을 복사하거나 Git에 기록하지 않았습니다. 과거에 키가 공유 ZIP에 있었을 수 있으니 키는 소유자가 교체해야 합니다.

## 단계별 기록

| 단계 | 실제 구현 | 검증 상태 |
|---|---|---|
| P0 Markdown 파서·표 | 직접 HTML 조립을 제거하고 `st.markdown(unsafe_allow_html=False)`로 출력, 제목/표/코드 스크롤 CSS | 정적 검사/단위 테스트 완료; 브라우저 BLOCKED |
| P1 모바일·스크롤 | 자동 부모 window 스크롤 제거, Streamlit chat input, 375/768px 미디어 쿼리, 줄바꿈/안전영역 | CSS 파싱 완료; 브라우저 BLOCKED |
| P2 첨부·설정 | 최대 8개/10MB 파일, 내용 해시·개별 제거, DOCX 순서, PDF/텍스트 추출, 이미지 정규화, sidebar 설정 | 파일 파서 단위 테스트 완료; 위젯 실사용 BLOCKED |
| P3 시각·CSS | 기존 다크 유리·그라데이션 컬러 유지, 레거시 고정 도크 규칙 제거, CSS 정리, 포커스 표시 | CSS 파싱 완료; 시각 평가 BLOCKED |
| P4 기능·시각 회귀 | `pytest`·구문 검증·Playwright 4개 뷰포트 스크립트 준비 | 단위 PASS; 실제 Playwright 브라우저 BLOCKED |

## 확인 명령

```bash
python -m pytest -q
python -m compileall -q app.py core scripts
python -m streamlit run app.py
# 별도 터미널에서
python scripts/visual_qa.py --url http://localhost:8501
# Markdown 전용 검사
python -m streamlit run scripts/markdown_fixture.py
python scripts/visual_qa.py --fixture
```

### 실측/미실측 구분

- 단위 테스트: 21개 통과 (현재 로컬 환경에서 실행됨).
- `compileall`과 `tinycss2` CSS 파싱: 정적 PASS.
- 현재 실행 환경에는 Streamlit 패키지가 설치되지 않아 실앱 실행 불가.
- Playwright Python 패키지와 시스템 Chromium은 발견되지만 실제 Streamlit 프런트엔드에 연결할 수 없으므로 스크린샷/실화면 PASS 판정하지 않음.
- Groq API 키 없음: 인증/모델 응답/스트리밍/비전 실제 API는 검증하지 않음.
- PASS는 재현 가능한 실행 로그 또는 브라우저 증거가 나와야만 갱신.

## 기능 제한/향후 보완

- 본 작업본은 최신 `aaiai(1).zip`을 병합한 것이 아닙니다. **최신 소스와 차이 비교가 필수**입니다.
- 문서 분석용 텍스트는 파일당 최대 12,000자만 전달합니다. 전체 문서 분석 완료라는 문구는 표시하지 않습니다.
- 여러 이미지는 선택한 모델이 실제 지원해야 합니다. VLM 모델은 사용자가 직접 지원되는 ID를 지정해야 합니다.
- API 에러 원문(비밀키/HTTP 본문 등)을 UI나 로그에 노출하지 않습니다.
- 브라우저 패스와 API 실제 검증을 통과하기 전 배포 완료 상태로 표시하지 않습니다.