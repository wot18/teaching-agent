#!/usr/bin/env python3

import json
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

st.set_page_config(
    page_title="全链路启发式教学辅助智能体",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.config_loader import get_auth_config

auth_cfg = get_auth_config()
credentials = auth_cfg.get("credentials", {})

if credentials:
    import streamlit_authenticator as stauth

    cookie_cfg = auth_cfg.get("cookie", {})
    user_dict = {}
    for _key, val in credentials.items():
        if isinstance(val, dict):
            uname = val.get("username", _key)
            pwd = val.get("password", "")
        else:
            uname, pwd = _key, str(val)
        user_dict[uname] = {"name": uname.capitalize(), "password": stauth.Hasher.hash(pwd)}

    authenticator = stauth.Authenticate(
        credentials={"usernames": user_dict},
        cookie_name=cookie_cfg.get("name", "teaching_agent"),
        cookie_key=cookie_cfg.get("key", "super_secret_key"),
        cookie_expiry_days=cookie_cfg.get("expiry_days", 7),
    )
    authenticator.login("main")

    if st.session_state.get("authentication_status") is False:
        st.error("用户名或密码错误")
        st.stop()
    elif st.session_state.get("authentication_status") is None:
        st.warning("请输入用户名和密码")
        st.stop()

    name = st.session_state.get("name", "")
    username = st.session_state.get("username", "")
else:
    username = "teacher"
    name = "Teacher"
    authenticator = None

st.sidebar.title("🎓 教学辅助智能体")
st.sidebar.markdown(f"当前用户: **{name}**")

role = "teacher" if username in ("teacher", "judge") else "student"
page = st.sidebar.radio(
    "选择功能",
    ["📚 教师端 - 课件解析与作业生成", "📝 学生端 - 作业提交与批阅"],
    index=0 if role == "teacher" else 1,
)

if authenticator:
    authenticator.logout("退出登录", location="sidebar")


def _session_dir() -> Path:
    sid = st.session_state.get("session_id", str(uuid.uuid4())[:8])
    d = Path("data/sessions") / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _render_teacher_page():
    st.title("📚 教师端 - 课件解析与作业生成")

    if "teacher_step" not in st.session_state:
        st.session_state.teacher_step = 1
        st.session_state.pdf_text = ""
        st.session_state.knowledge_md = ""
        st.session_state.exercise_md = ""
        st.session_state.exercise_set_json = ""
        st.session_state.notebook_path = ""
        st.session_state.session_id = str(uuid.uuid4())[:8]

    steps = ["1️⃣ 上传课件", "2️⃣ 知识抽取", "3️⃣ 习题生成", "4️⃣ 教师审核", "5️⃣ 生成作业"]
    current = st.session_state.teacher_step - 1
    st.markdown(" → ".join(f"**{s}**" if i == current else s for i, s in enumerate(steps)))

    if st.session_state.teacher_step == 1:
        st.header("1️⃣ 上传课件 PDF")
        uploaded = st.file_uploader("选择 PDF 课件文件", type=["pdf"], key="pdf_upload")
        if uploaded and not st.session_state.pdf_text:
            with st.spinner("解析 PDF..."):
                from src.pdf_parser import extract_text

                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(uploaded.getvalue())
                    tmp_path = tmp.name

                try:
                    text = extract_text(tmp_path)
                    st.session_state.pdf_text = text
                except Exception as e:
                    st.error(f"PDF解析失败：{e}")
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

        if st.session_state.pdf_text:
            st.success(f"解析成功！共提取 {len(st.session_state.pdf_text)} 个字符")
            with st.expander("预览提取文本"):
                preview = st.session_state.pdf_text[:3000] + ("..." if len(st.session_state.pdf_text) > 3000 else "")
                st.text_area("PDF文本", preview, height=300, disabled=True)
            if st.button("下一步：知识抽取 →", type="primary"):
                st.session_state.teacher_step = 2
                st.rerun()

    elif st.session_state.teacher_step == 2:
        st.header("2️⃣ 知识抽取")
        if st.button("开始知识抽取", type="primary"):
            from src.llm_client import LLMClient
            from src.exercise_generator import ExerciseGenerator
            from src.markdown_parser import save_markdown

            with st.spinner("正在调用大模型提取知识点...（可能需要1-2分钟）"):
                try:
                    llm = LLMClient()
                    gen = ExerciseGenerator(llm)
                    knowledge_md = gen.extract_knowledge(st.session_state.pdf_text)
                    st.session_state.knowledge_md = knowledge_md

                    session_dir = _session_dir()
                    save_markdown(knowledge_md, session_dir / "knowledge_summary.md")

                    st.success(f"知识抽取完成！（{len(knowledge_md)} 字符）")
                except Exception as e:
                    st.error(f"知识抽取失败：{e}")
                    return

        if st.session_state.knowledge_md:
            st.subheader("知识点总结")
            st.markdown(st.session_state.knowledge_md)

            session_dir = _session_dir()
            st.download_button(
                "📥 下载知识点总结 (Markdown)",
                data=st.session_state.knowledge_md,
                file_name="knowledge_summary.md",
                mime="text/markdown",
            )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("← 返回上传", key="back2"):
                    st.session_state.teacher_step = 1
                    st.rerun()
            with col2:
                if st.button("下一步：生成习题 →", type="primary"):
                    st.session_state.teacher_step = 3
                    st.rerun()

    elif st.session_state.teacher_step == 3:
        st.header("3️⃣ 习题生成")
        if st.button("生成习题", type="primary"):
            from src.llm_client import LLMClient
            from src.exercise_generator import ExerciseGenerator
            from src.markdown_parser import save_markdown

            with st.spinner("正在生成习题...（可能需要2-3分钟）"):
                try:
                    llm = LLMClient()
                    gen = ExerciseGenerator(llm)
                    exercise_md = gen.generate_exercises(st.session_state.knowledge_md)
                    st.session_state.exercise_md = exercise_md

                    session_dir = _session_dir()
                    save_markdown(exercise_md, session_dir / "exercise_draft.md")

                    st.success(f"习题生成完成！（{len(exercise_md)} 字符）")
                except Exception as e:
                    st.error(f"习题生成失败：{e}")
                    return

        if st.session_state.exercise_md:
            st.subheader("生成的习题（含答案）")
            st.markdown(st.session_state.exercise_md)

            session_dir = _session_dir()
            st.download_button(
                "📥 下载习题草稿 (Markdown)",
                data=st.session_state.exercise_md,
                file_name="exercise_draft.md",
                mime="text/markdown",
            )

            if st.button("下一步：教师审核 →", type="primary"):
                from src.markdown_parser import parse_exercise_markdown

                exercise_set = parse_exercise_markdown(
                    st.session_state.exercise_md,
                    st.session_state.knowledge_md,
                )
                st.session_state.exercise_set_json = exercise_set.model_dump_json(
                    indent=2, ensure_ascii=False,
                )
                st.session_state.teacher_step = 4
                st.rerun()

    elif st.session_state.teacher_step == 4:
        st.header("4️⃣ 教师审核")

        st.markdown("### 作业预览（含完整题目与答案）")
        st.markdown(st.session_state.exercise_md)

        st.download_button(
            "📥 下载教师审核版 (Markdown)",
            data=st.session_state.exercise_md.encode("utf-8"),
            file_name="exercise_review.md",
            mime="text/markdown",
        )

        st.markdown("---")
        st.markdown(
            "**审核流程：** 下载上方Markdown文件 → 在本地编辑修改 → 上传修改后的文件 → 确认生成"
        )

        uploaded_review = st.file_uploader(
            "📤 上传修改后的习题文件 (.md)",
            type=["md"],
            key="review_upload",
        )

        if uploaded_review:
            reviewed_md = uploaded_review.read().decode("utf-8")
            st.subheader("上传的修改版本预览")
            st.markdown(reviewed_md)

            col1, col2 = st.columns(2)
            with col1:
                if st.button("← 返回重新生成", key="back4"):
                    st.session_state.teacher_step = 3
                    st.rerun()
            with col2:
                if st.button("✅ 确认此版本，生成学生作业 →", type="primary"):
                    from src.markdown_parser import parse_exercise_markdown

                    exercise_set = parse_exercise_markdown(
                        reviewed_md,
                        st.session_state.knowledge_md,
                    )
                    st.session_state.exercise_md = reviewed_md
                    st.session_state.exercise_set_json = exercise_set.model_dump_json(
                        indent=2, ensure_ascii=False,
                    )
                    st.session_state.teacher_step = 5
                    st.rerun()
        else:
            if st.button("← 返回重新生成", key="back4_noupload"):
                st.session_state.teacher_step = 3
                st.rerun()

    elif st.session_state.teacher_step == 5:
        st.header("5️⃣ 生成学生作业")
        from src.models import ExerciseSet
        from src.notebook_builder import build_notebook

        exercise_set = ExerciseSet.model_validate_json(st.session_state.exercise_set_json)

        session_dir = _session_dir()
        answers_path = session_dir / "standard_answers.json"
        answers_path.write_text(st.session_state.exercise_set_json, encoding="utf-8")

        nb_path = session_dir / f"{exercise_set.chapter or '课程'}_作业练习.ipynb"
        build_notebook(exercise_set, nb_path)
        st.session_state.notebook_path = str(nb_path)

        st.success("✅ 作业文件已生成！")

        col1, col2 = st.columns(2)
        with col1:
            nb_data = Path(st.session_state.notebook_path).read_bytes()
            st.download_button(
                "📥 下载学生作业 (.ipynb)",
                data=nb_data,
                file_name=f"{exercise_set.chapter or '课程'}_作业练习.ipynb",
                mime="application/x-ipynb+json",
            )
        with col2:
            answers_data = answers_path.read_bytes()
            st.download_button(
                "📥 下载标准答案 (JSON)",
                data=answers_data,
                file_name=f"{exercise_set.chapter or '课程'}_标准答案.json",
                mime="application/json",
            )

        if st.button("🔄 重新开始（上传新课件）"):
            for key in ["teacher_step", "pdf_text", "knowledge_md", "exercise_md",
                         "exercise_set_json", "notebook_path"]:
                st.session_state.pop(key, None)
            st.rerun()


def _render_student_page():
    st.title("📝 学生端 - 作业提交与批阅")

    uploaded = st.file_uploader("上传完成的作业 (.ipynb)", type=["ipynb"], key="student_upload")
    answers_upload = st.file_uploader("上传标准答案 (.json)", type=["json"], key="answers_upload")

    if uploaded and answers_upload:
        if st.button("开始批阅", type="primary"):
            from src.models import ExerciseSet
            from src.llm_client import LLMClient
            from src.grading_agent import GradingAgent

            with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False) as nb_tmp:
                nb_tmp.write(uploaded.getvalue())
                nb_path = nb_tmp.name

            answers_data = json.loads(answers_upload.getvalue())

            try:
                exercise_set = ExerciseSet.model_validate(answers_data)
                llm = LLMClient()
                agent = GradingAgent(llm)

                with st.spinner("正在批阅...（可能需要3-5分钟）"):
                    result = agent.grade_submission(nb_path, exercise_set)

                st.success(f"批阅完成！总分：{result.total_score:.1f} / {result.total_max:.1f}")

                score_pct = result.total_score / max(result.total_max, 1) * 100
                st.progress(int(score_pct))
                st.markdown(f"### 📊 总分：{result.total_score:.1f} / {result.total_max:.1f} ({score_pct:.0f}%)")

                for qg in result.question_grades:
                    q_num = qg.question_id.replace("q", "")
                    with st.expander(f"第 {q_num} 题（得分：{qg.total_score:.1f}/{qg.total_max:.1f}）"):
                        st.markdown(qg.feedback)

                report_md = _generate_student_report(result)
                st.download_button(
                    "📥 下载批改报告 (Markdown)",
                    data=report_md,
                    file_name="批改报告.md",
                    mime="text/markdown",
                )
            except Exception as e:
                st.error(f"批阅失败：{e}")
            finally:
                Path(nb_path).unlink(missing_ok=True)


def _generate_student_report(result):
    lines = ["# 作业批改报告\n"]
    lines.append(f"**批改时间**: {result.graded_at}\n\n")
    score_pct = result.total_score / max(result.total_max, 1) * 100
    lines.append(f"**总分: {result.total_score:.1f} / {result.total_max:.1f} ({score_pct:.0f}%)**\n\n---\n")

    for qg in result.question_grades:
        q_num = qg.question_id.replace("q", "")
        lines.append(f"\n### 第 {q_num} 题（得分: {qg.total_score:.1f}/{qg.total_max:.1f}）\n")
        lines.append(qg.feedback)
        lines.append("\n---")

    return "\n".join(lines)


if "📚" in page:
    _render_teacher_page()
else:
    _render_student_page()
