# PDF Analyzer

간단한 Streamlit UI에서 PDF를 업로드하고 `opendataloader-pdf` 파서 결과를 확인하는 예제 앱입니다.

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud 배포

- 저장소 루트의 `requirements.txt`를 기준으로 의존성을 자동 설치합니다.
- 앱 시작 명령은 `streamlit run app.py`를 사용합니다.
- Python 버전은 Streamlit Cloud의 앱 설정(Advanced settings)에서 지정할 수 있으며, 지정하지 않으면 기본 버전이 사용됩니다.

## 샘플 사용 흐름

1. 앱 실행 후 `PDF Analyzer` 화면에서 PDF 파일을 업로드합니다.
2. 업로드 직후 임시 파일로 저장되고 파서가 실행됩니다.
3. 분석이 완료되면 JSON 형태의 파싱 결과를 확인합니다.
4. 파싱 중 오류가 발생하면 화면에 친화적인 에러 메시지가 표시됩니다.
