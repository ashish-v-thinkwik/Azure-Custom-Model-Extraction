import streamlit as st
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
import pandas as pd
import time
import re

# Azure credentials and settings
endpoint = ""
key = ""
model_id = ""

# Initialize Azure Document Intelligence Client
document_intelligence_client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))

st.title("📄 Azure Document Intelligence - Extracted Data")

# Multi-file upload
uploaded_files = st.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    st.success("Files uploaded successfully! Extracting data...")

    # Progress bar for processing
    progress_bar = st.progress(0)
    total_files = len(uploaded_files)
    all_extracted_data = {}

    for i, uploaded_file in enumerate(uploaded_files):
        poller = document_intelligence_client.begin_analyze_document(
            model_id=model_id, body=uploaded_file, content_type="application/pdf"
        )
        result = poller.result()

        extracted_data = {}

        # Loop through detected fields in JSON response
        for key, value in result.documents[0].fields.items():
            if value.type == "array":
                item_list = []
                for item in value.value_array:
                    data = item.value_object  
                    extracted_entry = {field: data.get(field, {}).get("valueString", "N/A") for field in data.keys()}
                    item_list.append(extracted_entry)

                df = pd.DataFrame(item_list)

                # If table matches "DailyEndingBalance" structure, process balances
                if "DailyEndingBalance" in key:
                    extracted_data["DailyEndingBalance"] = df

                extracted_data[key] = df

            else:
                extracted_data[key] = value.value_string if value.value_string else "N/A"

        # If "DailyEndingBalance" exists, compute metrics
        if "DailyEndingBalance" in extracted_data:
            balance_df = extracted_data["DailyEndingBalance"]

            # Extract all "AMOUNT" columns dynamically
            amount_columns = [col for col in balance_df.columns if re.match(r"AMOUNT(_\d+)?", col)]

            if amount_columns:
                # Convert balances to numeric (remove "$", ",") and handle errors
                for col in amount_columns:
                    balance_df[col] = balance_df[col].replace('[\$,]', '', regex=True)  # Remove currency symbols
                    balance_df[col] = pd.to_numeric(balance_df[col], errors="coerce").fillna(0)  # Convert to float

                # Compute Average Daily Balance
                all_amounts = balance_df[amount_columns].values.flatten()
                all_amounts = all_amounts[all_amounts != 0]  # Remove zero balances if they represent missing data
                avg_daily_balance = all_amounts.mean() if len(all_amounts) > 0 else 0

                # Compute Negative Days (any column with a negative balance)
                negative_days = (balance_df[amount_columns] < 0).any(axis=1).sum()
            else:
                avg_daily_balance, negative_days = "N/A", "N/A"
        else:
            avg_daily_balance, negative_days = "N/A", "N/A"

        # Store computed results
        extracted_data["Average Daily  Balance"] = avg_daily_balance
        extracted_data["Negative Days"] = negative_days

        all_extracted_data[f"File {i+1}"] = extracted_data

        # Update progress bar
        progress_bar.progress((i + 1) / total_files)

        time.sleep(1)

    # Display extracted results
    for file_name, file_data in all_extracted_data.items():
        st.subheader(f"🔹 {file_name}")
        for field_name, data in file_data.items():
            if isinstance(data, pd.DataFrame):
                st.subheader(f"📌 {field_name}")
                st.dataframe(data)
            else:
                st.markdown(f"**{field_name}:** {data}")

else:
    st.info("Please upload one or more PDF files for extraction.")