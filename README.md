# PDF Analyzer

간단한 Streamlit UI에서 PDF를 업로드하고 `opendataloader-pdf` 파서 결과를 확인하는 예제 앱입니다.

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

`opendataloader-pdf`는 PDF 파싱 과정에서 Java 실행 환경을 사용합니다. 앱 실행 전에 Java 17 이상을 설치하고 `java` 명령이 터미널에서 실행되는지 확인하세요.

Windows에서는 다음 명령으로 설치할 수 있습니다.

```powershell
winget install EclipseAdoptium.Temurin.17.JDK
java -version
```

설치 후에도 `java` 명령을 찾지 못하면 새 터미널을 열거나 `JAVA_HOME`과 `PATH` 환경 변수를 확인하세요.

## Streamlit Cloud 배포

- 저장소 루트의 `requirements.txt`를 기준으로 의존성을 자동 설치합니다.
- 앱 시작 명령은 `streamlit run app.py`를 사용합니다.
- Python 버전은 Streamlit Cloud의 앱 설정(Advanced settings)에서 지정할 수 있으며, 지정하지 않으면 기본 버전이 사용됩니다.
- 배포 환경에서도 Java가 필요합니다. Streamlit Cloud에서 동일한 오류가 발생하면 Java를 포함할 수 있는 배포 환경으로 전환하거나, Java 의존성이 없는 PDF 파서로 교체해야 합니다.

## 샘플 사용 흐름

1. 앱 실행 후 `PDF Analyzer` 화면에서 PDF 파일을 업로드합니다.
2. 업로드 직후 임시 파일로 저장되고 파서가 실행됩니다.
3. 분석이 완료되면 JSON 형태의 파싱 결과를 확인합니다.
4. 파싱 중 오류가 발생하면 화면에 친화적인 에러 메시지가 표시됩니다.
