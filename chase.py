import streamlit as st
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
import pandas as pd
import time
import re
import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("key")
endpoint = os.getenv("endpoint")
model_id = os.getenv("model_id")

# Initialize Azure Document Intelligence Client
document_intelligence_client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))

# Set page configuration
st.set_page_config(
    page_title="Loot Intelligence Dashboard",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Loot Intelligence")

# Custom CSS for styling
st.markdown("""
    <style>
    .stProgress > div > div > div > div {
        background-color: #4CAF50;
    }
    .metric-box {
        padding: 10px; 
        border-radius: 10px; 
        text-align: center; 
        background-color: #f3f3f3; 
        box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
        margin-bottom: 10px;
    }
    .metric-title {
        font-size: 18px;
        margin-bottom: 5px;
    }
    .metric-value {
        font-size: 24px;
        color: #4CAF50;
    }
    </style>
""", unsafe_allow_html=True)

# Function to display metric cards
def metric_card(title, value, icon):
    st.markdown(f"""
    <div class="metric-box">
        <h4 class="metric-title">{icon} {title}</h4>
        <h2 class="metric-value">{value}</h2>
    </div>
    """, unsafe_allow_html=True)

# Function to extract balance data from response
def extract_balance_data(result):
    extracted_data = {}

    for key, value in result.documents[0].fields.items():
        if value.type == "array":
            item_list = []
            for item in value.value_array:
                data = item.value_object  
                extracted_entry = {field: data.get(field, {}).get("valueString", "N/A") for field in data.keys()}
                item_list.append(extracted_entry)

            df = pd.DataFrame(item_list)
            df.columns = [col.title() for col in df.columns]

            if "DailyEndingBalance" in key:
                extracted_data["Daily Ending Balance"] = df
            else:
                extracted_data[key.replace("_", " ").title()] = df
        else:
            formatted_key = key.replace("_", " ").title()
            extracted_data[formatted_key] = value.value_string if value.value_string else "N/A"

    return extracted_data

# Function to calculate financial metrics
def calculate_metrics(balance_df):
    amount_columns = [col for col in balance_df.columns if re.match(r"Amount(_\d+)?", col, re.IGNORECASE)]
    date_columns = [col for col in balance_df.columns if re.match(r"Date(_\d+)?", col, re.IGNORECASE)]
    
    if not amount_columns:
        return "N/A", "N/A", "N/A"

    for col in amount_columns:
        balance_df[col] = balance_df[col].astype(str).str.replace(r'[^\d.-]', '', regex=True)
        balance_df[col] = pd.to_numeric(balance_df[col], errors="coerce").fillna(0)

    valid_amounts = []
    for date_col, amount_col in zip(date_columns, amount_columns):
        valid_rows = (balance_df[date_col] != "N/A")
        valid_amounts.extend(balance_df.loc[valid_rows, amount_col].tolist())

    avg_daily_balance = round(sum(valid_amounts) / len(valid_amounts), 2) if valid_amounts else "N/A"
    total_negative_days = (balance_df[amount_columns] < 0).any(axis=1).sum()
    total_transactions = len(valid_amounts)
    avg_negative_days = f"{round((total_negative_days / total_transactions) * 100, 2)}%" if total_transactions > 0 else "N/A"

    return avg_daily_balance, total_negative_days, avg_negative_days

# Function to process uploaded PDFs
def process_uploaded_files(uploaded_files):
    all_extracted_data = {}

    with st.spinner("Processing documents..."):
        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        total_files = len(uploaded_files)

        for i, uploaded_file in enumerate(uploaded_files):
            status_placeholder.text(f"Processing: {uploaded_file.name} ...")
            
            poller = document_intelligence_client.begin_analyze_document(
                model_id=model_id, body=uploaded_file, content_type="application/pdf"
            )
            result = poller.result()

            extracted_data = extract_balance_data(result)

            if "Daily Ending Balance" in extracted_data:
                avg_daily_balance, total_negative_days, avg_negative_days = calculate_metrics(extracted_data["Daily Ending Balance"])
            else:
                avg_daily_balance, total_negative_days, avg_negative_days = "N/A", "N/A", "N/A"

            extracted_data["Average Daily Balance"] = avg_daily_balance
            extracted_data["Total Negative Days"] = total_negative_days
            extracted_data["Average Negative Days"] = avg_negative_days

            all_extracted_data[uploaded_file.name] = extracted_data
            progress_bar.progress((i + 1) / total_files)
            time.sleep(0.5)

        status_placeholder.text("✅ All files processed successfully!")

    return all_extracted_data

# Function to display extracted metrics
def display_results(all_extracted_data):
    for file_name, file_data in all_extracted_data.items():
        st.markdown(f"## 🔹 {file_name}")

        tab1, tab2 = st.tabs(["📊 Summary", "📜 Raw Extracted Data"])

        with tab1:
            col1, col2, col3 = st.columns(3)
            with col1:
                metric_card("Avg. Daily Balance", f"${file_data.get('Average Daily Balance', 'N/A')}", "💰")
            with col2:
                metric_card("Total Negative Days", file_data.get('Total Negative Days', 'N/A'), "📉")
            with col3:
                metric_card("Avg. Negative Days", file_data.get('Average Negative Days', 'N/A'), "📊")

            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if "No.Of.Depositsandadditions" in file_data:
                    metric_card("No. of Deposits and Additions", file_data.get("No.Of.Depositsandadditions", "N/A"), "📥")
            with col2:
                if "Totalamountofdeposits" in file_data:
                    metric_card("Total Amount of Deposits", file_data.get("Totalamountofdeposits", "N/A"), "💵")

        with tab2:
            st.dataframe(file_data.get("Daily Ending Balance", pd.DataFrame()), use_container_width=True)

        st.divider()

# File upload section
st.markdown("### 📤 Upload Bank Statements")
with st.container():
    col1, col2 = st.columns([3, 1])
    with col1:
        uploaded_files = st.file_uploader("Choose PDF files", type=["pdf"], accept_multiple_files=True)
    with col2:
        if uploaded_files:
            st.success(f"✅ {len(uploaded_files)} file(s) uploaded!")

if uploaded_files:
    all_extracted_data = process_uploaded_files(uploaded_files)
    display_results(all_extracted_data)
else:
    st.info("ℹ️ Please upload one or more PDF files to begin the analysis.")
