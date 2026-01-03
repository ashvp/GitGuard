from google import genai
from google.genai import types
import os
import typer
from pydantic import BaseModel, Field
import json
from typing import Optional

class GitPlan(BaseModel):
    risk: str = Field(..., description="Risk level: LOW, MEDIUM, or HIGH")
    summary: str = Field(..., description="Short explanation of what will happen")
    commands: list[str] = Field(..., description="List of git commands to execute")
    missing_info_prompt: Optional[str] = Field(None, description="Question to ask user if info is missing (e.g. 'Enter repo URL')")

class CommitMessage(BaseModel):
    subject: str = Field(..., description="Concise summary (max 50 chars)")
    body: str = Field(..., description="Detailed explanation (bullet points)")

class AuditResult(BaseModel):
    issues: list[str] = Field(..., description="List of potential issues (security, bugs, TODOs)")
    severity: str = Field(..., description="Overall severity: LOW, MEDIUM, or HIGH")
    passed: bool = Field(..., description="Whether the code is safe to commit")

class Explanation(BaseModel):
    summary: str = Field(..., description="Plain English summary of changes")
    key_changes: list[str] = Field(..., description="Bullet points of key changes")

def get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

def get_git_plan(intent: str):
    client = get_client()
    if not client:
        print("[red]Error: GEMINI_API_KEY not found.[/red]")
        raise typer.Exit(1)

    prompt = f"""
    You are GitGuard, an AI Git Safety Copilot.
    The user's intent is: "{intent}"
    
    Create a safe execution plan for this Git operation.
    
    Guidelines:
    - LOW: Non-destructive (status, log, branch listing).
    - MEDIUM: Modifies history or working directory but recoverable (commit, checkout, reset --soft).
    - HIGH: Destructive or hard to undo (reset --hard, force push, branch deletion).
    - Ensure commands are valid and follow best practices.
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
        return json.loads(response.text)
    except Exception as e:
        print(f"[red]AI Error: {e}[/red]")
        return {"risk": "UNKNOWN", "summary": "Failed to generate plan", "commands": []}

def get_fix_plan(intent: str, failed_commands: list[str], error_message: str, command_history: list[str] = None):
    client = get_client()
    if not client: return None
    
    history_text = ""
    if command_history:
        history_text = "\nCOMMAND HISTORY:\n" + "\n".join([f"- {cmd}" for cmd in command_history])

    prompt = f"""
    You are GitGuard.
    CONTEXT: Intent: "{intent}". Failed commands: {failed_commands}
    {history_text}
    ERROR: "{error_message}"
    
    TASK: Provide a CORRECTED sequence of commands.
    
    CRITICAL INSTRUCTION FOR MISSING INFO:
    If the error indicates missing information that only the user knows (like a remote URL, a specific ID, or a message),
    you MUST set the 'missing_info_prompt' field to ask for it.
    Then, use the placeholder '{{INPUT}}' in the commands where that value belongs.
    
    Example:
    Error: "No configured push destination"
    missing_info_prompt: "Please enter the remote repository URL:"
    commands: ["git remote add origin {{INPUT}}", "git push -u origin main"]
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
        return json.loads(response.text)
    except Exception:
        return None

def generate_commit_message(diff: str):
    client = get_client()
    if not client: return None

    prompt = f"""
    Generate a Conventional Commit message for this diff:
    {diff[:10000]}  # Truncate if too long
    
    Format:
    - Subject: <type>(<scope>): <description>
    - Body: Bullet points
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CommitMessage,
                temperature=0.2,
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"[red]AI Error: {e}[/red]")
        return None

def audit_code(diff: str):
    client = get_client()
    if not client: return None

    prompt = f"""
    Audit this git diff for security issues (secrets, keys), critical bugs, or leftover TODOs.
    Diff:
    {diff[:10000]}
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AuditResult,
                temperature=0.2,
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"[red]AI Error: {e}[/red]")
        return None

def explain_changes(diff: str):
    client = get_client()
    if not client: return None

    prompt = f"""
    Explain these changes to a non-technical person in plain English.
    Diff:
    {diff[:10000]}
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Explanation,
                temperature=0.2,
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"[red]AI Error: {e}[/red]")
        return None
