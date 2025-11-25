"""Agents that coordinate façade grid generation, evaluation, and retrieval-backed design.

This module wires multiple `agno` agents together, patches session handling for robustness,
and defines structured schemas for façade workflows. Environment variables configure the
OpenAI models, JSON databases, and LanceDB knowledge base connections.
"""

import os
from agno.agent import Agent
from agno.db.json import JsonDb
from agno.models.openai.responses import OpenAIResponses
from agno.os import AgentOS
from agno.os.schema import SessionSchema
from agno.os.utils import get_session_name
from agno.tools.mcp import MCPTools
from schema.geometry import *
from pydantic import BaseModel
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.search import SearchType
from agno.vectordb.lancedb import LanceDb
from datetime import datetime, timezone
from agno.tools.openai import OpenAITools




from agno.memory import MemoryManager
from dotenv import load_dotenv
# loads .env once (idempotent)
load_dotenv()

def _safe_session_from_dict(cls, session):
    """Fallback `SessionSchema.from_dict` that tolerates missing or malformed session data."""
    session_data = session.get("session_data") or {}
    if not isinstance(session_data, dict):
        session_data = {}
    created_at = session.get("created_at")
    updated_at = session.get("updated_at")
    return cls(
        session_id=session.get("session_id", ""),
        session_name=get_session_name(session),
        session_state=session_data.get("session_state"),
        created_at=datetime.fromtimestamp(created_at, tz=timezone.utc) if created_at else None,
        updated_at=datetime.fromtimestamp(updated_at, tz=timezone.utc) if updated_at else None,
    )

SessionSchema.from_dict = classmethod(_safe_session_from_dict)

api_key = os.getenv("OPENAI_API_KEY", "")
open_ai_model = os.getenv("OPENAI_MODEL", "")
open_ai_model_eval = os.getenv("OPENAI_MODEL_EVAL", "")
open_ai_model_fast = os.getenv("OPENAI_MODEL_FAST", "")
open_ai_model_reason = os.getenv("OPENAI_MODEL_REASON", "")

# db = SqliteDb("agents.db")
# db = InMemoryDb()

db_path = os.getenv("DB_PATH", "")
contentdb_path = os.getenv("CONTENTDB__PATH", "")

lancedb_uri = os.getenv("LANCEDB_URI", "")
lancedb_table = os.getenv("LANCEDB_TABLE", "")


# database
db = JsonDb(db_path=db_path)


# Set up knowledge base
knowledge = Knowledge(
    name="knowledge_base",
    description="Knowledge base for design reasoning",
    vector_db=LanceDb(
        table_name=lancedb_table,
        uri=lancedb_uri,
        embedder= OpenAIEmbedder(api_key=api_key),
        search_type=SearchType.hybrid
    ),
    contents_db=JsonDb(db_path=contentdb_path),
    max_results=5
)

# Create your agent
knowledge_agent = Agent(
    name="Knowledge Agent",
    description="Always search knowledge before answering",
    model=OpenAIResponses(id=open_ai_model_eval, api_key=api_key),
    knowledge=knowledge,
    search_knowledge=True,
    markdown=False    
)


init_agent = Agent(
    name="Init Agent",
    description=(
        "Registers optimization objectives and creates a new session. "
        "Do not generate explanations or reasoning. Respond briefly with confirmation only."
    ),
    model=OpenAIResponses(id=open_ai_model, api_key=api_key),
    # model=DeepSeek(id="deepseek-chat", api_key=deepseek_api),
    # add_history_to_context=True,
    db=db,
    markdown=False
    )


class Grid(Geometry):
    """Grid composed of multiple line segments."""
    type: Literal["Grid"] = "Grid"
    lines: List[Line]

grid_agent = Agent(
    name="Grid Generator",
    description=(
        "You are the Grid Generator agent. Your goal is to iteratively improve facade planning grids "
        "based on previous results and evaluations.\n\n"
        "You receive input geometries (Box, Rectangle3d, Polyline, etc.) as structured JSON and must "
        "generate a rational, elegant planning grid composed of lines that subdivide the given boundary.\n\n"
        "### Objectives\n"
        "- Align the grid logically to the provided geometry (respect proportions, edges, and symmetry).\n"
        "- Generate consistent and constructible grid patterns (e.g., orthogonal, diagonal, or mixed).\n"
        "- Ensure the grid enhances architectural legibility (balance, rhythm, variation).\n"
        "- Each iteration should *improve upon previous attempts* based on stored history, "
        "user feedback, or pattern evaluations.\n\n"
        "### Iteration Strategy\n"
        "- Review previous iterations stored in the session or database.\n"
        "- Identify weaknesses or repetitive outputs and introduce meaningful variation.\n"
        "- Preserve successful geometric or compositional principles from earlier results.\n"
        "- Optimize to get the best rating from the evaluation.\n\n"
        "Return your result as a structured `Grid` model, containing all lines with clear spatial logic."
    ),
    # model=OpenAIResponses(id="gpt-4.1", api_key=api_key),
    model=OpenAIResponses(id=open_ai_model_eval, api_key=api_key),
    # model=DeepSeek(id="deepseek-chat", api_key=deepseek_api),
    # model=Ollama(id="qwen3:32b"),
    # add_history_to_context=True,
    output_schema=Grid,
    db=db,
    markdown=False
)

