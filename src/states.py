from typing import TypedDict, List, Annotated, NotRequired, Optional, Tuple
from pydantic import BaseModel, Field
import operator

class SystemState(TypedDict):
    user_query: str
    search_queries: List[dict[str, str]]
    search_results : Annotated[List[dict[str, str]], operator.add]
    summaries : Annotated[List[dict[str, str]], operator.add]
    review: dict[str, str]
    report: str

class QueryGeneratorState(TypedDict):
    user_query : str

class ResearcherState(TypedDict):
    user_query: str
    search_query: str
    search_results: Annotated[List[dict[str, str]], operator.add]

class ReviewerState(TypedDict):
    summaries : List[dict[str, str]]
    user_query: str

class WriterState(TypedDict):
    summaries : List[dict[str, str]]
    user_query: str

class QueryItem(BaseModel):
    query: str = Field(description="The keyword-optimized search string.")
    reason: str = Field(description="Justification for why this query was chosen.")

class GenerateQueries(BaseModel):
    search_queries: List[QueryItem] = Field(
        description="A list of 3 to 5 distinct search queries with justifications."
    )

class Summarize(BaseModel):
    summary: str = Field(
        description="A concise extraction of facts, dates, and numbers from the text that directly answer the user query. If the text contains NO relevant information, this must be an empty string."
    )

class Review(BaseModel):
    is_search_complete: bool = Field(
        description="True ONLY if the gathered information allows for a comprehensive, detailed answer to the user query. False if any specific detail is missing."
    )
    justification: str = Field(
        description="If False, specify exactly what information is missing to guide the next search. If True, briefly summarize why the data is sufficient."
    )

class Write(BaseModel):
    report: str = Field(
        description="A professional, structured report in Markdown format. It must answer the user query in depth using ONLY the provided page summaries, including inline citations [Source: URL] for every fact."
    )
