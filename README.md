# AI Studio — Streamlit 챗봇

2026-11-12 작업 기준. 기존 `ais.zip`에서 확인 가능한 Streamlit UI를 기초로 복원한 보안 정비 버전입니다. 최신 `aaiai(1).zip`은 접근 불가하므로 소스와 정확한 일치가 보장되지 않습니다.

## 실행

```bash
python -m pip install -r requirements.txt
export GROQ_API_KEY="YOUR_KEY"  # Windows PowerShell: $env:GROQ_API_KEY="YOUR_KEY"
python -m streamlit run app.py
```

환경 변수가 없다면 외부 AI 모델 호출은 비활성화되고, 기존 메시지 기록과 파일 관리 UI만 사용할 수 있습니다. `.streamlit/secrets.toml`과 `.env`를 Git에 올리지 마세요.

## QA

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app.py core
```

브라우저 확인: `python scripts/visual_qa.py` (Playwright + Chromium 필요).

단계 상태 및 미검증 항목은 `docs/QA_STATUS.md`에 기록합니다.