from deepagents import create_deep_agent
from attools import tools
from subagents_attack import execution_agent
import os
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model="moonshotai/Kimi-K2.6", 
    api_key= "",
    base_url= "https://llm.hpc.ntnu.no/v1"
    )


BossAgent = create_deep_agent(
    model=model,
    tools= tools,
    system_prompt="You are a planner in a pen testing environment. You job is to plan a penetration on the given url",
    name="Boss Agent",
    subagents=[execution_agent] 
)
result = BossAgent.invoke({"messages": "Research LangGraph and write a summary"})
