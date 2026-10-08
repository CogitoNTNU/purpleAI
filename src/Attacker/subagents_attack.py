from attools import sqlmap



execution_agent={
    "name": "execution_agent",
    "description": "Delegate execution tasks in the order of the TODO list.",
    "system_prompt": "You are an execution agent. Your task is to execute tasks and implement solutions.",
    "tools": [sqlmap],
}
