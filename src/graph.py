from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage
from langchain_ollama import ChatOllama
import logging
from langgraph.types import Send
from datetime import datetime

from prompts import *
from states import *
from utils import SearchWrapper, create_vector_store, get_top_k, save_report

logging.basicConfig(level=logging.INFO)

current_date = datetime.now()

class QueryGenerator:
    def __init__(self, model: str = "qwen3:8b"):
        self.llm = ChatOllama(model=model)
        self.structured_llm = self.llm.with_structured_output(GenerateQueries)
        self.system_prompt = GENERATE_QUERIES_PROMPT

    def generate_queries(self, state: QueryGeneratorState):
        logging.info("Entered in the 'generate_queries' node")
        prompt = [
            SystemMessage(self.system_prompt),
            SystemMessage(f"[USER QUERY]: {state["user_query"]}"),
            SystemMessage(f"[CURRENT DATE AND TIME]: {current_date}")
        ]
        response = GenerateQueries(
            search_queries=[
                QueryItem(query="", reason="The query generation has failed.")
            ]
        )
        for _ in range(5):
            try:
                response = self.structured_llm.invoke(prompt)
                break
            except Exception as e:
                logging.info(e)
        search_queries = response.search_queries
        logging.info(f"search_queries: {search_queries}")
        return {"search_queries": search_queries}

class Researcher:
    def __init__(self, model: str = "qwen3:8b", search_api: str = "ddgs"):
        self.llm = ChatOllama(model=model)
        self.structured_llm = self.llm.with_structured_output(Summarize)
        self.system_prompt = SUMMARIZER_PROMPT
        self.search_api = SearchWrapper(api=search_api)

    def search(self, state: ResearcherState):
        logging.info("Entered in the 'search' node")
        search_query = state["search_query"]
        urls, snippets = zip(*self.search_api.fetch(query=search_query))
        existing_urls = [result["url"] for result in state["search_results"]] if state["search_results"] else []
        scraped_data = [{"url": url, "content": self.search_api.scrape(url)} for url in urls if url not in existing_urls]
        if not scraped_data:
            logging.warning(f"No new content found for query: {search_query}")
            return {"summaries": [], "search_results": []}
        vector_store =  create_vector_store(web_pages=scraped_data, snippets_size=5000)
        top_k_snippets = get_top_k(query=state["user_query"], vector_store=vector_store, k=3)
        summaries = []
        for snippet in top_k_snippets:
            for _ in range(5):
                try:
                    url = snippet.metadata["url"]
                    content = snippet.page_content
                    prompt = [
                        SystemMessage(self.system_prompt),
                        SystemMessage(f"[CURRENT DATE AND TIME]: {current_date}"),
                        SystemMessage(f"[USER QUERY]: {state["user_query"]}"),
                        SystemMessage(f"[URL]: {url}"),
                        SystemMessage(f"[PAGE SNIPPET]: {content}")
                    ]
                    response = self.structured_llm.invoke(prompt)
                    summaries.append({"url": url, "summary": response.summary})
                    break
                except Exception as e:
                    logging.info(e)
        logging.info(f"search_results: {scraped_data}")
        logging.info(f"summaries: {summaries}")
        return {"summaries": summaries, "search_results": scraped_data}

class Reviewer:
    def __init__(self, model: str = "qwen3:8b"):
        self.llm = ChatOllama(model=model)
        self.structured_llm = self.llm.with_structured_output(Review)
        self.system_prompt = REVIEWER_PROMPT

    def is_search_complete(self, state: SystemState):
        logging.info(f"review: {state["review"]}")
        if state["review"]["is_search_complete"]:
            return True
        else:
            return False

    def review(self, state: ReviewerState):
        logging.info("Entered in the 'review' node")
        response = Review(is_search_complete=False, justification="An error occurred during review.")
        for _ in range(5):
            try:
                prompt = [
                    SystemMessage(self.system_prompt),
                    SystemMessage(f"[CURRENT DATE AND TIME]: {current_date}"),
                    SystemMessage(f"[USER QUERY]: {state["user_query"]}"),
                    SystemMessage(f"[SUMMARIES]: {state["summaries"]}")
                ]
                response = self.structured_llm.invoke(prompt)
                break
            except Exception as e:
                logging.info(e)
        is_search_complete = response.is_search_complete
        justification = response.justification
        logging.info(f"is_search_complete: {is_search_complete}")
        logging.info(f"justification: {justification}")
        return {"review": {"is_search_complete": is_search_complete, "justification": justification}}

class Writer:
    def __init__(self, model: str = "qwen3:8b"):
        self.llm = ChatOllama(model=model)
        self.structured_llm = self.llm.with_structured_output(Write)
        self.system_prompt = WRITER_PROMPT

    def write(self, state: WriterState):
        logging.info("Entered in the 'write' node")
        response = Review(is_search_complete=False, justification="An error occurred during review.")
        for _ in range(5):
            try:
                prompt = [
                    SystemMessage(self.system_prompt),
                    SystemMessage(f"[CURRENT DATE AND TIME]: {current_date}"),
                    SystemMessage(f"[USER QUERY]: {state["user_query"]}"),
                    SystemMessage(f"[SUMMARIES]: {state["summaries"]}")
                ]
                response = self.structured_llm.invoke(prompt)
                break
            except Exception as e:
                logging.info(e)
        report = response.report
        logging.info(f"report: {report}")
        return {"report": report}

def route_plan_to_search(state: SystemState):
    return [Send("search", {"search_query": query_item.query, "user_query": state["user_query"], "search_results": state["search_results"] if "search_results" in state.keys() else []}) for query_item in state["search_queries"]]

if __name__ == "__main__":
    query_generator = QueryGenerator()
    researcher = Researcher()
    reviewer = Reviewer()
    writer = Writer()

    graph = StateGraph(SystemState)

    graph.add_node("generate_queries", query_generator.generate_queries)
    graph.add_node("search", researcher.search)
    graph.add_node("review", reviewer.review)
    graph.add_node("write", writer.write)

    graph.add_conditional_edges(
        "generate_queries",
        route_plan_to_search,
        ["search"]
    )

    graph.add_edge("search", "review")
    graph.add_conditional_edges(
        "review",
        reviewer.is_search_complete,
        {True: "write", False: "generate_queries"}
    )
    graph.add_edge("write", END)

    graph.set_entry_point("generate_queries")
    graph = graph.compile()

    user_query = "Qui est le directeur artistique de Versace ?"

    state: SystemState = {
        "user_query": user_query,
    }

    final_state = graph.invoke(state)

    report = final_state["report"]
    print(report)
    save_report(user_query=user_query,report=report, file_name="report")