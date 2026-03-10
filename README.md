# File: full_ai_system_builder.py
import os
import time
import zipfile
import streamlit as st

# ================== إعداد المشروع ==================
PROJECT_NAME = "AI_System_Builder_Full"
LANGUAGES = ["Python", "JavaScript", "SQL"]  # اللغات المدعومة
FOLDERS = ["backend", "frontend", "ai_modules", "database", "tasks", "docs", "build"]

if not os.path.exists(PROJECT_NAME):
    os.mkdir(PROJECT_NAME)
    for folder in FOLDERS:
        os.mkdir(os.path.join(PROJECT_NAME, folder))

# ================== واجهة Streamlit ==================
st.set_page_config(page_title="AI System Builder Full", layout="wide")
st.title("🤖 AI System Builder Full")
st.write("""
Simulate a **fully autonomous AI software company** that builds complex systems automatically.
- Supports multiple languages (Python, JS, SQL)
- Generates real files and code
- Full development pipeline with testing and optimization
- Download project as ZIP
""")

user_idea = st.text_area("Enter your project idea:", "Build a cybersecurity OS similar to Kali Linux")
run_button = st.button("Run Full Project Simulation")
download_button = st.button("Download Full Project as ZIP")

# ================== وظيفة تحميل المشروع ==================
def zip_project():
    zipf = zipfile.ZipFile(f"{PROJECT_NAME}.zip", "w", zipfile.ZIP_DEFLATED)
    for root, dirs, files in os.walk(PROJECT_NAME):
        for file in files:
            zipf.write(os.path.join(root, file),
                       arcname=os.path.relpath(os.path.join(root, file), PROJECT_NAME))
    zipf.close()
    return f"{PROJECT_NAME}.zip"

# ================== وكلاء AI ==================
class ExecutiveAgent:
    def manage_project(self):
        st.info("🧠 Executive Agent: Managing project priorities and resources...")
        time.sleep(1)

class RequestAnalysisAgent:
    def analyze_request(self, idea):
        st.info(f"📊 Request Analysis Agent: Analyzing user idea -> '{idea}'")
        time.sleep(1)
        modules = ["backend", "frontend", "ai_modules", "database"]
        complexity = "High" if "OS" in idea or "SaaS" in idea else "Medium"
        return {"type": "Project", "modules": modules, "complexity": complexity, "languages": LANGUAGES}

class SystemArchitectAgent:
    def design_architecture(self, analysis):
        st.info(f"🏗 System Architect Agent: Designing architecture for modules {analysis['modules']}")
        time.sleep(1)
        architecture = {}
        for idx, mod in enumerate(analysis['modules']):
            architecture[mod] = {
                "structure": f"{mod}_structure",
                "language": analysis["languages"][idx % len(analysis["languages"])]
            }
        return architecture

class TaskPlannerAgent:
    def plan_tasks(self, architecture):
        st.info("📝 Task Planner Agent: Planning tasks based on architecture...")
        time.sleep(1)
        tasks = []
        for mod in architecture:
            tasks.append(f"Develop {mod}")
            tasks.append(f"Test {mod}")
            tasks.append(f"Optimize {mod}")
        return tasks

class DeveloperAgent:
    def develop_module(self, module, language):
        st.info(f"💻 Developer Agent: Writing {language} code for {module}...")
        time.sleep(1)
        folder_path = os.path.join(PROJECT_NAME, module)
        ext = {"Python": "py", "JavaScript": "js", "SQL": "sql"}.get(language, "txt")
        filename = os.path.join(folder_path, f"{module}.{ext}")
        with open(filename, "w") as f:
            if language == "Python":
                f.write(f"# {module} Python code\nprint('Running {module}')\n")
            elif language == "JavaScript":
                f.write(f"// {module} JavaScript code\nconsole.log('Running {module}');\n")
            elif language == "SQL":
                f.write(f"-- {module} SQL schema\nCREATE TABLE {module} (id INT PRIMARY KEY);\n")
        return filename

class TestingAgent:
    def test_module(self, filename):
        st.info(f"✅ Testing Agent: Testing {filename}...")
        time.sleep(1)
        st.success(f"{filename} passed automated tests!")

class DebuggingAgent:
    def debug_module(self, filename):
        st.info(f"🔧 Debugging Agent: Debugging {filename}...")
        time.sleep(1)
        st.success(f"{filename} debugged successfully!")

class IntegrationAgent:
    def integrate_modules(self, modules):
        st.info("🔗 Integration Agent: Merging modules into final project...")
        time.sleep(1)
        st.success("All modules integrated successfully!")

class OptimizationAgent:
    def optimize_project(self):
        st.info("⚡ Optimization Agent: Optimizing project performance and structure...")
        time.sleep(1)
        st.success("Project fully optimized!")

# ================== تشغيل المحاكاة ==================
if run_button:
    exec_agent = ExecutiveAgent()
    req_agent = RequestAnalysisAgent()
    arch_agent = SystemArchitectAgent()
    task_agent = TaskPlannerAgent()
    dev_agent = DeveloperAgent()
    test_agent = TestingAgent()
    debug_agent = DebuggingAgent()
    integ_agent = IntegrationAgent()
    opt_agent = OptimizationAgent()

    exec_agent.manage_project()
    analysis = req_agent.analyze_request(user_idea)
    architecture = arch_agent.design_architecture(analysis)
    tasks = task_agent.plan_tasks(architecture)

    st.subheader("🚀 Full Development Pipeline")
    for mod, info in architecture.items():
        file_created = dev_agent.develop_module(mod, info["language"])
        test_agent.test_module(file_created)
        debug_agent.debug_module(file_created)

    integ_agent.integrate_modules(list(architecture.keys()))
    opt_agent.optimize_project()

    st.success("🎉 Full Project Simulation Completed Successfully!")

    st.subheader("📂 Generated Project Files")
    for folder in FOLDERS:
        folder_path = os.path.join(PROJECT_NAME, folder)
        files = os.listdir(folder_path)
        st.write(f"{folder}: {files}")

# ================== تحميل المشروع ==================
if download_button:
    zip_path = zip_project()
    with open(zip_path, "rb") as f:
        st.download_button("⬇ Download Full Project ZIP", f, file_name=zip_path)
