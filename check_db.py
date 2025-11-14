
import sqlite3
import os

# --- Configuration ---
DB_PATH = "storage/sqlite/research.db"
PAPER_TITLE_FRAGMENT = "An Image is Worth 16x16 Words" # Using a fragment to avoid issues with exact title matching

# --- Script ---
db_file = os.path.abspath(DB_PATH)
print(f"Connecting to database at: {db_file}")

if not os.path.exists(db_file):
    print(f"❌ Error: Database file not found at '{db_file}'")
    exit()

paper_id = None
try:
    with sqlite3.connect(db_file) as conn:
        print("✅ Database connection successful.")
        cursor = conn.cursor()

        # 1. Find the paper_id from the papers table
        print(f"🔍 Searching for paper with title like '%{PAPER_TITLE_FRAGMENT}%'...")
        cursor.execute("SELECT paper_id, title FROM papers WHERE title LIKE ?", (f'%{PAPER_TITLE_FRAGMENT}%',))
        result = cursor.fetchone()

        if result:
            paper_id, title = result
            print(f"Found paper: '{title}' with ID: {paper_id}")
        else:
            print("❌ Paper not found in the 'papers' table.")
            exit()

        # 2. Using the paper_id, check for its full text in the paper_fulltext table
        if paper_id:
            print(f"🔍 Checking for full text for paper_id: {paper_id}...")
            cursor.execute("SELECT plain_text FROM paper_fulltext WHERE paper_id = ?", (paper_id,))
            full_text_result = cursor.fetchone()

            if full_text_result:
                full_text_content = full_text_result[0]
                if full_text_content and full_text_content.strip():
                    # To avoid printing a huge wall of text, we'll just show the first 500 characters
                    print(f"✅ SUCCESS: Full text found! Here are the first 500 characters:")
                    print("-" * 50)
                    print(full_text_content[:500] + "...")
                    print("-" * 50)
                else:
                    print("❌ FAILURE: Full text entry exists, but the 'plain_text' field is EMPTY.")
            else:
                print("❌ FAILURE: No entry found in the 'paper_fulltext' table for this paper_id.")

except sqlite3.Error as e:
    print(f"An error occurred with the database: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

