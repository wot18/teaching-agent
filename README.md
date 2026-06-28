# 全链路启发式教学辅助智能体

基于大模型的交互式脚手架教学智能体，实现从"课件解析"到"自动生成脚手架式作业"再到"语义级自动批阅"的闭环系统。

## 系统架构

```
PDF课件 ──► 课件解析 ──► 知识抽取(LLM) ──► 习题生成(LLM)
                                                │
                                           教师审核预览
                                                │
                                          Notebook生成 ──► .ipynb(学生版)
                                                │
学生提交.ipynb ──► 留白提取 ──► 语义评分(LLM) ──► 分数+诊断报告
```

## 技术栈

| 层面 | 技术 | 用途 |
|------|------|------|
| 前端交互 | Streamlit | 教师端/学生端Web界面 |
| 身份认证 | streamlit-authenticator | 轻量级账号密码验证 |
| 文档解析 | pdfplumber / PyMuPDF | 提取PDF课件文本 |
| 大模型接入 | OpenAI兼容API | MiniMax-M3 / DeepSeek / GLM |
| 作业构建 | nbformat | 生成与解析Jupyter Notebook |
| 数据校验 | Pydantic | JSON Schema验证 |
| 部署托管 | Streamlit Community Cloud | 公网HTTPS一键部署 |

## 项目结构

```
teaching-agent/
├── app.py                       # Streamlit主应用入口
├── grading_script.py            # 独立CLI评分脚本
├── requirements.txt             # Python依赖
├── config/
│   ├── config.yaml              # 运行配置（含API Key，已.gitignore）
│   └── config.example.yaml      # 脱敏配置模板
├── prompts/
│   ├── p1_extract_knowledge.md  # Prompt: 知识抽取
│   ├── p2_generate_exercise.md  # Prompt: 习题生成
│   └── p3_grade_answer.md       # Prompt: 语义批阅
├── src/
│   ├── models.py                # Pydantic数据模型
│   ├── config_loader.py         # 配置加载（双环境策略）
│   ├── llm_client.py            # LLM客户端（重试+JSON校验）
│   ├── pdf_parser.py            # PDF解析器
│   ├── exercise_generator.py    # 习题生成流水线
│   ├── notebook_builder.py      # Notebook构建器
│   ├── blank_extractor.py       # 学生答案提取器
│   └── grading_agent.py         # 语义评分引擎
└── data/
    ├── sessions/                # 教师审核会话数据
    └── uploads/                 # 上传文件临时存储
```

## 本地开发部署

### 1. 环境要求

- Python 3.10+
- pip

### 2. 克隆项目

```bash
git clone <你的仓库地址>
cd teaching-agent
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置API密钥

```bash
# 复制配置模板
cp config/config.example.yaml config/config.yaml
```

编辑 `config/config.yaml`，填入你的大模型API信息：

```yaml
llm:
  base_url: "https://api.minimaxi.com/v1"    # MiniMax API地址
  api_key: "你的API Key"                       # 替换为真实Key
  model_name: "MiniMax-M3"
  temperature: 0.3
  max_tokens: 8192
  max_retries: 3
```

如果使用其他模型，修改 `base_url` 和 `model_name` 即可：

| 模型 | base_url | model_name |
|------|----------|------------|
| MiniMax-M3 | `https://api.minimaxi.com/v1` | `MiniMax-M3` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 智谱GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4` |

### 5. 启动应用

```bash
streamlit run app.py
```

浏览器打开 `http://localhost:8501` 即可使用。

### 6. 测试账号

默认配置提供了以下账号：

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 教师 | teacher | teacher123 |
| 评委 | judge | TAC_judge_2026 |

可在 `config/config.yaml` 的 `auth` 部分修改。

## 公网部署（Streamlit Community Cloud）

### 前提条件

