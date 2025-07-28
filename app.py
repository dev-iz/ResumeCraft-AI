import streamlit as st
import PyPDF2 as pdf
import os
import pandas as pd
import matplotlib.pyplot as plt
from wordcloud import WordCloud
from dotenv import load_dotenv
import google.generativeai as genai
import difflib
import json
import re

# Inject Google Analytics tracking via HTML
st.markdown("""
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-BJMTQQPZK"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-BJMTQQPZK');
</script>
""", unsafe_allow_html=True)

# Setup
load_dotenv()
os.environ['GOOGLE_API_KEY'] = st.secrets['API_KEY']
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=GOOGLE_API_KEY)

def get_gemini_response(input):
    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content(input)
    return response.text

def input_pdf_text(uploaded_file):
    reader = pdf.PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text

def parse_gemini_response(response):
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        try:
            match = re.search(r'\{.*?\}', response, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception:
            pass
    return {}

input_prompt = """
Hey Act Like a skilled or very experienced ATS (Application Tracking System)
with a deep understanding of the tech field, software engineering, data science,
data analysis, and big data engineering. Your task is to evaluate the resumes based
on the given job description. You must consider the job market is very competitive
and you should provide the best assistance for improving the resumes. Assign the
percentage matching based on JD and the missing keywords with high accuracy.
resume:{text}
description:{jd}

I want the response as per below structure
{{"JD Match": "%", "MissingKeywords": [], "Profile Summary": "", "Suggestions": ""}}

Be strict while scoring: a candidate must cover most of the required skills, experience, and technologies to get a higher match. Score each resume uniquely and realistically based on content.
"""

st.set_page_config(page_title="Smart ATS for Resumes", layout="wide")
st.title("📄 Resume Checker using LLM")

jd = st.text_area("Paste the Job Description")
uploaded_files = st.file_uploader("Upload Your Resumes", type="pdf", accept_multiple_files=True)

if st.button("Submit"):
    if uploaded_files and jd:
        ranked_resumes = []

        for uploaded_file in uploaded_files:
            text = input_pdf_text(uploaded_file)
            input_text = input_prompt.format(text=text, jd=jd)
            response = get_gemini_response(input_text)

            parsed = parse_gemini_response(response)

            try:
                match_str = parsed.get("JD Match", "").replace("%", "").strip()
                match_percentage = float(match_str) if match_str else None
            except:
                match_percentage = None

            if match_percentage is None:
                ratio = difflib.SequenceMatcher(None, jd.lower(), text.lower()).ratio()
                match_percentage = round(ratio * 100, 2)
                st.warning(f"⚠️ Gemini failed for: {uploaded_file.name} → Fallback used.")

            description = parsed.get("Profile Summary", "No summary found")
            missing_keywords = parsed.get("MissingKeywords", [])
            suggestions = parsed.get("Suggestions", "No suggestions provided.")
            source = "Gemini" if parsed.get("JD Match") else "Fallback"

            ranked_resumes.append({
                "name": uploaded_file.name,
                "match_percentage": match_percentage,
                "response": response,
                "description": description,
                "missing_keywords": missing_keywords,
                "suggestions": suggestions,
                "source": source
            })

        ranked_resumes = sorted(ranked_resumes, key=lambda x: x["match_percentage"], reverse=True)
        df = pd.DataFrame(ranked_resumes)
        df["Rank"] = range(1, len(df) + 1)

        st.session_state["df"] = df

        def highlight_match(val):
            color = '#b2f2bb' if val >= 85 else '#a5d8ff' if val >= 70 else '#ffc9c9'
            return f'background-color: {color}'

        styled_df = df[["name", "Rank", "match_percentage", "source", "description", "missing_keywords"]].style.applymap(
            highlight_match, subset=["match_percentage"]
        )

        st.subheader("📊 Ranked Resume Results")
        st.dataframe(styled_df, use_container_width=True)

        st.subheader("📈 Visual Match Progress")
        for _, row in df.iterrows():
            st.markdown(f"**{row['name']}**")
            st.progress(int(row['match_percentage']))

        all_keywords = [kw for kws in df["missing_keywords"] for kw in kws]
        if all_keywords:
            st.subheader("☁️ Common Missing Keywords")
            wordcloud = WordCloud(width=800, height=300, background_color='black').generate(" ".join(all_keywords))
            plt.imshow(wordcloud, interpolation='bilinear')
            plt.axis("off")
            st.pyplot(plt)

        st.subheader("🔍 Detailed Feedback")
        for _, row in df.iterrows():
            with st.expander(f"{row['name']} - Match: {row['match_percentage']}%"):
                st.markdown("**📋 Profile Summary:**")
                st.write(row["description"])
                st.markdown("**🧩 Missing Keywords:**")
                st.write(", ".join(row["missing_keywords"]) if row["missing_keywords"] else "✅ No major gaps!")
                st.markdown("**🛠 Suggestions:**")
                st.write(row["suggestions"])
                st.markdown(f"**📥 Scoring Source:** `{row['source']}`")

        st.subheader("📊 Match % Distribution")
        st.bar_chart(df.set_index("name")["match_percentage"])

if "df" in st.session_state:
    st.subheader("🎯 Filter by Minimum Match %")
    min_score = st.slider("Set minimum match %", 0, 100, 70)
    filtered_df = st.session_state["df"][st.session_state["df"]["match_percentage"] >= min_score]

    st.subheader("📋 Filtered Resumes")
    st.dataframe(filtered_df[["name", "Rank", "match_percentage", "source"]], use_container_width=True)

    st.download_button("📥 Download Results as CSV", filtered_df.to_csv(index=False), "filtered_resume_results.csv", "text/csv")
