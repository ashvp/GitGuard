from google import genai
from google.genai import types
import os
import typer
from pydantic import BaseModel, Field

class GitPlan(BaseModel):
    risk: str = Field(..., description="Risk level: LOW, MEDIUM, or HIGH")
    summary: str = Field(..., description="Short explanation of what will happen")
    commands: list[str] = Field(..., description="List of git commands to execute")

def get_git_plan(intent: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[red]Error: GEMINI_API_KEY not found in environment variables.[/red]")
        raise typer.Exit(1)

    client = genai.Client(api_key=api_key)

    prompt = f"""
    You are GitGuard, an AI Git Safety Copilot.
    The user's intent is: "{intent}"
    
    Create a safe execution plan for this Git operation.
    
    Guidelines:
    - LOW: Non-destructive (status, log, branch listing).
    - MEDIUM: Modifies history or working directory but recoverable (commit, checkout, reset --soft).
    - HIGH: Destructive or hard to undo (reset --hard, force push, branch deletion).
    - Ensure commands are valid and follow best practices.
    - For "delete this branch", determine the current branch first, then delete it safely.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GitPlan,
                temperature=0.2,
            )
        )
        
        # With structured outputs, we get a parsed object directly if we use the schema correctly,
        # or we can parse the JSON text which is guaranteed to match the schema.
        # The new SDK often returns a parsed structure if requested.
        # For safety/clarity, we parse the text which is standard.
        import json
        plan = json.loads(response.text)
        return plan
        
    except Exception as e:
        print(f"[red]AI Error: {e}[/red]")
        return {
            "risk": "UNKNOWN",
            "summary": "Failed to generate plan via AI",
            "commands": []
        }