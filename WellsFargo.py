import streamlit as st
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
import pandas as pd
import io
import os 
from dotenv import load_dotenv
load_dotenv()
# Azure Document Intelligence Configuration
key = os.getenv("key")
endpoint = os.getenv("endpoint")
model_id = os.getenv("model_id2")

document_intelligence_client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))

def extract_data_from_pdf(file_bytes):
    """Extract transaction details including deposit counts and total deposit amount from a PDF."""
    deposit_counts = {"TranscationHistory_page1": 0, "TranscationHistory_page2": 0}
    total_deposits = {"TranscationHistory_page1": 0.0, "TranscationHistory_page2": 0.0}  

    try:
        poller = document_intelligence_client.begin_analyze_document(
            model_id=model_id, body=io.BytesIO(file_bytes), content_type="application/pdf"
        )
        result = poller.result()

        if hasattr(result, "documents") and result.documents:
            doc = result.documents[0]

            for key, value in doc.fields.items():
                if key in ["TranscationHistory_page1", "TranscationHistory_page2"]:  
                    item_list = []
                    for item in value.value_array:
                        data = item.value_object
                        extracted_entry = {field: data.get(field, {}).get("valueString", "N/A") for field in data.keys()}
                        item_list.append(extracted_entry)

                    df = pd.DataFrame(item_list)

                    # Convert numeric columns safely
                    df = df.apply(lambda col: pd.to_numeric(col.astype(str).str.replace(",", ""), errors="coerce") if col.dtype == 'object' else col)

                    # Identify deposit-related columns
                    deposit_columns = [col for col in df.columns if "deposit" in col.lower() or "credit" in col.lower()]

                    # Count valid deposit entries and sum total deposits
                    for col in deposit_columns:
                        df[col] = df[col].replace("N/A", None)  # Handle missing values
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                        
                        deposit_counts[key] += df[col].dropna().astype(bool).sum()  # Count deposits
                        total_deposits[key] += df[col].dropna().sum()  # Sum deposit amounts

    except Exception as e:
        st.error(f"⚠️ Error processing file: {e}")

    return deposit_counts, total_deposits

# Streamlit UI
st.set_page_config(page_title="Bank Statement Analysis", page_icon="📄", layout="wide")
st.title("📄 Loot Intelligence")

uploaded_files = st.file_uploader("Upload Bank Statements", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    st.success("Files uploaded successfully! Extracting data...")

    progress_bar = st.progress(0)
    total_files = len(uploaded_files)
    all_extracted_data = {}

    # Store extracted ending balances data
    ending_balance_summary = []
    balance_aggregates = []

    for i, uploaded_file in enumerate(uploaded_files):
        file_bytes = uploaded_file.read()  
        ending_balances = []  

        try:
            poller = document_intelligence_client.begin_analyze_document(
                model_id=model_id, body=io.BytesIO(file_bytes), content_type="application/pdf"
            )
            result = poller.result()
            extracted_data = {}

            if hasattr(result, "documents") and result.documents:
                doc = result.documents[0]

                for key, value in doc.fields.items():
                    if value.type == "array":
                        item_list = []
                        for item in value.value_array:
                            data = item.value_object  
                            extracted_entry = {field: data.get(field, {}).get("valueString", "N/A") for field in data.keys()}
                            item_list.append(extracted_entry)

                        df = pd.DataFrame(item_list)

                        if "Ending daily balance" in df.columns:
                            df["Ending daily balance"] = pd.to_numeric(df["Ending daily balance"].str.replace(",", ""), errors="coerce")
                            ending_balances.extend(df["Ending daily balance"].dropna().tolist())

                        extracted_data[key] = df  
                    else:
                        extracted_data[key] = value.value_string if value.value_string else "N/A"

                all_extracted_data[uploaded_file.name] = extracted_data

                # Extract deposit counts & total deposit amounts
                deposit_counts, total_deposits = extract_data_from_pdf(file_bytes)

            else:
                st.warning(f"No data extracted from {uploaded_file.name}")

        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")

        # Store balance summaries
        if ending_balances:
            total_balance = sum(ending_balances)
            mean_balance = total_balance / len(ending_balances)
            negative_days = sum(1 for balance in ending_balances if balance < 0)

            # Compute Average Negative Days (%)
            if len(ending_balances) > 1:
                total_count_excluding_last = len(ending_balances) - 1
                avg_negative_days = (negative_days / total_count_excluding_last) * 100 if total_count_excluding_last > 0 else 0
            else:
                avg_negative_days = 0

            ending_balance_summary.append({
                "File Name": uploaded_file.name,
                "Total Count": len(ending_balances)
            })

            balance_aggregates.append({
                "File Name": uploaded_file.name,
                "Total Balance ": sum(ending_balances[:-1]) if len(ending_balances) > 1 else "N/A",
                "Average Balance ": (sum(ending_balances[:-1]) / len(ending_balances[:-1])) if len(ending_balances) > 1 else "N/A"
            })

        with st.expander(f"📊 Balance Summary for {uploaded_file.name}"):
            if balance_aggregates:
                
                df_balances = pd.DataFrame(balance_aggregates)
                st.table(df_balances)

            if ending_balances:
                st.write(f"**Negative Days Count:** {negative_days}")
                st.write(f"**Average Negative Days (%):** {round(avg_negative_days, 2)}%")
            else:
                st.write("No valid ending balance data found.")

        # Display deposit details
        with st.expander(f"💰 Deposit Details for {uploaded_file.name}"):
            st.write("### Deposits Identified:")
            total_deposits_count = sum(deposit_counts.values())  
            total_deposits_amount = sum(total_deposits.values())  

            for page, count in deposit_counts.items():
                st.write(f"**{page}:** {count} deposit(s) - ${total_deposits[page]:,.2f}")

            st.write(f"### 🏦 **No.of.Deposits:** {total_deposits_count}")
            st.write(f"### 🏦 **Total Amount of Deposits:** ${total_deposits_amount:,.2f}")

        progress_bar.progress((i + 1) / total_files)

    for file_name, file_data in all_extracted_data.items():
        with st.expander(f"📄 Extracted Data from {file_name}"):
            for field_name, data in file_data.items():
                if isinstance(data, pd.DataFrame):
                    st.subheader(f"📌 {field_name}")
                    st.dataframe(data)
                else:
                    st.markdown(f"**{field_name}:** {data}")

    st.success("✅ Extraction Completed!")

else:
    st.info("📥 Please upload one or more PDF files for extraction.")
