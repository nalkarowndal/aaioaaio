# AI Studio · P0–P4 구현 및 QA 보고서

작성일: 2026-11-12 (Asia/Seoul)

## 소스/병합 출처

- 대상: `https://github.com/nalkarowndal/aaioaaio`의 `main`.
- 최초 확인 당시 저장소가 비어 있었고 기존 PR·브랜치·커밋이 없어 PR 병합 대신 최초 커밋 후 안전한 초기 복원 작업본을 순차 커밋했습니다.
- 원본은 접근 가능한 `ais.zip`의 Streamlit UI/팔레트와 사전 작성된 P0 키트를 기준으로 재구성했습니다. **최신 `aaiai(1).zip` 원본 바이트는 접근 불가능했으므로 최신 로컬 코드와 동일한 프로젝트라는 보장은 없습니다.** 소스 차이 비교는 별도 과제로 남습니다.
- 비밀정보가 포함될 수 있는 기존 `.streamlit/secrets.toml`, `.env` 및 IDE/캐시·녹화물은 저장소에 복사하지 않았습니다. 과거 ZIP에 포함됐던 키는 소유자가 회전(폐기/재발급)해야 합니다.

## 구현 및 검증 결과

| 단계 | 구현 내용 | 검증 결과 |
| --- | --- | --- |
| P0 콘텐츠 렌더링 | 정규식 기반 HTML 응답을 `st.markdown(unsafe_allow_html=False)`로 대체. H1–H3, 코드, 중첩 목록, 링크, 긴 표와 가로 스크롤 | 단위 PASS + Streamlit 브라우저 PASS |
| P1 모바일/스크롤 | 강제 `window.parent` 스크롤 제거. 기본 chat input 사용. 375/768px 헤더, 제목 줄바꿈, 하단 입력 가시성, safe-area 규칙 | 네 뷰포트의 브라우저 자동 검사 PASS |
| P2 첨부/설정 | 다중 파일 첨부 최대 8개, 파일당 10MB, 해시 기반 중복 식별, 개별 제거, 상태 표시, DOCX 문단·표 순서, PDF/텍스트, RGBA/WebP 이미지 정규화, 사이드바 설정 | 파서 단위 PASS + 두 파일 첨부/메시지 전송 브라우저 PASS |
| P3 시각/CSS | 기존 오로라 다크 + 보라·시안 팔레트 유지, Streamlit 개발자 `Deploy` 메뉴 숨김, AI/사용자 말풍선 구별 및 정렬, CSS 정리, 포커스 접근성 표시 | 375px 및 1280px 캡처 검토 + 자동 검사 PASS |
| P4 회귀 검증 | `pytest`, Python compileall, 브라우저 375×812 / 768×1024 / 1280×800 / 1920×1080, Markdown 샘플과 파일/입력 UI 검증 | 현재 작업본 브라우저 및 단위 자동 회귀 PASS, 외부 연동/실기기 확인 미완료 |

## 재현 가능한 근거

- 로컬: `python -m pytest -q` → **25 passed**.
- 로컬: `python -m compileall -q app.py core scripts` → 정상 종료.
- 로컬: `tinycss2`로 CSS 문법 오류 0건 확인.
- GitHub Actions: **run 43132552327 — success**, HEAD `006396840dade5a02b5c10b3ff02b9cae12e76f5`.
  - URL: https://github.com/nalkarowndal/aaioaaio/actions/runs/43132552327
  - 단계: Install runtime → Unit tests and syntax → Markdown fixture browser QA → Main application browser QA → Upload screenshots → 모든 단계 `success`.
  - 보관 증거: `ai-studio-visual-qa` GitHub Actions artifact (fixture/app, 네 뷰포트 및 상호작용 캡처).
  - 검증 스크립트는 헤더 노출, 기본 개발용 Deploy 버튼 미노출, 전체 페이지 가로 넘침 부재, 표 내부 가로 스크롤, H1–H3, 코드 블록, 채팅 입력창, 파일 2개 동시 선택, 사용자 메시지 제출, 사용자 말풍선의 보라색 그라데이션을 검사합니다.
- 눈으로 확인한 실측 이미지: 375×812 초기 화면 및 1280×800 파일 첨부·메시지 전송 후 화면. 원본 서비스의 화면이 아닌 이 저장소에 반영한 복원 작업본의 실제 Chromium 캡처입니다.
- 마지막 GitHub main 소스 변경 HEAD와 위 QA 실행 HEAD가 일치합니다. 본 문서 및 의존성 설정의 후속 정리 커밋은 QA 실행 결과를 무효화하지 않는 내용만 포함해야 합니다.

## 제한/미완료 (PASS와 구분)

- Groq 실서비스 API 키로 인증·모델 결과·모델별 비전 요청을 실측하지 않았습니다. API 미설정 시 **가짜 AI 답변을 생성하지 않고** 오류 상태를 표시합니다.
- Windows 환경 및 실제 Android arm64 휴대폰에서 키보드 노출·터치·시스템 안전영역은 별도 검증이 필요합니다. 자동화 Chromium 뷰포트는 물리 기기 검증을 대체하지 않습니다.
- 파일의 문서 내용은 모델 프롬프트에 파일당 최대 12,000자만 전달합니다. **전체 문서를 분석했다는 의미가 아닙니다.**
- 최신 `aaiai(1).zip`와의 세부 파일·기능 비교/통합은 소스 확보 후 별도로 수행해야 합니다.

## 다시 실행하기

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app.py core scripts
python -m playwright install chromium
python -m streamlit run scripts/markdown_fixture.py
# 다른 터미널
python scripts/visual_qa.py --fixture
# 앱 실행으로 교체한 뒤
python -m streamlit run app.py
python scripts/visual_qa.py
```