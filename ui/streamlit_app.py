import streamlit as st
import requests
import pandas as pd
import json

# API Configuration
API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="AIDEP Platform",
    page_icon="🚀",
    layout="wide"
)

def check_health():
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

def fetch_seeds():
    try:
        response = requests.get(f"{API_BASE_URL}/seed")
        if response.status_code == 200:
            return response.json().get("seeds", [])
    except Exception:
        pass
    return []

def add_seed(instruction, domain, category, difficulty, input_text="", output_text="", metadata=None):
    payload = {
        "instruction": instruction,
        "input": input_text,
        "output": output_text,
        "domain": domain,
        "category": category,
        "difficulty": difficulty,
        "metadata": metadata or {}
    }
    response = requests.post(f"{API_BASE_URL}/seed", json=payload)
    return response

def add_seed_json(json_str):
    try:
        data = json.loads(json_str)
        instruction = data.get("instruction", "")
        
        task = data.get("task", {})
        domain = task.get("domain", "General")
        category_raw = task.get("category", "other").lower()
        
        # Determine difficulty mapping
        diff_str = str(task.get("difficulty", "")).lower()
        if diff_str == "easy":
            difficulty = 2
        elif diff_str == "medium":
            difficulty = 5
        elif diff_str == "hard":
            difficulty = 8
        else:
            difficulty = 5
            
        example = data.get("example", {})
        input_text = example.get("input", "")
        output_text = example.get("output", "")
        
        # Pack extra info into metadata
        metadata = {}
        if "seed_id" in data:
            metadata["seed_id"] = data["seed_id"]
        if "constraints" in data:
            metadata["constraints"] = data["constraints"]
        if "reasoning_level" in task:
            metadata["reasoning_level"] = task["reasoning_level"]
        if "type" in task:
            metadata["type"] = task["type"]
            
        return add_seed(instruction, domain, category_raw, difficulty, input_text, output_text, metadata)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {str(e)}"}
    except Exception as e:
        return {"error": f"Error parsing JSON: {str(e)}"}

def run_pipeline(count):
    payload = {"count": count}
    response = requests.post(f"{API_BASE_URL}/pipeline/run", json=payload)
    return response

# Sidebar navigation
st.sidebar.title("AIDEP Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Seed Knowledge Base", "Pipeline Orchestrator"])

if page == "Dashboard":
    st.title("🚀 Autonomous Instruction Data Engineering Platform (AIDEP)")
    
    st.write("Welcome to the AIDEP Platform. Use the sidebar to navigate.")
    
    health = check_health()
    if health:
        st.success("API Status: Connected & Operational")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("AIDEP Version", health.get("version", "N/A"))
        with col2:
            st.metric("Database Status", health.get("database", "N/A"))
    else:
        st.error("API Status: Disconnected. Please ensure FastAPI is running on port 8000.")

elif page == "Seed Knowledge Base":
    st.title("🌱 Seed Knowledge Base")
    
    st.subheader("Add a New Seed Task")
    tab1, tab2 = st.tabs(["Simple Form", "Advanced JSON Input"])
    
    with tab1:
        with st.form("add_seed_form"):
            col_id, col_type = st.columns(2)
            with col_id:
                seed_id = st.text_input("Seed ID", placeholder="seed_0001")
            with col_type:
                task_type = st.text_input("Task Type", value="Generation")
                
            instruction = st.text_area("Instruction", placeholder="Translate English text into French.")
            
            col1, col2 = st.columns(2)
            with col1:
                domain = st.text_input("Domain", value="Language")
            with col2:
                category = st.selectbox("Category", ["coding", "reasoning", "summarization", "translation", "other"], index=3)
                
            col3, col4 = st.columns(2)
            with col3:
                difficulty_str = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"])
            with col4:
                reasoning_level = st.selectbox("Reasoning Level", ["Low", "Medium", "High"])
                
            constraints = st.text_area("Constraints (One per line)", placeholder="Preserve meaning\nReturn only translated text")
            
            st.markdown("**Example**")
            example_input = st.text_area("Input", placeholder="Good morning")
            example_output = st.text_area("Output", placeholder="Bonjour")
            
            submitted = st.form_submit_button("Add Seed Task")
            if submitted:
                if instruction:
                    # Map difficulty
                    diff_map = {"Easy": 2, "Medium": 5, "Hard": 8}
                    diff_val = diff_map.get(difficulty_str, 5)
                    
                    # Pack metadata
                    metadata = {}
                    if seed_id: metadata["seed_id"] = seed_id
                    if task_type: metadata["type"] = task_type
                    if reasoning_level: metadata["reasoning_level"] = reasoning_level
                    if constraints: 
                        metadata["constraints"] = [c.strip() for c in constraints.split("\n") if c.strip()]
                        
                    res = add_seed(instruction, domain, category, diff_val, example_input, example_output, metadata)
                    if res.status_code == 201:
                        st.success("Seed task added successfully!")
                    else:
                        st.error(f"Failed to add seed task: {res.text}")
                else:
                    st.warning("Please provide an instruction.")
                    
    with tab2:
        with st.form("add_json_form"):
            json_input = st.text_area("Paste Human Feed JSON", height=300, placeholder='{\n  "seed_id": "seed_0001",\n  "instruction": "Translate..."\n}')
            json_submitted = st.form_submit_button("Submit JSON Seed")
            
            if json_submitted:
                if json_input.strip():
                    res = add_seed_json(json_input)
                    if isinstance(res, dict) and "error" in res:
                        st.error(res["error"])
                    elif res.status_code == 201:
                        st.success("JSON Seed task added successfully!")
                    else:
                        st.error(f"Failed to add JSON seed task: {res.text}")
                else:
                    st.warning("Please provide a JSON payload.")
                
    st.divider()
    st.subheader("Existing Seed Tasks")
    seeds = fetch_seeds()
    if seeds:
        df = pd.DataFrame(seeds)
        # Reorder and format columns for display
        if not df.empty:
            display_cols = ["id", "instruction", "domain", "category", "difficulty", "source"]
            st.dataframe(df[[c for c in display_cols if c in df.columns]], use_container_width=True)
    else:
        st.info("No seed tasks found or unable to fetch from API.")

elif page == "Pipeline Orchestrator":
    st.title("⚙️ Pipeline Orchestrator")
    st.write("Run the end-to-end instruction generation pipeline.")
    
    with st.form("pipeline_form"):
        st.write("Configure Pipeline Run")
        count = st.number_input("Number of instructions to generate", min_value=1, max_value=200, value=10)
        
        submitted = st.form_submit_button("Run Pipeline")
        
    if submitted:
        with st.spinner(f"Running pipeline to generate {count} instructions... This may take a while."):
            res = run_pipeline(count)
            if res.status_code == 202 or res.status_code == 200:
                data = res.json()
                st.success("Pipeline completed successfully!")
                st.json(data)
            else:
                st.error(f"Pipeline failed: {res.text}")
