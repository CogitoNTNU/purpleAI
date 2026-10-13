from attools import sqlmap



execution_agent={
    "name": "execution_agent",
    "description": "Execute the tasks and implement solutions delegated by the Boss Agent.",
    "system_prompt": "You are an execution agent. Your task is to execute tasks and implement solutions. Your tools are sqlmap: Map vulnerable SQL injection points in a web app via sqlmap.",
    "tools": [sqlmap],
}
