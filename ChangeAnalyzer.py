import streamlit as st
import pandas as pd
import json
import time

# --- Your existing functions (slightly adjusted) ---

def load_excel(file):
    try:
        return pd.read_excel(file)
    except Exception as e:
        st.error(f"Failed to load file: {e}")
        return None

def validate_schema(df1, df2):
    return set(df1.columns) == set(df2.columns)

def compare_datasets(df_prev, df_curr, primary_key):
    if not validate_schema(df_prev, df_curr):
        st.error("Column headers do not match.")
        return None

    df_prev = df_prev.set_index(primary_key)
    df_curr = df_curr.set_index(primary_key)

    merged = df_prev.merge(df_curr, on=primary_key, how='outer', indicator=True)

    new_records = df_curr[merged['_merge'] == 'right_only']
    removed_records = df_prev[merged['_merge'] == 'left_only']

    common = df_prev.index.intersection(df_curr.index)

    modified_mask = (df_curr.loc[common] != df_prev.loc[common])
    modified_records = df_curr.loc[common][modified_mask.any(axis=1)]
    unchanged_records = df_curr.loc[common][~modified_mask.any(axis=1)]

    summary = {
        "Total Previous Records": len(df_prev),
        "Total Current Records": len(df_curr),
        "New Records": len(new_records),
        "Removed Records": len(removed_records),
        "Modified Records": len(modified_records),
        "Unchanged Records": len(unchanged_records),
    }

    return {
        "summary": summary,
        "new_records": new_records,
        "removed_records": removed_records,
        "modified_records": modified_records,
        "unchanged_records": unchanged_records
    }

# --- Streamlit UI ---

st.title("📊 Excel Dataset Comparator")

file_prev = st.file_uploader("Upload Previous Dataset", type=["xlsx"])
file_curr = st.file_uploader("Upload Current Dataset", type=["xlsx"])

primary_key = st.text_input("Enter Primary Key")

if st.button("Generate Analysis"):
    if not file_prev or not file_curr:
        st.warning("Please upload both files")
    elif not primary_key:
        st.warning("Enter primary key")
    else:
        with st.spinner("Processing..."):
            df_prev = load_excel(file_prev)
            df_curr = load_excel(file_curr)

            results = compare_datasets(df_prev, df_curr, primary_key)

            if results:
                st.success("Analysis Complete")

                st.subheader("Summary")
                st.json(results["summary"])

                st.subheader("New Records")
                st.dataframe(results["new_records"])

                st.subheader("Removed Records")
                st.dataframe(results["removed_records"])

                st.subheader("Modified Records")
                st.dataframe(results["modified_records"])

                st.subheader("Unchanged Records")
                st.dataframe(results["unchanged_records"])