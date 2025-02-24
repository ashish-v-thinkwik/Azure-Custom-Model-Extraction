import streamlit as st
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
import pandas as pd
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Azure Credentials
key = os.getenv("key")
endpoint = os.getenv("endpoint")
model_id = os.getenv("model_id3")

st.title("📄 Loot Intelligence")

# Initialize Azure Document Intelligence Client
document_intelligence_client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))

# Upload PDF files
uploaded_files = st.file_uploader("Upload Bank Statement files", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    st.success("Files uploaded successfully! Extracting data...")

    # Progress bar
    progress_bar = st.progress(0)
    total_files = len(uploaded_files)
    all_extracted_data = {}

    for i, uploaded_file in enumerate(uploaded_files):
        file_bytes = uploaded_file.read()  # Read file as bytes

        try:
            # Send file to Azure Document Intelligence for analysis
            poller = document_intelligence_client.begin_analyze_document(
                model_id=model_id, body=file_bytes, content_type="application/pdf"
            )
            result = poller.result()
            extracted_data = {}

            # Extract fields from the analyzed document
            if hasattr(result, "documents") and result.documents:
                doc = result.documents[0]

                # Debugging - Show all extracted fields
                #st.write(f"Extracted fields from {uploaded_file.name}:", doc.fields)

                deposit_amount = "N/A"
                number_of_deposits = "N/A"

                for key, value in doc.fields.items():
                    key_lower = key.lower()  # Convert key to lowercase for flexible matching
                    
                    # Extract value safely
                    if isinstance(value, dict) and "valueString" in value:
                        field_value = value["valueString"]
                    elif value.type == "string":
                        field_value = value.value_string
                    elif value.type in ["float", "integer"]:
                        field_value = str(value.value_number)  # Convert numbers to strings
                    else:
                        field_value = "N/A"

                    # Clean up deposit amount (remove commas and convert to float)
                    if key_lower in ["total deposit amount", "depositamount"] and value.confidence > 0.9:
                        deposit_amount = field_value.replace(",", "") if field_value.replace(",", "").replace(".", "").isdigit() else "N/A"
                    
                    elif key_lower in ["number of deposits", "no.of.deposits"] and value.confidence > 0.9:
                        number_of_deposits = field_value

                    # Handle table data
                    elif value.type == "array":
                        item_list = []
                        for item in value.value_array:
                            data = item.value_object
                            extracted_entry = {field: data.get(field, {}).get("valueString", "N/A") for field in data.keys()}
                            item_list.append(extracted_entry)

                        df = pd.DataFrame(item_list)
                        extracted_data[key] = df  # Store table data
                    else:
                        extracted_data[key] = field_value if field_value else "N/A"

                extracted_data["Total Deposit Amount"] = deposit_amount
                extracted_data["Number of Deposits"] = number_of_deposits

                all_extracted_data[uploaded_file.name] = extracted_data
            else:
                st.warning(f"No data extracted from {uploaded_file.name}")

        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")

        # Update progress bar
        progress_bar.progress((i + 1) / total_files)

    # Process and display financial data
    for file_name, file_data in all_extracted_data.items():
        total_balance = 0
        mean_balance = 0
        negative_days = 0
        total_rows = 0  # Track the total number of rows in daily ledger balance
        balance_count = 0

        for field_name, data in file_data.items():
            if isinstance(data, pd.DataFrame):
                # Process Balance Column
                balance_columns = [col for col in data.columns if "Balance" in col]
                if balance_columns:
                    all_balances = pd.to_numeric(data[balance_columns].stack(), errors='coerce').dropna()

                    # Compute metrics
                    total_balance += all_balances.sum()
                    mean_balance += all_balances.mean()
                    negative_days += (all_balances < 0).sum()
                    total_rows += len(all_balances)  # Count total rows
                    balance_count += 1

        # Calculate overall mean balance if any balances were processed
        overall_mean_balance = mean_balance / balance_count if balance_count > 0 else 0

        # Calculate Average Negative Days
        average_negative_days = negative_days / total_rows if total_rows > 0 else 0

        # Display results for each file
        with st.expander(f"📄 Processed Data from {file_name}"):
            st.write(f"**Total Deposit Amount:** ${file_data.get('Total Deposit Amount', 'N/A')}")
            st.write(f"**Number of Deposits:** {file_data.get('Number of Deposits', 'N/A')}")
            st.write(f"**Total Daily Ledger Balance:** ${total_balance:.2f}")
            st.write(f"**Average Daily Ledger Balance:** ${overall_mean_balance:.2f}")
            st.write(f"**Negative Balance Days:** {negative_days}")
            st.write(f"**Average Negative Days:** {average_negative_days * 100:.2f}%")  # Display as a percentage


    st.success("✅ Extraction Completed!")

else:
    st.info("📥 Please upload one or more PDF files for extraction.")
