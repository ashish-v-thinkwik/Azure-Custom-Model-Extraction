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
model_id= os.getenv("model_id")
# Initialize Azure Document Intelligence Client
document_intelligence_client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))

# Set page configuration
st.set_page_config(
    page_title="Loot Intelligence Dashboard",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Loot Intelligence")

def extract_balance_data(result):
    """Extracts Daily Ending Balance table from Azure Document Intelligence response."""
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

def calculate_metrics(balance_df):
    """Calculates Average Daily Balance, Total Negative Days, and Average Negative Days."""
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

def process_uploaded_files(uploaded_files):
    """Processes uploaded PDFs and extracts financial metrics."""
    all_extracted_data = {}

    with st.spinner("Processing documents..."):
        progress_bar = st.progress(0)
        total_files = len(uploaded_files)

        for i, uploaded_file in enumerate(uploaded_files):
            st.markdown(f"### Processing: {uploaded_file.name}")
            
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

    return all_extracted_data

def display_results(all_extracted_data):
    """Displays extracted financial metrics in Streamlit without tables."""
    for file_name, file_data in all_extracted_data.items():
        st.markdown(f"## 🔹 {file_name}")
        
        # Display extracted metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Average Daily Balance", f"${file_data.get('Average Daily Balance', 'N/A')}")
        with col2:
            st.metric("Total Negative Days", file_data.get('Total Negative Days', 'N/A'))
        with col3:
            st.metric("Average Negative Days", file_data.get('Average Negative Days', 'N/A'))

        # Display extracted textual fields (but no tables)
        for field_name, data in file_data.items():
            if not isinstance(data, pd.DataFrame) and field_name not in ['Average Daily Balance', 'Total Negative Days', 'Average Negative Days']:
                st.markdown(f"**{field_name}:** {data}")
        
        st.markdown("---")  # Add a separator between files

# File upload section
st.markdown("### 📤 Upload Bank Statements")
uploaded_files = st.file_uploader(
    "Choose PDF files",
    type=["pdf"],
    accept_multiple_files=True,
    help="Select multiple PDF files to process them in batch"
)

if uploaded_files:
    st.success(f"✅ {len(uploaded_files)} file(s) uploaded successfully!")
    all_extracted_data = process_uploaded_files(uploaded_files)
    display_results(all_extracted_data)
else:
    st.info("ℹ️ Please upload one or more PDF files to begin the analysis.")
