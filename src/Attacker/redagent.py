from deepagents import create_deep_agent

from subagents_attack import subagents

agent = create_deep_agent(
    model="openai:gpt-6-astra",
    tools=[my_custom_tool],
    system_prompt="You are a research assistant.",
    subagents=subagents,
)
result = agent.invoke({"messages": "Research LangGraph and write a summary"})