class Evaluation(BaseModel):
    """
    Evaluation result for facade panel quality.
    """
    rating: float = Field(..., ge=1, le=10, description="Overall evaluation rating from 1 (poor) to 10 (excellent).")
    evaluation_feedback: str = Field(..., description="Qualitative feedback explaining the evaluation reasoning and suggestion of improvement for the next iterations.")

eval_agent = Agent(
    name="Evaluation Agent",
    description="Evaluates the resulting facade panels",
    model=OpenAIResponses(id=open_ai_model_eval, api_key=api_key),
    # model=DeepSeek(id="deepseek-chat", api_key=deepseek_api),
    # add_history_to_context=True,
    output_schema=Evaluation,
    db=db,
    markdown=False
)

    
    
# --- Schema Definitions ---
class FacadeElement(BaseModel):
    """Single façade element or grid panel assignment with descriptive intent."""
    id: str = Field(..., description="Unique identifier of the façade element or grid panel.")
    type: str = Field(..., description="Assigned façade element type, e.g. glazing, shading, vent, opaque panel, PV panel, etc.")
    description: str = Field(..., description="Concise conceptual description expressing material, function, and aesthetic intent.")


class FacadeElementList(BaseModel):
    """Collection of façade elements along with an overarching composition concept."""
    concept: str = Field(..., description="Overall façade concept summarizing composition, performance logic, and adaptive strategy.")
    facade: List[FacadeElement] = Field(
        default_factory=list,
        description="List of façade elements assigned to grid panels with conceptual descriptions."
    )

class FacadeTypology(BaseModel):
    """Grouping of façade elements that share a typological logic or treatment."""
    typology: str = Field(..., description="Facade typology name or category, e.g. glazing, shading, vent, opaque panel, PV panel, etc.")
    concept: str = Field(..., description="Concise conceptual description explaining the material logic, function, or aesthetic intent of this typology.")
    elements: List[str] = Field(..., description="List of façade element or grid panel IDs belonging to this typology.")

class FacadeTypologyList(BaseModel):
    """List of façade typologies plus a high-level narrative."""
    concept: str = Field(
        ..., 
        description="Overall façade concept summarizing composition, performance logic, and adaptive strategy."
    )
    facade: List[FacadeTypology] = Field(
        default_factory=list,
        description="List of façade typologies, each with its concept and assigned element IDs."
    )

# --- Agent Definition ---
facade_design_agent = Agent(
    name="Facade Design Agent",
    description=(
        "You are the Facade Design Agent. Group façade panels into clear typologies and define concise conceptual "
        "descriptions for each. Focus on clarity, modular logic, constructability, and environmental responsiveness. "
        "If the user introduces a specific theme (e.g., edge computing), treat it as an additional design driver—but "
        "do not assume any theme unless explicitly mentioned.\n\n"

        "### Method\n"
        "- Read the user brief carefully to identify performance goals and contextual drivers.\n"
        "- Respond to building orientation, adjacency, openings, and climatic conditions.\n"
        "- Organize panels into coherent typologies (e.g., glazing, shading, PV, opaque, vented) that follow a rational logic.\n"
        "- Ensure typologies express both functional intent and visual hierarchy.\n"

        "### Output (strict JSON schema)\n"
        "Return a `FacadeTypologyList` object with:\n"
        "- `concept`: a short paragraph summarizing overall façade composition, performance logic, and adaptive strategy.\n"
        "- `facade`: an array of typology entries, each containing:\n"
        "    • `typology`: the façade type/category (e.g., glazing, shading, PV panel).\n"
        "    • `concept`: a concise design description explaining material, function, or aesthetic intent.\n"
        "    • `elements`: a list of panel or grid element IDs belonging to this typology.\n"
        "Do NOT include extra keys, commentary, or formatting outside the JSON.\n\n"

        "### Quality Criteria\n"
        "- **Legibility:** clear rhythms and typological hierarchy; avoid random or excessive variation.\n"
        "- **Environmental fitness:** daylight control, ventilation, thermal response, and view quality.\n"
        "- **Constructability:** maintain modular logic and clear assembly or access pathways.\n"
        "- **Contextual fit:** respond to street-facing character, layering, and vernacular proportion without mimicry.\n\n"

        "### Style\n"
        "- Use precise, factual phrasing; avoid marketing or overly abstract language.\n"
        "- Keep concept statements compact and functional.\n"
        "- Maintain architectural tone and clarity."
    ),
    # knowledge=knowledge,
    # search_knowledge=True,
    model=OpenAIResponses(id=open_ai_model_reason, api_key=api_key),
    output_schema=FacadeTypologyList,
    db=db,
    markdown=False
)



# Create the AgentOS
agent_os = AgentOS(agents=[init_agent,grid_agent, eval_agent,facade_design_agent, knowledge_agent],
                   knowledge=[knowledge])
# Get the FastAPI app for the AgentOS
app = agent_os.get_app()
