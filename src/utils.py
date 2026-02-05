from ddgs.exceptions import DDGSException
import logging
import requests
import os
from ddgs import DDGS
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_classic.retrievers.document_compressors import FlashrankRerank
from langchain_classic.retrievers import ContextualCompressionRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter

class SearchWrapper:
    def __init__(self, api):
        self.registry = {
            "ddgs": DDGSearch()
        }
        self.api = self.registry[api]

    def fetch(self, query: str, max_results: int = 3) -> list:
        return self.api.fetch(query=query, max_results=max_results)

    def scrape(self, url: str, max_chars: int = 125_000) -> str:
        return self.api.scrape(url=url, max_chars=max_chars)

class DDGSearch:
    def __init__(self):
        self.ddgs = DDGS()

    def fetch(self, query: str, max_results: int = 3):
        try:
            return [(result["href"], result["body"]) for result in self.ddgs.text(query=query, max_results=max_results)]
        except DDGSException as e:
            logging.exception(e)
            return []

    def scrape(self, url: str, max_chars: int = 125_000) -> str:
        response = requests.get(
            url=f"https://r.jina.ai/{url}",
            headers={
                "Authorization": f"Bearer {os.environ['JINA_API_KEY']}",
                "X-Retain-Images": "none",
                "X-Return-Format": "markdown"
            }
        )
        return response.text[:max_chars]

def create_vector_store(web_pages: list, snippets_size: int = 5000):
    urls, contents = zip(*[(page["url"], page["content"]) for page in web_pages])

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=snippets_size,
        chunk_overlap=150,
        separators=["\n\n", "\n", " ", ""]
    )
    all_chunks = []
    all_metadata = []

    for url, page in zip(urls, contents):
        if not page or len(page) < 10:
            continue

        chunks = splitter.split_text(page)
        all_chunks.extend(chunks)
        all_metadata.extend([{"url": url} for _ in chunks])

    embeddings = OllamaEmbeddings(model="nomic-embed-text")

    vector_store = FAISS.from_texts(
        texts=all_chunks,
        embedding=embeddings,
        metadatas=all_metadata
    )
    return vector_store

def get_top_k(query: str, vector_store: FAISS, k: int = 5):
    reranker = FlashrankRerank(top_n=k)
    base_retriever = vector_store.as_retriever(search_kwargs={"k": k*5})
    compressor_retriever = ContextualCompressionRetriever(
        base_compressor=reranker,
        base_retriever=base_retriever
    )
    return compressor_retriever.invoke(query)

def save_report(user_query: str, report: str, file_name: str):
    file = f"""
    [USER QUERY]: {user_query}
    
    [REPORT]: {report}
    """
    with open(file_name, "w") as f:
        f.write(file)