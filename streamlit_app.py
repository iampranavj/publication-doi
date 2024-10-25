import streamlit as st
import pandas as pd
import requests
import re
from time import sleep
from difflib import SequenceMatcher

def clean_text_for_comparison(text):
    """Clean text for comparison by removing punctuation and standardizing spaces"""
    text = re.sub(r'[^\w\s-]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.lower().strip()

def search_crossref_doi(title, authors='', year=''):
    """Search CrossRef API for a DOI using article title, authors, and year"""
    base_url = "https://api.crossref.org/works"
    clean_title = title.strip().replace('\n', ' ')
    
    params = {
        "query.title": f'"{clean_title}"',
        "rows": 3,
        "select": "DOI,title,published-print,author,container-title",
    }
    
    try:
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            results = response.json()
            if not results["message"]["items"]:
                return ""
            
            input_title_clean = clean_text_for_comparison(clean_title)
            
            for result in results["message"]["items"]:
                if "title" not in result or not result["title"]:
                    continue
                
                result_title = result["title"][0]
                result_title_clean = clean_text_for_comparison(result_title)
                similarity = SequenceMatcher(None, result_title_clean, input_title_clean).ratio()
                
                if similarity > 0.85:
                    if year and "published-print" in result:
                        pub_year = str(result["published-print"].get("date-parts", [[""]])[0][0])
                        if pub_year != year:
                            continue
                    return result.get("DOI", "")
        return ""
    except Exception as e:
        st.warning(f"Error searching DOI: {str(e)}")
        return ""

def extract_publications(text):
    """Extract publications from text with complex format handling"""
    entries = re.split(r'(?=\d{4}\s*-\s*)', text)
    publications = []
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
            
        try:
            year_match = re.match(r'(\d{4})\s*-\s*', entry)
            if not year_match:
                continue
                
            year = year_match.group(1)
            title_match = re.search(r'"([^"]+)"', entry)
            if not title_match:
                continue
                
            title = title_match.group(1).strip()
            start_pos = year_match.end()
            end_pos = title_match.start()
            authors = entry[start_pos:end_pos].strip().rstrip('.')
            venue = entry[title_match.end():].strip().strip('.')
            
            publications.append({
                'Year': year,
                'Authors': authors,
                'Title': title,
                'Venue': venue
            })
            
        except Exception as e:
            st.warning(f"Failed to parse entry: {entry[:100]}... Error: {str(e)}")
            continue
    
    return publications

def create_doi_url(doi):
    """Create DOI URL if DOI exists"""
    if doi and doi.startswith('10.'):
        return f"https://doi.org/{doi}"
    return ""

def process_dois(df, progress_bar=None):
    """Process a batch of articles to find DOIs"""
    dois = []
    total = len(df)
    found_count = 0
    
    for idx, row in df.iterrows():
        if progress_bar:
            progress_bar.progress((idx + 1) / total)
            
        doi = search_crossref_doi(
            title=row['Title'],
            authors=row.get('Authors', ''),
            year=row.get('Year', '')
        )
        
        if doi and doi.startswith('10.'):
            found_count += 1
            st.sidebar.write(f"Found DOIs: {found_count}")
            
        dois.append(doi)
        sleep(1)  # Rate limiting
    
    return dois

# Set page config
st.set_page_config(
    page_title="Publication Parser & DOI Finder",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
        .block-container {
            max-width: 1000px;
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        .element-container {
            max-width: 100%;
        }
        .stDataFrame {
            width: 100%;
        }
    </style>
    """, unsafe_allow_html=True)

# Initialize session state
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None
if 'show_doi_results' not in st.session_state:
    st.session_state.show_doi_results = False
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "Single Search"

# Sidebar
with st.sidebar:
    st.title("Navigation")
    st.session_state.active_tab = st.radio(
        "Choose Function:",
        ["Single Search", "Batch Processing", "About"]
    )
    
    if st.session_state.active_tab == "Batch Processing":
        st.markdown("---")
        st.subheader("Settings")
        input_method = st.radio(
            "Input Method:",
            ["Paste Text", "Upload Text File"]
        )
    
    if st.session_state.processed_df is not None:
        st.markdown("---")
        st.subheader("Quick Stats")
        df = st.session_state.processed_df
        st.write(f"Total Publications: {len(df)}")
        if 'DOI' in df.columns:
            doi_found = df['DOI'].apply(lambda x: bool(x) and x.startswith('10.')).sum()
            st.write(f"DOIs Found: {doi_found}")
            st.write(f"Not Found: {len(df) - doi_found}")

# Main content area
if st.session_state.active_tab == "Single Search":
    st.title("Single Article DOI Search")
    
    title = st.text_input("Article Title:")
    authors = st.text_input("Authors (optional):")
    year = st.text_input("Year (optional):")
    
    if st.button("Search DOI") and title:
        with st.spinner("Searching..."):
            doi = search_crossref_doi(title, authors, year)
            if doi:
                st.success(f"DOI: {doi}")
                st.success(f"DOI URL: https://doi.org/{doi}")
            else:
                st.info("No DOI found for this publication")

elif st.session_state.active_tab == "Batch Processing":
    st.title("Batch DOI Processing")
    
    if input_method == "Paste Text":
        text_input = st.text_area(
            "Paste your publications list:",
            height=200,
            help="Format: YEAR - Authors. \"Title\". Venue"
        )
    else:  # Upload File
        uploaded_file = st.file_uploader("Choose text file", type="txt")
        if uploaded_file:
            text_input = uploaded_file.getvalue().decode()
            st.text_area("File contents preview:", value=text_input[:500] + "...", height=150)
        else:
            text_input = ""

    # Process publications button
    if text_input and st.button("1. Process Publications"):
        with st.spinner("Extracting publications..."):
            publications = extract_publications(text_input)
            if not publications:
                st.error("No publications found in the input")
                st.stop()
            
            st.session_state.processed_df = pd.DataFrame(publications)
            st.success(f"Found {len(publications)} publications")
            st.write("Preview of extracted data:")
            st.dataframe(st.session_state.processed_df)
    
    # Find DOIs button
    if st.session_state.processed_df is not None:
        if st.button("2. Find DOIs"):
            df = st.session_state.processed_df
            progress_bar = st.progress(0)
            
            with st.spinner("Finding DOIs..."):
                dois = process_dois(df, progress_bar)
                df['DOI'] = dois
                df['DOI URL'] = df['DOI'].apply(create_doi_url)
                st.session_state.processed_df = df
                
                # Show results
                st.write("Results:")
                columns = ['Year', 'Authors', 'Title', 'DOI', 'DOI URL', 'Venue']
                st.dataframe(df[columns])
                
                # Download buttons
                csv = df.to_csv(index=False)
                st.download_button(
                    "📥 Download Results (CSV)",
                    csv,
                    "publications_with_dois.csv",
                    "text/csv"
                )
                
                # Statistics
                st.write("\nStatistics:")
                doi_found = df['DOI'].apply(lambda x: bool(x) and x.startswith('10.')).sum()
                st.write(f"DOIs found: {doi_found} out of {len(df)} publications ({(doi_found/len(df)*100):.1f}%)")

else:  # About tab
    st.title("About")
    st.markdown("""
    ### Publication Parser & DOI Finder
    
    This tool helps you:
    - Find DOIs for individual articles
    - Process batch publication lists
    - Extract structured data from publication text
    - Download results in CSV format
    
    ### Data Format
    For batch processing, format your publications as:
    ```
    YEAR - Authors. "Title". Venue/Journal. Additional Info
    ```
    
    ### Note
    - Not all publications have DOIs
    - The tool uses strict matching to avoid incorrect DOIs
    - Conference papers and some other formats might not have DOIs
    """)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <small>Please make sure to verify the DOI</small>
</div>
""", unsafe_allow_html=True)
