"""Test script to verify ChromaDB course isolation."""

import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils import load_config, setup_logging
from src.vectorstore import VectorStore
from langchain_core.documents import Document

def run_test():
    print("Initializing test...")
    setup_logging()
    config = load_config()
    
    # Initialize VectorStore
    persist_dir = Path(__file__).parent / "data" / "test_chroma_db"
    
    # Clean up test directory if it exists from previous runs
    import shutil
    if persist_dir.exists():
        shutil.rmtree(persist_dir)
        print(f"Cleaned up old test database at {persist_dir}")
        
    vs = VectorStore(
        persist_directory=persist_dir,
        collection_name="test_materials",
        embedding_model=config['embeddings']['model_name'],
        device=config['embeddings']['device']
    )
    
    # Define test documents
    # Course 101: Kedokteran (Cardiology)
    doc_course_101 = [
        Document(
            page_content="Jantung adalah organ otot berongga yang berfungsi memompa darah ke seluruh tubuh melalui sistem peredaran darah.",
            metadata={"source": "cardio.pdf", "page": 1}
        )
    ]
    
    # Course 102: Ilmu Komputer (Computer Science)
    doc_course_102 = [
        Document(
            page_content="Sistem operasi adalah perangkat lunak sistem yang mengelola perangkat keras komputer, sumber daya perangkat lunak, dan menyediakan layanan umum untuk program komputer.",
            metadata={"source": "os.pdf", "page": 1}
        )
    ]
    
    print("\n--- TEST 1: Ingesting documents to separate courses ---")
    print("Adding cardiology document to course 101...")
    vs.add_documents(doc_course_101, course_id="101")
    
    print("Adding computer science document to course 102...")
    vs.add_documents(doc_course_102, course_id="102")
    
    count_101 = vs.get_count(course_id="101")
    count_102 = vs.get_count(course_id="102")
    print(f"Course 101 document count: {count_101} (Expected: 1)")
    print(f"Course 102 document count: {count_102} (Expected: 1)")
    
    assert count_101 == 1, "Course 101 count should be 1"
    assert count_102 == 1, "Course 102 count should be 1"
    print("✅ Ingestion count assertions passed.")
    
    print("\n--- TEST 2: Similarity search isolation ---")
    # Query relevant to cardiology
    query = "Bagaimana organ jantung memompa darah?"
    
    print(f"Searching query '{query}' in Course 101...")
    res_101 = vs.similarity_search(query, k=1, course_id="101")
    print(f"Result 101: {res_101[0].page_content if res_101 else 'None'}")
    assert len(res_101) == 1, "Should find result in course 101"
    assert "jantung" in res_101[0].page_content.lower(), "Should be cardiology document"
    
    print(f"Searching query '{query}' in Course 102...")
    res_102 = vs.similarity_search(query, k=1, course_id="102")
    print(f"Result 102: {res_102[0].page_content if res_102 else 'None'}")
    assert len(res_102) == 1, "Should find result in course 102 (nearest match)"
    assert "sistem operasi" in res_102[0].page_content.lower(), "Should be OS document, not Cardiology doc"
    print("✅ Search isolation assertions passed (No data leaks between collections).")
    
    print("\n--- TEST 3: Clearing specific course materials ---")
    print("Clearing course 101...")
    vs.clear(course_id="101")
    
    count_101_after = vs.get_count(course_id="101")
    count_102_after = vs.get_count(course_id="102")
    print(f"Course 101 count after clear: {count_101_after} (Expected: 0)")
    print(f"Course 102 count after clear: {count_102_after} (Expected: 1)")
    
    assert count_101_after == 0, "Course 101 should be empty"
    assert count_102_after == 1, "Course 102 should still have its document"
    print("✅ Course clearing isolation assertions passed.")
    
    print("\n--- TEST 4: Clearing remaining course ---")
    print("Clearing course 102...")
    vs.clear(course_id="102")
    
    count_102_final = vs.get_count(course_id="102")
    print(f"Course 102 count after clear: {count_102_final} (Expected: 0)")
    assert count_102_final == 0, "Course 102 should be empty"
    print("✅ Final course clearing passed.")
    
    # Clean up test database directory
    if persist_dir.exists():
        shutil.rmtree(persist_dir)
        print(f"\nTest database directory {persist_dir} cleaned up.")
        
    print("\n🎉 ALL COURSE ISOLATION TESTS PASSED SUCCESSFULLY! 🎉")

if __name__ == "__main__":
    run_test()