- GitHub 账号
- Streamlit Community Cloud 账号（用GitHub登录 [share.streamlit.io](https://share.streamlit.io)）

### 步骤

#### 1. 推送代码到GitHub

确保以下文件**不包含**在仓库中（已被 `.gitignore` 排除）：

- `config/config.yaml`（含API密钥）
- `data/sessions/`、`data/uploads/`（运行时数据）

确认 `config/config.example.yaml` 在仓库中作为配置参考。

```bash
git init
git add .
git status   # 检查 config.yaml 不在暂存区
git commit -m "Initial commit: teaching agent system"
git remote add origin <你的GitHub仓库地址>
git push -u origin main
```

#### 2. 在Streamlit Cloud配置Secrets

登录 [share.streamlit.io](https://share.streamlit.io)，新建App，选择你的GitHub仓库。

在 **Settings → Secrets** 中添加：

```toml
LLM_API_KEY = "你的API Key"
LLM_BASE_URL = "https://api.minimaxi.com/v1"
LLM_MODEL_NAME = "MiniMax-M3"
```

这样代码会通过 `config_loader.py` 的双环境策略自动从 Secrets 读取配置，无需在代码中硬编码。

#### 3. 部署

点击 **Deploy**，Streamlit Cloud 会自动安装依赖并启动应用。

部署成功后你会获得一个公网URL，如 `https://your-app-name.streamlit.app`。

### 备选部署方案：Hugging Face Spaces

```bash
# 1. 创建Space（选择Streamlit SDK）
# 在 https://huggingface.co/new-space 创建，SDK选Streamlit

# 2. 添加Secrets
# 在 Space Settings → Repository secrets 中添加：
# LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME

# 3. 推送代码
git remote add space https://huggingface.co/spaces/<你的用户名>/<space名>
git push space main
```

## 使用指南

### 教师端流程

1. **上传课件**：上传PDF格式的教学课件
2. **知识抽取**：系统自动调用LLM提取知识点，可预览抽取结果
3. **习题生成**：基于知识点自动生成10道脚手架式习题
4. **教师审核**：预览含完整答案的Markdown文档，可下载审核
5. **生成作业**：确认后生成学生版 `.ipynb` 文件和标准答案JSON，供下载分发

### 学生端流程

1. 下载教师分发的 `.ipynb` 作业文件
2. 在Jupyter Notebook中填写留白区域（`??????` 处）
3. 上传完成的 `.ipynb` 文件和标准答案JSON
4. 系统自动批阅，展示分数和诊断反馈
5. 下载批改报告

### CLI评分脚本

适合批量评分场景：

```bash
# 基本用法
python grading_script.py student_work.ipynb standard_answers.json

# 输出到文件
python grading_script.py student_work.ipynb standard_answers.json -o result.json

# 同时生成Markdown报告
python grading_script.py student_work.ipynb standard_answers.json -o result.json --markdown report.md
```

## 脚手架留白标记体系

系统使用结构化标记定位学生填写区域：

**Markdown Cell中：**

```html
<!-- BLANK_START:q1_step3 --> ????? <!-- BLANK_END:q1_step3 -->
```

**Code Cell中：**

```python
# BLANK_START:q2_sort
open_list.sort(key=lambda n: ???)  # TODO: 按f(n)排序
# BLANK_END:q2_sort
```

评分引擎通过正则匹配 `BLANK_START:id` 和 `BLANK_END:id` 精准提取每个留白区域的学生作答内容。

## 习题JSON Schema

每道题目的数据结构：

```json
{
  "id": "q1",
  "type": "logical_reasoning",
  "difficulty": 2,
  "knowledge_points": ["命题逻辑", "假言推理"],
  "question_text": "题目描述（Markdown）",
  "scaffold_cells": [
    {
      "cell_type": "markdown",
      "content": "含BLANK标记的脚手架内容",
      "has_blanks": true,
      "blank_ids": ["q1_step1", "q1_step2"]
    }
  ],
  "standard_answer": "完整标准答案",
  "rubric": [
    {"step": "q1_step1", "weight": 0.3, "description": "评分要点"},
    {"step": "q1_step2", "weight": 0.7, "description": "评分要点"}
  ]
}
```

题目类型：`logical_reasoning`（逻辑推理）、`proof`（证明）、`calculation`（计算）、`programming`（编程）

## 配置说明

### 双环境配置策略

`config_loader.py` 按以下优先级读取配置：

1. **本地 `config/config.yaml`**（开发环境首选）
2. **环境变量** `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_NAME`（云部署推荐）
3. **Streamlit Secrets**（Streamlit Cloud专属）

这意味着：
- 本地开发：只需填写 `config/config.yaml`
- 云端部署：只需在平台Secrets面板配置环境变量
- 两套配置互不干扰，`config.yaml` 已被 `.gitignore` 排除不会泄露

### 环境变量方式

如果不想用yaml文件，也可以直接设置环境变量：

```bash
export LLM_API_KEY="你的Key"
export LLM_BASE_URL="https://api.minimaxi.com/v1"
export LLM_MODEL_NAME="MiniMax-M3"
streamlit run app.py
```

## 注意事项

- **API费用**：每次完整流程（知识抽取+习题生成+批阅10题）约消耗3-5万token，请注意API用量
- **首次运行**：LLM生成习题约需2-3分钟，批阅约需3-5分钟，属于正常等待时间
- **PDF质量**：扫描版PDF或图片PDF可能无法提取文本，建议使用文字版PDF课件
- **浏览器兼容**：推荐使用Chrome或Edge访问Streamlit界面
- **并发限制**：Streamlit Community Cloud免费版有资源限制，建议避免多用户同时使用
