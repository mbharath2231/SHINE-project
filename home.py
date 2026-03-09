import streamlit as st
import sqlite3
import pandas as pd

st.set_page_config(page_title = "SHINE Search Engine", layout = "wide")

st.title("SHINE Database - Foundation Test")

@st.cache_data
def load_data():
    try:
        conn = sqlite3.connect("shine.db")
        query = """
            SELECT title, author, year, type, venue, url, 
                   summary_part1, summary_part2, keywords 
            FROM resources
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Database Connection Failed....{e}")
        return pd.DataFrame()
    
df_main = load_data()

if df_main.empty:
    st.error("CRITICAL ERROR: shine.db is missing or empty.")
    st.stop()

# ---------------------------------------------------------
# THE COMPPILE UI REPLICA
# ---------------------------------------------------------

st.markdown("### Basic Search")
basic_search = st.text_input("Search all fields:", key="basic")

st.markdown("---")
st.markdown("### Custom Search")

# Create layout columns to mimic the CompPile side-by-side dropdowns and text boxes
col1, col2 = st.columns([1, 2])

with col1:
    field1 = st.selectbox("Choose Field 1", ["Author", "Title", "Publication Year", "Publisher Info", "Keywords", "Annotations"])
    field2 = st.selectbox("Choose Field 2", ["Author", "Title", "Publication Year", "Publisher Info", "Keywords", "Annotations"], index=1)

with col2:
    query1 = st.text_input("Search Term 1", key="custom1")
    query2 = st.text_input("Search Term 2", key="custom2")

st.markdown("---")
st.markdown("### Order Results By:")
sort_option = st.selectbox("Sort Order", [
    "Author (A-Z)", 
    "Publication Date: Newest First", 
    "Publication Date: Oldest First", 
    "Title (A-Z)"
])

st.markdown("---")
st.button("Search") # Streamlit naturally reruns the script when a button is clicked

# ---------------------------------------------------------
# THE FILTERING ENGINE
# ---------------------------------------------------------

# Start with the full dataset
results = df_main.copy()

# 1. Apply Basic Search (Searches EVERYTHING)
if basic_search:
    # We combine all text columns into one giant hidden string column just for searching
    text_cols = ['title', 'author', 'venue', 'summary_part1', 'summary_part2', 'keywords']
    results['combined_text'] = results[text_cols].astype(str).agg(' '.join, axis=1)
    results = results[results['combined_text'].str.contains(basic_search, case=False, na=False)]
    results = results.drop(columns=['combined_text'])

# 2. Helper function to map UI dropdowns to actual database columns
def map_field_to_col(ui_field):
    mapping = {
        "Author": "author",
        "Title": "title",
        "Publication Year": "year",
        "Publisher Info": "venue",
        "Keywords": "keywords"
    }
    return mapping.get(ui_field)

# 3. Apply Custom Search 1
if query1:
    if field1 == "Annotations":
        # Annotations must search BOTH summary parts
        mask = (results['summary_part1'].str.contains(query1, case=False, na=False) | 
                results['summary_part2'].str.contains(query1, case=False, na=False))
        results = results[mask]
    else:
        db_col = map_field_to_col(field1)
        results = results[results[db_col].astype(str).str.contains(query1, case=False, na=False)]

# 4. Apply Custom Search 2
if query2:
    if field2 == "Annotations":
        mask = (results['summary_part1'].str.contains(query2, case=False, na=False) | 
                results['summary_part2'].str.contains(query2, case=False, na=False))
        results = results[mask]
    else:
        db_col = map_field_to_col(field2)
        results = results[results[db_col].astype(str).str.contains(query2, case=False, na=False)]

# 5. Apply Sorting
if sort_option == "Author (A-Z)":
    results = results.sort_values(by="author", ascending=True)
elif sort_option == "Publication Date: Newest First":
    results = results.sort_values(by="year", ascending=False)
elif sort_option == "Publication Date: Oldest First":
    results = results.sort_values(by="year", ascending=True)
elif sort_option == "Title (A-Z)":
    results = results.sort_values(by="title", ascending=True)

# ---------------------------------------------------------
# DISPLAY RAW RESULTS (Step 2 Testing)
# ---------------------------------------------------------

# ---------------------------------------------------------
# DISPLAY FORMATTED RESULTS (CompPile Style)
# ---------------------------------------------------------

st.markdown(f"**Search Results:** Your search found {len(results)} citations.")
st.markdown("---")

if not results.empty:
    # Loop through the filtered dataframe row by row
    for index, row in enumerate(results.itertuples(), start=1):
        
        # 1. Clean the Author
        author = row.author if pd.notna(row.author) and str(row.author).strip() != "" else "Unknown Author"
        
        # 2. Clean the Year (Prevent "2022.0" float formatting)
        if pd.notna(row.year):
            try:
                year_str = f"({int(row.year)})"
            except ValueError:
                year_str = f"({row.year})"
        else:
            year_str = "(n.d.)" # No date
            
        # 3. Clean the Title & Venue
        title = row.title if pd.notna(row.title) else "Untitled"
        venue = f"*{row.venue}*" if pd.notna(row.venue) and row.venue != "Not Provided" else ""
        
        # 4. Clean the URL
        url = row.url if pd.notna(row.url) and row.url != "Not Provided" and row.url != "N/A" else ""
        
        # --- RENDER THE CITATION BLOCK ---
        
        # Build the main APA string
        citation = f"{index}. {author}. {year_str}. {title}. {venue}."
        st.markdown(citation)
        
        # Add the URL on a new line if it exists
        if url:
            # Check if it actually looks like a link
            if url.startswith("http"):
                st.markdown(f"[{url}]({url})")
            else:
                st.markdown(url)
                
        # Add the Keywords line
        keywords = row.keywords if pd.notna(row.keywords) and row.keywords != "Not Provided" else "None listed"
        st.markdown(f"**Keywords:** {keywords}")
        
        # Add visual spacing between results
        st.markdown("<br>", unsafe_allow_html=True)
else:
    st.info("No results found. Try adjusting your search terms.")