"""Tests for ChangelogParser."""

import pytest
from adaptive_radar_mcp.parser import ChangelogParser
from adaptive_radar_mcp.models import UpdateCategory


SAMPLE_CHANGELOG = """🛠 AI Automation Daily Changelog - 04.11.2026

[AGENTIC WORKFLOWS & FRAMEWORKS]

• PydanticAI v2.65.0: додано можливість динамічного керування параметром 'thinking effort' (OpenAI/Anthropic) посеред діалогу та підтримку мультимодальних нотаток в AskUserAnswer. (Джерело)

• CrewAI & NVIDIA NemoClaw: реалізовано оркестрацію самоевoлюціонуючих агентів із безпечним середовищем виконання для автономної генерації інструментів. (Джерело)

• LangChain Browser Use: оптимізовано роботу агентів із браузером через інструменти Stagehand, що знижує вартість та покращує траєкторію виконання завдань на сайтах без API. (Джерело)

• n8n v3.1.0: виправлено роботу AI Agent Node та впроваджено редакцію помилок у MCP-воркфлоу для захисту конфіденційних даних. (Джерело)

[LLMOps, INFRASTRUCTURE & COST]

• LangSmith BYOC: сервіс став доступним у форматі Bring Your Own Cloud на AWS (GA), Azure та GCP (Beta), розділяючи control plane та data plane. (Джерело)

💡 Для автоматизації: Дозволяє розгортати агенти в ентерпрайзі з повним збереженням трейсів та промптів у власному периметрі безпеки.

• AWS Bedrock AgentCore: впроваджено механізм OBO (on-behalf-of) токенів для ServiceNow через Entra ID для збереження ідентичності користувача. (Джерело)

• Qdrant x LangChain: покращено асинхронну підтримку для масштабних RAG-систем, що критично для стабільності продуктових інсталяцій. (Джерело)

[TOOLS, PROTOCOLS & MCP]

• EDB Postgres AI: запущено семантичний шар AIDB, який експонує схеми та коментарі Postgres через Model Context Protocol (MCP) для агентів. (Джерело)

💡 Для автоматизації: База даних стає self-describing інструментом, що радикально зменшує кількість помилок у Text-to-SQL пайплайнах.

• LLM CLI v0.37: додано підтримку GPT-6.1 та мультимодальних ембеддінгів (аудіо, відео, зображення) через Gemini Embedding 2. (Джерело)

• OpenAI Research: опубліковано нові стратегії захисту агентів від prompt injection через обмеження ризикованих дій у робочих процесах. (Джерело)

📌 Що взяти в беклог:
Використовуйте MCP для побудови семантичного шару над SQL-базами даних. Це дозволяє агентам розуміти бізнес-логіку через нативні коментарі БД, уникаючи роздування системного промпту.
"""


def test_parse_sample_changelog():
    draft = ChangelogParser.parse_text(SAMPLE_CHANGELOG)
    
    assert draft.date == "04.11.2026"
    assert len(draft.items) == 10
    assert draft.backlog_summary is not None
    assert "MCP" in draft.backlog_summary

    # Test PydanticAI item
    pydantic_item = next(i for i in draft.items if "PydanticAI" in i.tool_name)
    assert pydantic_item.version == "v2.65.0"
    assert pydantic_item.category == UpdateCategory.AGENTIC
    assert "thinking effort" in pydantic_item.summary

    # Test EDB Postgres AI and insight
    edb_item = next(i for i in draft.items if "EDB Postgres AI" in i.tool_name)
    assert edb_item.category == UpdateCategory.MCP_TOOLS
    assert edb_item.automation_insight is not None
    assert "self-describing" in edb_item.automation_insight

    # Test n8n item
    n8n_item = next(i for i in draft.items if "n8n" in i.tool_name)
    assert n8n_item.version == "v3.1.0"
