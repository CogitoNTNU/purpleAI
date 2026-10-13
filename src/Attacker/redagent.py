import os

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

#from attools import tools
from config import Target_url
from subagents_attack import execution_agent

model = ChatOpenAI(
    model="moonshotai/Kimi-K2.6",
    api_key=os.environ.get("LLM_API_KEY", ""),
    base_url="https://llm.hpc.ntnu.no/v1",
    )


BossAgent = create_deep_agent(
    model=model,
    #tools= tools,
    system_prompt=
    "You are a planner in a pen testing environment. You job is to plan a penetration on the given url"
    "Delegate tasks to subagents and provide a summary of the results. The execution agent is responsible for executing tasks and implementing solutions. You are not allowed to execute any tasks yourself, only delegate to the execution agent."
    "Execution_agent has the tools: sqlmap: Map vulnerable SQL injection points in a web app via sqlmap.",
    name="Boss Agent",
    subagents=[execution_agent]
)

if __name__ == "__main__":
    result = BossAgent.invoke({"messages": f"Scan {Target_url} for SQL injection."})
    print(result)
