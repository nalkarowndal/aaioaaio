# P5 — 채팅 입력창·첨부 UI 통합

기준 저장소: `nalkarowndal/aaioaaio`, 기존 `main` P0–P4 위에 구축.

## 의도

기존 Streamlit + Python + Groq 모델 구조 및 다크 오로라·보라/시안 팔레트를 유지하면서, 업로드 패널을 상시 노출하지 않고 Chat 입력창의 내장 파일 첨부로 일원화합니다. React/Next.js 재작성 및 별도의 DB 도입은 P5 범위에 포함하지 않습니다.

## 동작

1. 기본 화면에는 메시지 입력창만 보입니다. Streamlit의 기본 파일 첨부 버튼을 통해 허용된 여러 문서/이미지를 선택할 수 있습니다.
2. 메시지와 파일을 함께 보내면 첨부내용을 정리한 뒤 기존 Groq 요청 처리를 실행합니다.
3. 파일만 제출하면 파일이 채팅 세션에 보관되고 Groq API는 호출하지 않습니다.
4. 이미 보관한 파일이 있을 때만 '첨부파일 N/8 · 관리' 패널을 표시합니다. 기본적으로 접혀 있으며 개별 제거, 이미지 미리보기, 전체 제거를 제공합니다.
5. 파일별 10MB, 최대 8개, 형식 검증, 문서 본문 제한, 이미지 정규화 규칙은 기존 core/attachments.py를 그대로 재사용합니다.
6. 같은 파일을 명시적으로 다시 선택하는 것은 새로운 사용자 동작이므로 허용합니다. 이전 업로더의 일시적인 중복 방지 키는 새 제출에서 초기화합니다.

## 확인 기준

- [x] GitHub Actions의 pytest·compileall PASS (27 passed)
- [x] 375/768/1280/1920px 반응형·가로 넘침 QA PASS (Chromium)
- [x] 1280px 기본 chat composer에서 TXT 2개 첨부 후 전송 PASS
- [x] 사용자 메시지 보라색 우측 정렬, AI 메시지와 구별 PASS (자동 스타일 검사)
- [ ] 첨부 9개 이상/중복/오류 파일 관리 및 이미지 미리보기 수동 확인
- [ ] 실제 Groq 키 연결 및 Windows/Android 실기기 확인

**주의:** 자동 QA가 PASS하더라도 실제 Groq 계정/Windows/Android 기기 검수는 별도로 구분합니다. 기존 P0–P4 QA 완료 기록은 수정하지 않습니다.

## 자동 검증 결과

- [GitHub Actions #43160878018](https://github.com/nalkarowndal/aaioaaio/actions/runs/43160878018): 2026-11-12, **success**.
- pytest: **27 passed**. `compileall`, Markdown fixture 브라우저 검사, 네 해상도의 메인 앱 브라우저 검사, 증거 artifact 업로드 모두 success.
- 실기기/실제 Groq 요청 및 첨부 경계 사례 수동 검증은 PASS로 표시하지 않습니다.
