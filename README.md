# PDF Analyzer

간단한 Streamlit UI에서 PDF를 업로드하고 테이블 내용 조건 또는 문서 항목 경로 조건을 입력하면, `opendataloader-pdf` 파서가 추출한 테이블 중 조건에 맞는 항목을 HTML 또는 Markdown 형식으로 확인하고 내보내는 예제 앱입니다.

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
2. 테이블 내용 조건 또는 문서 항목 경로 조건을 입력합니다. 조건을 비워두면 모든 테이블을 가져옵니다.
3. `테이블 검색`을 눌러 PDF 전체에서 테이블을 추출하고 조건을 적용합니다.
4. 분석이 완료되면 가벼운 테이블 인덱스에서 크기와 식별 단서를 확인합니다.
5. 문서 항목 경로 조건을 사용한 경우 검색 진단에서 어느 단계까지 매칭되었는지 확인합니다.
6. 필요한 경우 테이블 하나만 상세 미리보기로 열어 내용을 확인합니다.
7. 내보낼 테이블만 선택하고 HTML 또는 Markdown 형식으로 파일을 저장합니다.
8. 파싱 중 오류가 발생하면 화면에 친화적인 에러 메시지가 표시됩니다.

## 테이블 내용 조건 예시

- `매출 영업이익`: 두 단어가 모두 포함된 테이블을 찾습니다.
- `매출 AND 영업이익`: 위와 동일하게 AND 조건으로 찾습니다.
- `"현금흐름" OR EBITDA`: 문구 또는 단어 중 하나가 포함된 테이블을 찾습니다.
- `매출 NOT 전년`: `매출`은 포함하고 `전년`은 포함하지 않는 테이블을 찾습니다.

## 문서 항목 경로 조건 예시

여러 줄 또는 `>>`를 포함한 조건은 테이블 내용이 아니라 테이블이 속한 문서 항목 경로에서 검색합니다.
번호, 괄호, 대괄호, 일반 공백, 줄바꿈, 전각 공백, 보이지 않는 공백 문자 차이는 무시하고 부분 문구가 포함되면 같은 항목으로 봅니다.

```text
경영지표
>> 지급여력비율
>> 지급여력비율의 경과조치 적용에 관한 세부사항
>> 지급여력비율의 경과조치 적용에 관한 사항
>> 공통적용 경과조치 관련
```
