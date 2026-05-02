# PDF Analyzer

간단한 Streamlit UI에서 PDF를 업로드하고 `opendataloader-pdf` 파서가 추출한 테이블을 HTML 또는 Markdown 형식으로 확인하고 내보내는 예제 앱입니다.

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

`opendataloader-pdf`는 PDF 파싱 과정에서 Java 실행 환경을 사용합니다. 로컬 실행 시에는 Java 런타임을 설치하고 `java` 명령이 터미널에서 실행되는지 확인하세요.

Windows에서는 다음 명령으로 설치할 수 있습니다.

```powershell
winget install EclipseAdoptium.Temurin.17.JDK
java -version
```

설치 후에도 `java` 명령을 찾지 못하면 새 터미널을 열거나 `JAVA_HOME`과 `PATH` 환경 변수를 확인하세요.

## Streamlit Cloud 배포

- 저장소 루트의 `requirements.txt`를 기준으로 의존성을 자동 설치합니다.
- 저장소 루트의 `packages.txt`를 기준으로 Java 런타임(`default-jre-headless`)을 함께 설치합니다.
- 앱 시작 명령은 `streamlit run app.py`를 사용합니다.
- Python 버전은 Streamlit Cloud의 앱 설정(Advanced settings)에서 지정할 수 있으며, 지정하지 않으면 기본 버전이 사용됩니다.
- `packages.txt`를 추가하거나 변경한 뒤에는 Streamlit Cloud에서 앱을 재부팅해야 시스템 패키지가 다시 설치됩니다.

## 샘플 사용 흐름

1. 앱 실행 후 `PDF Analyzer` 화면에서 PDF 파일을 업로드합니다.
2. 업로드 직후 임시 파일로 저장되고 파서가 실행됩니다.
3. 분석이 완료되면 PDF에 포함된 테이블 목록을 확인합니다.
4. 미리 볼 테이블을 선택하고 HTML 또는 Markdown 출력 형식을 고릅니다.
5. 개별 테이블 또는 선택한 테이블 전체를 파일로 내보냅니다.
6. 파싱 중 오류가 발생하면 화면에 친화적인 에러 메시지가 표시됩니다.
