import pandas as pd
import sqlite3
import os

PUBLIC_FILE = "Data/public.xlsx"
HANNAH_FILE = "Data/hannah_intake.xlsx"
DB_NAME = "shine.db"

def load_messy_excel(filepath, sheet_name=None):
    """Dynamically finds the header row instead of guessing."""
    if sheet_name:
        df = pd.read_excel(filepath, sheet_name=sheet_name, header=None)
    else:
        df = pd.read_excel(filepath, header=None)
        
    # Scan the first 15 rows to find the actual headers
    header_idx = 0
    for i in range(min(15, len(df))):
        row_vals = df.iloc[i].astype(str).str.lower().str.strip().tolist()
        if 'title' in row_vals or 'title of text:' in row_vals:
            header_idx = i
            break
            
    # Apply the correct headers and drop the garbage above them
    df.columns = df.iloc[header_idx].astype(str).str.strip()
    df = df.iloc[header_idx+1:].reset_index(drop=True)
    return df

def run_basic_etl():
    print(f"1. Reading the Data from {PUBLIC_FILE}...")
    if not os.path.exists(PUBLIC_FILE):
        print(f"ERROR: File not Found at {PUBLIC_FILE}. Stop here and fix your file paths")
        return
    
    df_public = load_messy_excel(PUBLIC_FILE)
    df_public['source_file'] = 'Public Archive'
    all_dataframes = [df_public]

    print(f"Opening the Workbook...{HANNAH_FILE}")
    hannah_xls = pd.ExcelFile(HANNAH_FILE)

    for sheet in hannah_xls.sheet_names:
        print(f"      - Extracting tab: {sheet}")
        try:
            df_sheet = load_messy_excel(HANNAH_FILE, sheet_name=sheet)
            df_sheet['source_file'] = f'Hannah Archive - {sheet}'
            all_dataframes.append(df_sheet)
        except Exception as e:
            print(f"      - Skipping {sheet}: {e}")

    print("2. Standardising the Column Names...Schema Mapping")
    
    # Notice these keys are all completely LOWERCASE to prevent mismatch errors
    public_mapping = {
        'title': 'title',
        'author(s)': 'author',
        'year of pub': 'year',
        'type': 'type',
        'publisher:': 'venue',
        'doi or url if possible': 'url',
        'this text is about:': 'summary_part1',
        'the author(s) argue/report on:': 'summary_part2',
        'please check 3-5 key words': 'keywords'
    }

    hannah_mapping = {
        'title of text:': 'title',
        'text author(s) [ex: janeway, k. for one author] or  [burnham, m., sisko, b., & pike, c. for multiple authors]': 'author',
        'year of publication:': 'year',
        'select type of text:': 'type',
        'publisher:': 'venue',
        'doi or url (if possible - if not possible, put n/a):': 'url',
        'this text is about _.': 'summary_part1',
        'the author(s) argue/report on _.': 'summary_part2',
        'please check 3-5 key words': 'keywords',
        'email address': 'submitter_email',
        'your first name:': 'submitter_fname',
        'your last name:': 'submitter_lname',
        'your institution/organization:': 'organization'
    }

    clean_dfs = []
    for df in all_dataframes:
        if df.empty:
            continue
            
        # Temporarily save the source file string before we lowercase the columns
        original_source = df['source_file'].iloc[0] if 'source_file' in df.columns else 'Unknown'
        
        # Make ALL columns lowercase and strip spaces so they match our dictionaries perfectly
        df.columns = df.columns.astype(str).str.lower().str.strip()
        
        if 'title of text:' in df.columns:
            print(f"      -> Applied Hannah Mapping to: {original_source}")
            df = df.rename(columns=hannah_mapping)
        elif 'title' in df.columns:
            print(f"      -> Applied Public Mapping to: {original_source}")
            df = df.rename(columns=public_mapping)
        else:
            print(f"      -> WARNING: Unrecognized schema in {original_source}. Available columns: {list(df.columns)}")
            
        # Re-capitalize the source_file column name since we just lowercased everything
        if 'source_file' in df.columns:
            df['source_file'] = original_source
            
        if 'submitter_fname' in df.columns and 'submitter_lname' in df.columns:
            s1 = df['submitter_fname'].fillna('').astype(str)
            s2 = df['submitter_lname'].fillna('').astype(str)
            df['submitter_name'] = (s1 + " " + s2).str.strip()
            df.loc[df['submitter_name'] == '', 'submitter_name'] = 'N/A'
        else:
            df['submitter_name'] = 'N/A'
            
        clean_dfs.append(df)

    print("3. Merging datasets together...")
    df_master = pd.concat(clean_dfs, ignore_index=True)

    from datetime import datetime
    df_master['date_added'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    target_columns = ['title', 'author', 'year', 'type', 'venue', 'url', 'summary_part1', 'summary_part2', 'keywords', 'submitter_name', 'submitter_email', 'organization', 'source_file', 'date_added']
    
    for col in target_columns:
        if col not in df_master.columns:
            df_master[col] = "N/A"
    
    text_cols = [
        'author', 'type', 'venue', 'url', 'summary_part1', 
        'summary_part2', 'keywords', 'organization', 'submitter_email'
    ]
    for col in text_cols:
        # Fill actual nulls, and also replace empty strings
        df_master[col] = df_master[col].fillna("Not Provided")
        df_master.loc[df_master[col].astype(str).str.strip() == '', col] = "Not Provided"

    # 2. Year Column: Force it to be a number. 
    # Invalid years (like "TBD") become NaN, which becomes NULL in SQL. 
    # DO NOT fill this with text. Leave it as a proper database NULL.
    df_master['year'] = pd.to_numeric(df_master['year'], errors='coerce')

    df_master = df_master[target_columns]
    
    # Strictly filter out bad rows so we don't drop good ones by accident
    df_master = df_master.dropna(subset=['title'])
    df_master = df_master[df_master['title'].astype(str) != 'nan']
    df_master = df_master[df_master['title'].astype(str) != 'N/A']
    df_master = df_master[df_master['title'].astype(str).str.strip() != '']

    print(f"   -> Merged data contains {len(df_master)} total valid rows.")

    print(f"4. Connecting to Database...{DB_NAME}")
    conn = sqlite3.connect(DB_NAME)

    df_master.to_sql("resources", conn, if_exists="replace", index=False)
    conn.close()

    print("ETL Complete Database Created...")

if __name__ == "__main__":
    run_basic_etl()