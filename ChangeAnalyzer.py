import streamlit as st
import pandas as pd
import json

# ------------------ FUNCTIONS ------------------

def load_excel(file):
    try:
        return pd.read_excel(file, engine="openpyxl")
    except Exception as e:
        st.error(f"Failed to load file: {e}")
        return None

def validate_schema(df1, df2):
    return set(df1.columns) == set(df2.columns)

def compare_datasets(df_prev, df_curr, primary_key):

    if not validate_schema(df_prev, df_curr):
        st.error("Column headers do not match between datasets.")
        return None

    df_prev = df_prev.set_index(primary_key)
    df_curr = df_curr.set_index(primary_key)

    # New & Removed
    merged = df_prev.merge(df_curr, on=primary_key, how='outer', indicator=True)
    new_records = df_curr[merged['_merge'] == 'right_only']
    removed_records = df_prev[merged['_merge'] == 'left_only']

    # Common
    common = df_prev.index.intersection(df_curr.index)

    modified_mask = (df_curr.loc[common] != df_prev.loc[common])
    modified_records = df_curr.loc[common][modified_mask.any(axis=1)]
    unchanged_records = df_curr.loc[common][~modified_mask.any(axis=1)]

    # ------------------ DETAILED CHANGES ------------------
    detailed_changes = []

    for idx in modified_records.index:
        for col in df_prev.columns:
            if modified_mask.loc[idx, col]:
                detailed_changes.append({
                    "Primary Key": idx,
                    "Column": col,
                    "From": df_prev.loc[idx, col],
                    "To": df_curr.loc[idx, col]
                })

    detailed_changes_df = pd.DataFrame(detailed_changes)

    # ------------------ ALL CHANGES (SIDE BY SIDE) ------------------
    all_changes = pd.DataFrame(index=modified_records.index)

    for col in df_prev.columns:
        all_changes[f"Prev_{col}"] = df_prev.loc[modified_records.index, col].where(modified_mask[col])
        all_changes[f"Curr_{col}"] = df_curr.loc[modified_records.index, col].where(modified_mask[col])

    all_changes.reset_index(inplace=True)

    # ------------------ SUMMARY ------------------
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
        "new_records": new_records.reset_index(),
        "removed_records": removed_records.reset_index(),
        "modified_records": modified_records.reset_index(),
        "unchanged_records": unchanged_records.reset_index(),
        "detailed_changes": detailed_changes_df,
        "all_changes": all_changes
    }

# ------------------ STREAMLIT UI ------------------

st.set_page_config(page_title="Excel Comparator", layout="wide")

st.title("📊 Excel Dataset Comparator")

col1, col2 = st.columns(2)

with col1:
    file_prev = st.file_uploader("Upload Previous Dataset", type=["xlsx"])

with col2:
    file_curr = st.file_uploader("Upload Current Dataset", type=["xlsx"])

primary_key = st.text_input("Enter Primary Key Column")

# ------------------ PROCESS ------------------

if st.button("🚀 Generate Analysis"):

    if not file_prev or not file_curr:
        st.warning("Please upload both files.")
    elif not primary_key:
        st.warning("Please enter a primary key.")
    else:
        with st.spinner("Analyzing datasets..."):

            df_prev = load_excel(file_prev)
            df_curr = load_excel(file_curr)

            if df_prev is not None and df_curr is not None:

                results = compare_datasets(df_prev, df_curr, primary_key)

                if results:

                    st.success("✅ Analysis Completed")

                    # ------------------ SUMMARY ------------------
                    st.subheader("📌 Summary")
                    st.json(results["summary"])

                    # ------------------ TABS ------------------
                    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
                        "New Records",
                        "Removed Records",
                        "Modified Records",
                        "Unchanged Records",
                        "Detailed Changes",
                        "All Changes"
                    ])

                    with tab1:
                        st.dataframe(results["new_records"], use_container_width=True)

                    with tab2:
                        st.dataframe(results["removed_records"], use_container_width=True)

                    with tab3:
                        st.dataframe(results["modified_records"], use_container_width=True)

                    with tab4:
                        st.dataframe(results["unchanged_records"], use_container_width=True)

                    with tab5:
                        st.dataframe(results["detailed_changes"], use_container_width=True)

                        # Filter option
                        if not results["detailed_changes"].empty:
                            st.markdown("### 🔍 Filter by Primary Key")
                            selected_id = st.selectbox(
                                "Select Record",
                                results["detailed_changes"]["Primary Key"].unique()
                            )
                            filtered = results["detailed_changes"][
                                results["detailed_changes"]["Primary Key"] == selected_id
                            ]
                            st.dataframe(filtered, use_container_width=True)

                    with tab6:
                        st.dataframe(results["all_changes"], use_container_width=True)
