from attools import sqlmap
subagents = [
    {
        "name": "recon_agent",
        "description": "This agent is responsible for gathering information and conducting research on various topics.",
        "system_prompt": "You are a research agent. Your task is to gather information and conduct research on various topics.",
        "tools": [my_custom_tool],
    },
    {
        "name": "execution_agent",
        "description": "This agent is responsible for executing tasks and implementing solutions.",
        "system_prompt": "You are an execution agent. Your task is to execute tasks and implement solutions.",
        "tools": [sqlmap],
    },
]
