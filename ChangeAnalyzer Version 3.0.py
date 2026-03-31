import streamlit as st
import pandas as pd
from io import BytesIO
from openai import OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

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

    # ------------------ NEW / REMOVED ------------------
    merged = df_prev.merge(df_curr, on=primary_key, how='outer', indicator=True)
    new_records = df_curr[merged['_merge'] == 'right_only']
    removed_records = df_prev[merged['_merge'] == 'left_only']

    # ------------------ COMMON ------------------
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

    # ------------------ ALL CHANGES ------------------
    all_changes = pd.DataFrame(index=modified_records.index)

    for col in df_prev.columns:
        all_changes[f"Prev_{col}"] = df_prev.loc[modified_records.index, col].where(modified_mask[col])
        all_changes[f"Curr_{col}"] = df_curr.loc[modified_records.index, col].where(modified_mask[col])

    all_changes.reset_index(inplace=True)

    # ------------------ FULL SUMMARY ------------------
    full_summary = []
    all_keys = df_prev.index.union(df_curr.index)

    for key in all_keys:

        if key in df_prev.index and key in df_curr.index:
            changes_from = []
            changes_to = []
            changed_cols = []

            for col in df_prev.columns:
                prev_val = df_prev.loc[key, col]
                curr_val = df_curr.loc[key, col]

                if pd.isna(prev_val) and pd.isna(curr_val):
                    continue

                if prev_val != curr_val:
                    changes_from.append(str(prev_val))
                    changes_to.append(str(curr_val))
                    changed_cols.append(col)

            if changes_from:
                change_flag = "Yes"
                from_text = " | ".join(changes_from)
                to_text = " | ".join(changes_to)
                cols_text = " | ".join(changed_cols)
            else:
                change_flag = "No"
                from_text = "-"
                to_text = "-"
                cols_text = "-"

            row_data = df_curr.loc[key].to_dict()
            row_data[primary_key] = key
            row_data["Change"] = change_flag
            row_data["Changed Columns"] = cols_text
            row_data["From"] = from_text
            row_data["To"] = to_text

            full_summary.append(row_data)

        elif key in df_curr.index:
            row_data = df_curr.loc[key].to_dict()
            row_data[primary_key] = key
            row_data["Change"] = "Yes"
            row_data["Changed Columns"] = "-"
            row_data["From"] = "-"
            row_data["To"] = "New Record"
            full_summary.append(row_data)

        elif key in df_prev.index:
            row_data = df_prev.loc[key].to_dict()
            row_data[primary_key] = key
            row_data["Change"] = "Yes"
            row_data["Changed Columns"] = "-"
            row_data["From"] = "Removed Record"
            row_data["To"] = "-"
            full_summary.append(row_data)

    full_summary_df = pd.DataFrame(full_summary)

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
        "all_changes": all_changes,
        "full_summary": full_summary_df
    }

# ------------------ INSIGHTS ------------------

def generate_insights(results):

    summary = results["summary"]
    detailed = results["detailed_changes"]

    insights = {}
    total_curr = summary["Total Current Records"]

    insights["% New Records"] = round((summary["New Records"] / total_curr) * 100, 2) if total_curr else 0
    insights["% Removed Records"] = round((summary["Removed Records"] / total_curr) * 100, 2) if total_curr else 0
    insights["% Modified Records"] = round((summary["Modified Records"] / total_curr) * 100, 2) if total_curr else 0
    insights["% Unchanged Records"] = round((summary["Unchanged Records"] / total_curr) * 100, 2) if total_curr else 0

    if not detailed.empty:
        col_changes = detailed["Column"].value_counts().reset_index()
        col_changes.columns = ["Column", "Change Count"]
    else:
        col_changes = pd.DataFrame(columns=["Column", "Change Count"])

    observations = []

    if insights["% Modified Records"] > 50:
        observations.append("⚠️ More than 50% of records were modified.")
    elif insights["% Modified Records"] > 20:
        observations.append("⚠️ Significant number of records were modified.")

    if insights["% New Records"] > 10:
        observations.append("🆕 High number of new records added.")

    if insights["% Removed Records"] > 10:
        observations.append("❌ High number of records removed.")

    if insights["% Unchanged Records"] > 80:
        observations.append("✅ Majority of data remains unchanged.")

    if not col_changes.empty:
        observations.append(f"🔍 Most changed column: {col_changes.iloc[0]['Column']}")

    insights_text = "\n".join(observations) if observations else "No major anomalies detected."

    return insights, col_changes, insights_text

