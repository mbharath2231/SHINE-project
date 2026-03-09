import streamlit as st
import sqlite3
import pandas as pd
import math

st.set_page_config(page_title="SHINE Search Engine", layout="wide")

# # --- CUSTOM CSS ---
# st.markdown("""
#     <style>
#     div.stButton > button {
#         background-color: #333333;
#         color: white;
#         border: none;
#         width: 100%;
#         border-radius: 2px;
#     }
#     div.stButton > button:hover {
#         background-color: #555555;
#         color: white;
#     }
#     .block-container {
#         border: 1px solid #cccccc;
#         padding: 2rem !important;
#         margin-top: 2rem;
#     }
#     </style>
# """, unsafe_allow_html=True)

# --- STATE MANAGEMENT (Crucial for Pagination) ---
if 'page' not in st.session_state:
    st.session_state.page = 1

# --- DATABASE CONNECTION ---
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
        st.error(f"Database connection failed: {e}")
        return pd.DataFrame()

df_main = load_data()
if df_main.empty:
    st.error("CRITICAL ERROR: shine.db is missing or empty.")
    st.stop()

# --- HELPER FUNCTIONS ---
def map_field_to_col(ui_field):
    mapping = {
        "Author": "author", "Title": "title", "Publication Year": "year",
        "Publisher Info": "venue", "Keywords": "keywords", "Journal Title": "venue"
    }
    return mapping.get(ui_field)

def apply_match(df, col, term, match_type):
    """Handles Wildcard vs Starts With vs Ends With"""
    if not term:
        return pd.Series([True] * len(df)) # Return all if blank
        
    term = str(term).lower()
    col_data = df[col].astype(str).str.lower()
    
    if match_type == "Starts With":
        return col_data.str.startswith(term, na=False)
    elif match_type == "Ends With":
        return col_data.str.endswith(term, na=False)
    else: # Wildcard / Contains
        return col_data.str.contains(term, na=False)

# --- UI: SEARCH FORMS ---
st.title("Search SHINE Database")

# 1. BASIC SEARCH BLOCK
with st.container(border=True):
    st.markdown("**Basic Search:**")
    basic_term = st.text_input("Search term", key="basic_term", label_visibility="collapsed")
    
    col_type, col_sort = st.columns([2, 2])
    with col_type:
        basic_match = st.radio("Search Type:", ["Wildcard", "Starts With", "Ends With"], horizontal=True, key="basic_match")
    with col_sort:
        basic_sort = st.selectbox("Order Results By:", ["Author", "Publication Date: Newest First", "Publication Date: Oldest First", "Title"], key="basic_sort")
    
    if st.button("Basic Search"):
        st.session_state.page = 1 # Reset to page 1 on new search

# 2. CUSTOM SEARCH BLOCK
with st.container(border=True):
    st.markdown("**Custom Search**")
    boolean_logic = st.radio("Search For:", ["All Terms (Boolean AND)", "Any Terms (Boolean OR)"], horizontal=True)
    
    # Row 1
    c1, c2, c3 = st.columns([2, 1, 4])
    with c1: f1 = st.selectbox("Field 1", ["Author", "Title", "Publication Year", "Journal Title", "Keywords", "Annotations"], label_visibility="collapsed")
    with c2: st.selectbox("Condition 1", ["Is"], disabled=True, label_visibility="collapsed") # Dummy dropdown to match UI
    with c3: q1 = st.text_input("Term 1", key="q1", label_visibility="collapsed")
    match1 = st.radio("Type 1", ["Wildcard", "Starts With", "Ends With"], horizontal=True, key="m1", label_visibility="collapsed")
    
    # Row 2
    c1, c2, c3 = st.columns([2, 1, 4])
    with c1: f2 = st.selectbox("Field 2", ["Author", "Title", "Publication Year", "Journal Title", "Keywords", "Annotations"], index=1, label_visibility="collapsed")
    with c2: st.selectbox("Condition 2", ["Is"], disabled=True, label_visibility="collapsed", key="cond2")
    with c3: q2 = st.text_input("Term 2", key="q2", label_visibility="collapsed")
    match2 = st.radio("Type 2", ["Wildcard", "Starts With", "Ends With"], horizontal=True, key="m2", label_visibility="collapsed")

    custom_sort = st.selectbox("Order Custom Results By:", ["Author", "Publication Date: Newest First", "Publication Date: Oldest First", "Title"], key="custom_sort")

    if st.button("Custom Search"):
        st.session_state.page = 1

# --- RESULTS PER PAGE UI ---
with st.container(border=True):
    st.markdown("**Results Per Page:**")
    col_per_page, col_update = st.columns([3, 1])
    with col_per_page:
        results_per_page = st.selectbox("Count", [10, 25, 50, 100], index=1, label_visibility="collapsed")
    with col_update:
        if st.button("Update Pagination"):
            st.session_state.page = 1

# --- FILTERING LOGIC ---
results = df_main.copy()

# Apply Basic Search
if basic_term:
    text_cols = ['title', 'author', 'venue', 'summary_part1', 'summary_part2', 'keywords']
    results['combined_text'] = results[text_cols].astype(str).agg(' '.join, axis=1)
    mask = apply_match(results, 'combined_text', basic_term, basic_match)
    results = results[mask].drop(columns=['combined_text'])
    sort_option = basic_sort

