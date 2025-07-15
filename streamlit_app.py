import streamlit as st
import httpx
import asyncio
import sys
import nest_asyncio
import chromadb, uuid, ollama
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from textxtract import AsyncTextExtractor
from chromadb.api.client import SharedSystemClient

# --- Initial Setup ---
nest_asyncio.apply()

if sys.platform == "win32" and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- Constants ---
FASTAPI_BASE_URL = "http://localhost:8000"
CHROMA_DIR = "chroma_data"
COLLECTION_NAME = "scraped_documents"
SELECTED_OLLAMA_MODEL = "gemma3:1b"

st.set_page_config(layout="wide", page_title="Secure RAG Scraper & Chat")

# --- Streamlit Session State ---
defaults = {
    "clerk_token": "",
    "authenticated": False,
    "login_error": "",
    "messages": [],
    "db_uploaded": False
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

def rerun():
    try:
        st.experimental_rerun()
    except Exception:
        pass

# --- Auth Verification ---
async def verify_token(token: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{FASTAPI_BASE_URL}/protected",
            headers={"Authorization": f"Bearer {token}"}
        )
        return r.status_code == 200

async def rag_chat(query: str, token: str):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{FASTAPI_BASE_URL}/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": query}
        )
        r.raise_for_status()
        return r.json().get("answer", "")

# --- ChromaDB Setup ---
try:
    SharedSystemClient.clear_system_cache()
except:
    pass

db_client = chromadb.PersistentClient(path=CHROMA_DIR)
embed_fn = chromadb.utils.embedding_functions.DefaultEmbeddingFunction()

def prepare_documents(results):
    docs, metas = [], []
    for res in results:
        if res.success:
            if hasattr(res, "text"):
                docs.append(res.text.strip())
                metas.append({"source": res.source, "type": "document"})
            else:
                content = (res.extracted_content or res.markdown or res.html or "").strip()
                if content:
                    docs.append(content)
                    metas.append({"source": res.url, "type": "webpage"})
    return docs, metas

def upload_to_chromadb(documents, metadatas):
    try:
        db_client.delete_collection(name=COLLECTION_NAME)
    except:
        pass
    coll = db_client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)
    if not documents:
        st.info("No documents to upload.")
        st.session_state.db_uploaded = False
        return
    ids = [str(uuid.uuid4()) for _ in documents]
    coll.add(documents=documents, metadatas=metadatas, ids=ids)
    st.session_state.db_uploaded = True
    st.success(f"Uploaded {len(documents)} documents to ChromaDB.")

def get_ollama_response(prompt_text, context):
    prompt = (
        f"You are precise. Use only the context below to answer.\n"
        f"Context:\n{context}\n"
        f"Question: {prompt_text}\nExact Answer:"
    )
    try:
        r = ollama.chat(model=SELECTED_OLLAMA_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        stream=False)
        return r["message"]["content"]
    except Exception as e:
        return f"Ollama error: {e}"

# --- Main App ---
async def main_app():
    st.title("🔐 Secure RAG Scraper & Chat")

    if not st.session_state.authenticated:
        token = st.text_area("🎟 JWT token:", height=100)
        if st.button("Verify"):
            if await verify_token(token.strip()):
                st.session_state.clerk_token = token.strip()
                st.session_state.authenticated = True
                rerun()
                return
            else:
                st.session_state.login_error = "Invalid or expired token."
        if st.session_state.login_error:
            st.error(st.session_state.login_error)
        return

    if st.sidebar.button("Logout"):
        for key in defaults:
            st.session_state[key] = defaults[key]
        rerun()
        return

    st.header("1️⃣ Scrape & Upload")
    urls = st.text_area("URLs (one per line):")
    files = st.file_uploader("Upload docs", type=["pdf", "docx", "txt"], accept_multiple_files=True)

    if st.button("Run scraping"):
        st.info("Processing...")

        async def run_scraping_tasks():
            results = []
            if urls.strip():
                cfg = BrowserConfig(headless=True)
                run_cfg = CrawlerRunConfig()
                async with AsyncWebCrawler(config=cfg) as crawler:
                    tasks = [crawler.arun(url=u.strip(), config=run_cfg) for u in urls.splitlines() if u.strip()]
                    wr = await asyncio.gather(*tasks)
                    results.extend([r for r in wr if r.success])
            if files:
                ext = AsyncTextExtractor()
                async with ext:
                    for f in files:
                        txt = await ext.extract(f.read(), f.name)
                        results.append(type("DocRes", (), {"source": f.name, "text": txt, "success": True})())
            return results

        scrape_results = await run_scraping_tasks()
        docs, metas = prepare_documents(scrape_results)
        upload_to_chromadb(docs, metas)

    st.markdown("---")
    st.header("2️⃣ Chat with Content")

    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).markdown(msg["content"])

    prompt = st.chat_input("Your question:")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("assistant").markdown("Processing...")

        coll = db_client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)
        if coll.count() == 0:
            msg = "❗ No docs uploaded"
            st.warning(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})
        else:
            hits = coll.query(query_texts=[prompt], n_results=4)
            ctxt = "\n\n".join(
                f"[{m['type']}:{m['source']}]\n{d}"
                for d, m in zip(hits["documents"][0], hits["metadatas"][0])
            )
            answer = get_ollama_response(prompt, ctxt)
            st.session_state.messages.append({"role": "assistant", "content": answer})
        rerun()

# --- Safe Async Runner for Streamlit ---
def run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

# --- Entry ---
if __name__ == "__main__":
    run_async(main_app())
