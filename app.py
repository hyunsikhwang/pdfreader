import json
import tempfile
from pathlib import Path

import streamlit as st
import opendataloader_pdf


st.set_page_config(page_title="PDF Analyzer", layout="centered")
st.title("PDF Analyzer")

uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is None:
    st.info("PDF 파일을 업로드하면 분석 결과를 확인할 수 있습니다.")
else:
    suffix = Path(uploaded_file.name).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(uploaded_file.getbuffer())
        tmp_path = tmp_file.name

    try:
        with st.spinner("PDF를 분석하는 중입니다..."):
            result = opendataloader_pdf.convert(input_path=tmp_path)

        st.subheader("Parsed Result")

        if isinstance(result, (dict, list)):
            st.json(result)
        else:
            try:
                parsed_result = json.loads(result)
                st.json(parsed_result)
            except Exception:
                st.write(result)

    except Exception as exc:
        st.error(f"PDF 파싱에 실패했습니다. 파일 형식 또는 내용 확인 후 다시 시도해 주세요.\n\n상세: {exc}")