# ------------------ EXCEL DOWNLOAD ------------------

def create_excel_download(results, insights, col_changes):

    output = BytesIO()

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:

        pd.DataFrame([results["summary"]]).to_excel(writer, sheet_name="Summary", index=False)

        results["new_records"].to_excel(writer, sheet_name="New Records", index=False)
        results["removed_records"].to_excel(writer, sheet_name="Removed Records", index=False)
        results["modified_records"].to_excel(writer, sheet_name="Modified Records", index=False)
        results["unchanged_records"].to_excel(writer, sheet_name="Unchanged Records", index=False)
        results["detailed_changes"].to_excel(writer, sheet_name="Detailed Changes", index=False)
        results["all_changes"].to_excel(writer, sheet_name="All Changes", index=False)
        results["full_summary"].to_excel(writer, sheet_name="Full Summary", index=False)

        pd.DataFrame([insights]).to_excel(writer, sheet_name="Insights", index=False)
        col_changes.to_excel(writer, sheet_name="Column Changes", index=False)

    output.seek(0)
    return output


#-------------------OpenAI Magic -----------------------

def generate_ai_insights(results, insights, col_changes):

    try:
        summary = results["summary"]

        # Prepare input text
        input_text = f"""
Dataset Context: Generic Dataset

Summary:
Total Previous Records: {summary['Total Previous Records']}
Total Current Records: {summary['Total Current Records']}
New Records: {summary['New Records']}
Removed Records: {summary['Removed Records']}
Modified Records: {summary['Modified Records']}
Unchanged Records: {summary['Unchanged Records']}

Percentages:
New: {insights['% New Records']}%
Removed: {insights['% Removed Records']}%
Modified: {insights['% Modified Records']}%
Unchanged: {insights['% Unchanged Records']}%

Top Changed Columns:
{col_changes.head(5).to_string(index=False)}
"""

        # OpenAI call
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a data analyst."},
                {"role": "user", "content": f"""
Analyze the dataset comparison below and provide:

- Key insights
- Risks or anomalies
- Possible reasons for changes

Keep it concise and in bullet points.

{input_text}
"""}
            ],
            temperature=0.3
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"⚠️ AI insights could not be generated: {e}"

# ------------------ STREAMLIT UI ------------------

st.set_page_config(page_title="Excel Comparator", layout="wide")

st.title("📊 Excel Dataset Comparator")

col1, col2 = st.columns(2)

with col1:
    file_prev = st.file_uploader("Upload Previous Dataset", type=["xlsx"])

with col2:
    file_curr = st.file_uploader("Upload Current Dataset", type=["xlsx"])

primary_key = st.text_input("Enter Primary Key Column")

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

                    st.subheader("📌 Summary")
                    st.json(results["summary"])

                    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
                        "New Records",
                        "Removed Records",
                        "Modified Records",
                        "Unchanged Records",
                        "Detailed Changes",
                        "All Changes",
                        "📋 Full Summary",
                        "🧠 Insights",
                        "📥 Downloads",
                        "🤖 AI Insights"
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

                    with tab6:
                        st.dataframe(results["all_changes"], use_container_width=True)

                    with tab7:
                        st.dataframe(results["full_summary"], use_container_width=True)

                    with tab8:
                        st.subheader("🧠 Dataset Insights")

                        insights, col_changes, insights_text = generate_insights(results)

                        st.markdown("### 📊 Change Percentages")
                        st.json(insights)

                        st.markdown("### 🔍 Key Observations")
                        st.write(insights_text)

                        st.markdown("### 📈 Most Changed Columns")
                        st.dataframe(col_changes, use_container_width=True)

                    with tab9:
                        st.subheader("📥 Download Results")

                        insights, col_changes, _ = generate_insights(results)

                        excel_file = create_excel_download(results, insights, col_changes)

                        st.download_button(
                            label="⬇️ Download Full Analysis (Excel)",
                            data=excel_file,
                            file_name=f"comparison_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

                        st.info("This file contains all comparison results across multiple sheets.")

                    with tab10:
                            st.subheader("🤖 AI-Powered Insights")

                            st.info("This section uses AI to analyze dataset changes and generate smart insights.")

                            # Generate insights if not already available
                            insights, col_changes, insights_text = generate_insights(results)

                            with st.spinner("Generating AI insights... 🤖"):
                                ai_text = generate_ai_insights(results, insights, col_changes)
 
                            st.markdown("### 📊 AI Analysis Output")
                            st.write(ai_text)