# Apply Custom Search (Only if Basic is empty)
elif q1 or q2:
    mask1 = pd.Series([False] * len(results)) if boolean_logic == "Any Terms (Boolean OR)" else pd.Series([True] * len(results))
    mask2 = mask1.copy()
    
    if q1:
        if f1 == "Annotations":
            m_a = apply_match(results, 'summary_part1', q1, match1)
            m_b = apply_match(results, 'summary_part2', q1, match1)
            mask1 = m_a | m_b
        else:
            mask1 = apply_match(results, map_field_to_col(f1), q1, match1)
            
    if q2:
        if f2 == "Annotations":
            m_a = apply_match(results, 'summary_part1', q2, match2)
            m_b = apply_match(results, 'summary_part2', q2, match2)
            mask2 = m_a | m_b
        else:
            mask2 = apply_match(results, map_field_to_col(f2), q2, match2)
            
    if boolean_logic == "All Terms (Boolean AND)":
        final_mask = mask1 & mask2 if q1 and q2 else (mask1 if q1 else mask2)
    else: # OR
        final_mask = mask1 | mask2
        
    results = results[final_mask]
    sort_option = custom_sort
else:
    sort_option = basic_sort # Default

# Apply Sorting
if sort_option == "Author":
    results = results.sort_values(by="author", ascending=True)
elif sort_option == "Publication Date: Newest First":
    results = results.sort_values(by="year", ascending=False)
elif sort_option == "Publication Date: Oldest First":
    results = results.sort_values(by="year", ascending=True)
elif sort_option == "Title":
    results = results.sort_values(by="title", ascending=True)


# --- PAGINATION MATHEMATICS ---
total_records = len(results)
total_pages = math.ceil(total_records / results_per_page) if total_records > 0 else 1

# Ensure current page doesn't exceed total pages if user changes filters
if st.session_state.page > total_pages:
    st.session_state.page = total_pages

start_idx = (st.session_state.page - 1) * results_per_page
end_idx = start_idx + results_per_page
paginated_results = results.iloc[start_idx:end_idx]


# --- DISPLAY FORMATTED RESULTS ---
st.markdown(f"### Search Results")
st.markdown(f"Your search found **{total_records}** citations. Showing page **{st.session_state.page}** of **{total_pages}**.")
st.markdown("---")

if not paginated_results.empty:
    for index, row in enumerate(paginated_results.itertuples(), start=start_idx + 1):
        # 1. Clean the Author & Year
        author = row.author if pd.notna(row.author) and str(row.author).strip() != "" else "Unknown Author"
        
        if pd.notna(row.year):
            try: year_str = f"({int(row.year)})"
            except ValueError: year_str = f"({row.year})"
        else: year_str = "(n.d.)"
            
        # 2. Clean the Title & Venue
        title = row.title if pd.notna(row.title) else "Untitled"
        venue = f"<i>{row.venue}</i>" if pd.notna(row.venue) and row.venue != "Not Provided" else ""
        
        # 3. Handle the URL cleanly for HTML (Lighter blue for Dark Mode)
        url_html = ""
        url = row.url if pd.notna(row.url) and row.url not in ["Not Provided", "N/A"] else ""
        if url:
            if url.startswith("http"): 
                url_html = f'<div style="margin-top: 2px;"><a href="{url}" target="_blank" style="color: #4da6ff; text-decoration: none;">{url}</a></div>'
            else: 
                url_html = f'<div style="margin-top: 2px; color: #4da6ff;">{url}</div>'
                
        # 4. Clean Keywords
        keywords = row.keywords if pd.notna(row.keywords) and row.keywords != "Not Provided" else "None listed"
        
        # 5. THE HTML TEMPLATE: No hardcoded text colors, letting Streamlit's native white text take over
        result_html = (
            f'<div style="margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid rgba(255,255,255,0.2); font-family: sans-serif; line-height: 1.5;">'
            f'<div style="font-size: 16px;">{index}. {author}. {year_str}. {title}. {venue}.</div>'
            f'{url_html}'
            f'<div style="margin-top: 6px; font-size: 14.5px; opacity: 0.7;"><strong>Keywords:</strong> {keywords}</div>'
            f'</div>'
        )
        
        # Render the raw HTML block
        st.markdown(result_html, unsafe_allow_html=True)
else:
    st.info("No results found. Try adjusting your search terms.")

# --- PAGINATION CONTROLS (BOTTOM OF PAGE) ---
st.markdown("---")
col_prev, col_page, col_next = st.columns([1, 2, 1])

with col_prev:
    if st.button("⬅️ Previous Page", disabled=(st.session_state.page == 1)):
        st.session_state.page -= 1
        st.rerun()

with col_page:
    # Instead of 20 separate buttons, we use a clean dropdown to jump to any page
    jump_page = st.selectbox("Jump to page:", range(1, total_pages + 1), index=st.session_state.page - 1, label_visibility="collapsed")
    if jump_page != st.session_state.page:
        st.session_state.page = jump_page
        st.rerun()

with col_next:
    if st.button("Next Page ➡️", disabled=(st.session_state.page == total_pages)):
        st.session_state.page += 1
        st.rerun()