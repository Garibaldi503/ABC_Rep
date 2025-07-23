import streamlit as st
import pandas as pd
import numpy as np
import openai
import os
import io

# ✅ Load OpenAI API key from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

if not openai.api_key:
    st.error("❌ OPENAI_API_KEY not found. Please set it in your environment variables.")
    st.stop()

st.set_page_config(page_title="ABC/XYZ Inventory with ChatGPT", layout="wide")
st.title("📦 ABC/XYZ Inventory Classification with ChatGPT Assistant")

# Upload section
st.sidebar.header("Upload Your Inventory File")
uploaded_file = st.sidebar.file_uploader("Upload Excel or CSV file", type=["xlsx", "csv"])

if uploaded_file:
    # Load file
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    # Ensure required columns
    required_cols = {"item_id", "description", "sales", "qty", "date"}
    if not required_cols.issubset(df.columns):
        st.error(f"Missing columns. Your file must include: {', '.join(required_cols)}")
        st.stop()

    # Optional category column
    category_col = None
    for col in ["category", "Category", "group", "Group", "description"]:
        if col in df.columns:
            category_col = col
            break

    # Data cleaning
    df["date"] = pd.to_datetime(df["date"])
    df["sales"] = pd.to_numeric(df["sales"], errors="coerce").fillna(0)
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0)

    # Allow user to filter by category
    if category_col:
        unique_categories = df[category_col].dropna().unique()
        selected_cat = st.sidebar.selectbox("Select Category to View", ["All"] + sorted(unique_categories.tolist()))
        if selected_cat != "All":
            df = df[df[category_col] == selected_cat]

    # ABC classification
    agg = df.groupby(["item_id", "description"]).agg({"sales": "sum", "qty": "sum"}).reset_index()
    agg = agg.sort_values(by="sales", ascending=False)
    agg["cum_pct"] = agg["sales"].cumsum() / agg["sales"].sum()
    agg["ABC"] = agg["cum_pct"].apply(lambda x: "A" if x <= 0.7 else ("B" if x <= 0.9 else "C"))

    # XYZ classification with 'ME' instead of deprecated 'M'
    monthly_qty = df.groupby(["item_id", pd.Grouper(key="date", freq="ME")])["qty"].sum().reset_index()
    pivot = monthly_qty.pivot(index="item_id", columns="date", values="qty").fillna(0)
    cv = pivot.std(axis=1) / (pivot.mean(axis=1).replace(0, np.nan))
    cv = cv.fillna(0)
    agg = agg.join(cv.rename("CV"), on="item_id")
    agg["XYZ"] = agg["CV"].apply(lambda c: "X" if c <= 0.5 else ("Y" if c <= 1.0 else "Z"))
    agg["ABC_XYZ"] = agg["ABC"] + "/" + agg["XYZ"]

    # ABC/XYZ filter
    unique_abcxyz = agg["ABC_XYZ"].dropna().unique()
    selected_abcxyz = st.sidebar.multiselect("Filter by ABC/XYZ Group", sorted(unique_abcxyz), default=sorted(unique_abcxyz))
    filtered_agg = agg[agg["ABC_XYZ"].isin(selected_abcxyz)]

    # Auto-replenishment suggestion
    st.subheader("📦 Suggested Replenishment Policy")
    replenishment_rules = {
        "A/X": "Reorder weekly with tight safety stock control.",
        "A/Y": "Reorder bi-weekly using smoothed demand forecast.",
        "A/Z": "Manual review monthly with cautious reorder quantity.",
        "B/X": "Reorder bi-weekly with fixed reorder point.",
        "B/Y": "Monitor monthly; reorder with buffer stock.",
        "B/Z": "Review quarterly with manual override.",
        "C/X": "Low-priority reorder, maintain minimum stock.",
        "C/Y": "Replenish only with demand signal.",
        "C/Z": "Do not replenish unless justified by exception."
    }

    filtered_agg.loc[:, "Replenishment Advice"] = filtered_agg["ABC_XYZ"].map(replenishment_rules)

    # Hide ABC, CV, XYZ, and cum_pct from display
    display_cols = [col for col in filtered_agg.columns if col not in ["ABC", "CV", "XYZ", "cum_pct"]]

    # Show result
    st.subheader("📊 ABC/XYZ Classification Result with Replenishment")
    st.dataframe(filtered_agg[display_cols])

    # Download result
    output = io.BytesIO()
    filtered_agg.to_excel(output, index=False, engine="openpyxl")
    output.seek(0)
    st.download_button("📥 Download Classification Excel", data=output, file_name="abc_xyz_analysis.xlsx")

    # ChatGPT assistant popup
    with st.expander("💬 Open ChatGPT Assistant"):
        st.markdown("**Try asking:**")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("- Why are Z items risky?")
            st.markdown("- Should I promote A/X items?")
        with col2:
            st.markdown("- Propose markdown strategy for C/Z.")
            st.markdown("- Suggest replenishment for A/Y.")

        user_input = st.text_area("Ask ChatGPT about your inventory analysis:")
        if st.button("🧠 Get Response"):
            with st.spinner("Thinking..."):
                try:
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "You are an expert inventory management assistant."},
                            {"role": "user", "content": user_input}
                        ]
                    )
                    st.success("Response received:")
                    st.write(response.choices[0].message.content)
                except Exception as e:
                    st.error(f"API error: {e}")
else:
    st.info("Upload an inventory file to get started.")
