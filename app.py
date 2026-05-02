import json
import os
import shutil
import tempfile
from pathlib import Path

import streamlit as st
import opendataloader_pdf


def is_java_available() -> bool:
    return shutil.which("java") is not None


def parse_pdf(input_path: str) -> object:
    with tempfile.TemporaryDirectory() as output_dir:
        opendataloader_pdf.convert(
            input_path=input_path,
            output_dir=output_dir,
            format="json",
            quiet=True,
        )

        output_files = sorted(Path(output_dir).glob("*.json"))
        if not output_files:
            raise RuntimeError("파서가 JSON 결과 파일을 생성하지 않았습니다.")

        result_text = output_files[0].read_text(encoding="utf-8")
        if not result_text.strip():
            raise RuntimeError("파서가 빈 JSON 결과 파일을 생성했습니다.")

        return json.loads(result_text)


st.set_page_config(page_title="PDF Analyzer", layout="centered")
st.title("PDF Analyzer")

uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is None:
    st.info("PDF 파일을 업로드하면 분석 결과를 확인할 수 있습니다.")
elif not is_java_available():
    st.error(
        "PDF 파서 실행에 Java 런타임이 필요하지만 현재 Streamlit 실행 환경에서 "
        "`java` 명령을 찾을 수 없습니다.\n\n"
        "Streamlit Cloud 배포 시 저장소 루트의 `packages.txt`에 "
        "`default-jre-headless`가 포함되어 있는지 확인한 뒤 앱을 재부팅해 주세요."
    )
else:
    suffix = Path(uploaded_file.name).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(uploaded_file.getbuffer())
        tmp_path = tmp_file.name

    try:
        with st.spinner("PDF를 분석하는 중입니다..."):
            result = parse_pdf(tmp_path)

        st.subheader("Parsed Result")
        st.json(result)

    except Exception as exc:
        st.error(f"PDF 파싱에 실패했습니다. 파일 형식 또는 내용 확인 후 다시 시도해 주세요.\n\n상세: {exc}")
    finally:
        os.unlink(tmp_path)
