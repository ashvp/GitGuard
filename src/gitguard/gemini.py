from google import genai
from google.genai import types
import os
import typer
from pydantic import BaseModel, Field
import json
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class GitPlan(BaseModel):
    risk: str = Field(..., description="Risk level: LOW, MEDIUM, or HIGH")
    summary: str = Field(..., description="Short explanation of what will happen")
    commands: list[str] = Field(..., description="List of git commands to execute")
    missing_info_prompt: Optional[str] = Field(None, description="Question to ask user if info is missing (e.g. 'Enter repo URL')")
    explanation: Optional[str] = Field(None, description="Brief educational note about what these commands do")

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

class CommandExplanation(BaseModel):
    what_it_does: str = Field(..., description="Simple explanation of the command")
    use_cases: list[str] = Field(..., description="Common scenarios for using this command")
    risks: str = Field(..., description="Potential risks or side effects")
    related_commands: list[str] = Field(..., description="Related commands to learn")

def get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

def get_git_plan(intent: str, context: dict = None):
    client = get_client()
    if not client:
        print("[red]Error: GEMINI_API_KEY not found.[/red]")
        raise typer.Exit(1)

    context_str = ""
    if context:
        branches_str = ", ".join(context.get('all_branches', [])) if context.get('all_branches') else "None"
        context_str = f"""
        SYSTEM CONTEXT:
        - OS: {context.get('os', 'Unknown')}
        - Current Branch: {context.get('branch', 'Unknown')}
        - All Local Branches: {branches_str}
        - Remotes: {context.get('remotes', [])}
        - Has Uncommitted Changes: {context.get('has_uncommitted', False)}
        - Has Untracked Files: {context.get('has_untracked', False)}
        - Ahead of Remote: {context.get('ahead', 0)} commits
        - Behind Remote: {context.get('behind', 0)} commits
        """

    prompt = f"""
    You are GitGuard, an AI Git Safety Copilot designed to help beginners learn Git safely.
    The user's intent is: "{intent}"
    
    {context_str}
    
    Create a safe execution plan for this Git operation.
    
    STRICT CONSTRAINTS (SECURITY):
    - ONLY output git commands (no rm, cd, curl, wget, cat, etc.)
    - NO commands with && or || or ; (one command per array element)
    - NO commands with pipes (|) or redirects (>, <, >>)
    - NO backticks or $(...) command substitution
    - NO shell variables like $HOME, $USER
    - For Windows: Use forward slashes, avoid bash-specific syntax
    - Use explicit branch names from SYSTEM CONTEXT - you can see all branches listed there
    - IMPORTANT: When deleting multiple branches, create one 'git branch -D <branch>' command per branch
    
    RISK CLASSIFICATION:
    - LOW: Read-only operations (status, log, diff, show, branch -l, remote -v)
    - MEDIUM: Modifies but recoverable (commit, add, checkout <branch>, pull, reset --soft, stash)
    - HIGH: Destructive or hard to undo (reset --hard, push --force, branch -D, rebase, clean -fd, push with force)
    
    EDUCATIONAL APPROACH:
    - Add a brief 'explanation' field (1-2 sentences) teaching what these commands accomplish
    - This helps users learn as they use the tool
    
    MISSING INFORMATION HANDLING:
    - If a remote URL is needed but missing, set 'missing_info_prompt' to "Enter remote repository URL (e.g., https://github.com/user/repo.git)"
    - If a branch name is needed, set 'missing_info_prompt' to "Enter branch name"
    - Use placeholder {{{{INPUT}}}} in commands where user input goes
    - DO NOT ask for input if you can see the information in SYSTEM CONTEXT (like branch names)
    
    EXAMPLES:
    User: "delete all branches except main"
    Context shows: All Local Branches: main, feature-1, feature-2, old-branch
    Correct response should include these commands (one per branch to delete):
      - git branch -D feature-1
      - git branch -D feature-2
      - git branch -D old-branch
    
    IMPORTANT: Each command should be a complete, standalone git command that can be executed independently.
    """

    try:
        logger.info(f"Requesting AI plan for intent: {intent}")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GitPlan,
                temperature=0.2,
            )
        )
        plan = json.loads(response.text)
        logger.info(f"AI plan generated: {plan}")
        return plan
    except Exception as e:
        logger.error(f"AI plan generation failed: {e}")
        print(f"[red]AI Error: {e}[/red]")
        return {"risk": "UNKNOWN", "summary": "Failed to generate plan", "commands": []}

def get_fix_plan(intent: str, failed_commands: list[str], error_message: str, command_history: list[str] = None, context: dict = None):
    client = get_client()
    if not client: return None
    
    history_text = ""
    if command_history:
        history_text = "\nCOMMAND HISTORY:\n" + "\n".join([f"- {cmd}" for cmd in command_history[-5:]])  # Last 5 only

    context_str = ""
    if context:
        branches_str = ", ".join(context.get('all_branches', [])) if context.get('all_branches') else "None"
        context_str = f"""
        SYSTEM CONTEXT:
        - OS: {context.get('os', 'Unknown')}
        - Current Branch: {context.get('branch', 'Unknown')}
        - All Local Branches: {branches_str}
        - Remotes: {context.get('remotes', [])}
        - Has Uncommitted Changes: {context.get('has_uncommitted', False)}
        """

    prompt = f"""
    You are GitGuard fixing a failed Git operation.
    
    ORIGINAL INTENT: "{intent}"
    FAILED COMMANDS: {failed_commands}
    {history_text}
    {context_str}
    ERROR MESSAGE: "{error_message}"
    
    TASK: Provide a CORRECTED sequence of commands.
    
    ANALYSIS GUIDELINES:
    - Look at the All Local Branches list in SYSTEM CONTEXT to see available branches
    - If error mentions "unrelated histories": suggest `git pull origin <branch> --allow-unrelated-histories`
    - If error mentions "no upstream branch": suggest setting upstream with `git push -u origin <branch>`
    - If error mentions "remote URL": set 'missing_info_prompt' to ask for URL
    - If error mentions "permission denied": explain authentication issue (cannot fix programmatically)
    - If error mentions "conflict": suggest resolving conflicts manually or aborting
    
    CRITICAL CONSTRAINTS (same as before):
    - ONLY git commands
    - NO shell substitution like $(git ...) or backticks
    - Use literal branch names from SYSTEM CONTEXT
    - NO && or || or ; operators
    - For missing info (like remote URL), use 'missing_info_prompt' and {{INPUT}} placeholder
    
    AVOID INFINITE LOOPS:
    - DO NOT suggest the exact same commands that just failed
    - If the error is unfixable programmatically (auth, network), explain and set commands to []
    """

    try:
        logger.info(f"Requesting fix plan for error: {error_message}")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GitPlan,
                temperature=0.2,
            )
        )
        fix = json.loads(response.text)
        logger.info(f"Fix plan generated: {fix}")
        return fix
    except Exception as e:
        logger.error(f"Fix plan generation failed: {e}")
        return None

def generate_commit_message(diff: str):
    client = get_client()
    if not client: return None

    prompt = f"""
    Generate a Conventional Commit message for this diff.
    
    Conventional Commit Format:
    - Subject: <type>(<scope>): <description>
    - Types: feat, fix, docs, style, refactor, test, chore
    - Example: "feat(auth): add password reset functionality"
    
    Diff (truncated):
    {diff[:10000]}
    
    Generate:
    - subject: Keep under 50 characters
    - body: Bullet points explaining changes (2-5 bullets)
    """
    
    try:
        logger.info("Generating commit message")
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
        logger.error(f"Commit message generation failed: {e}")
        print(f"[red]AI Error: {e}[/red]")
        return None

def audit_code(diff: str):
    client = get_client()
    if not client: return None

    prompt = f"""
    Audit this git diff for common issues that beginners might miss:
    
    CHECK FOR:
    1. Hardcoded secrets (API keys, passwords, tokens)
    2. Sensitive data (emails, phone numbers, private keys)
    3. Console.log or debug statements left in
    4. TODO or FIXME comments
    5. Commented-out code blocks
    6. Obvious bugs (null pointer risks, infinite loops)
    7. Missing error handling
    
    Diff (truncated):
    {diff[:10000]}
    
    Be educational - explain WHY each issue matters.
    """
    
    try:
        logger.info("Running code audit")
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
        logger.error(f"Code audit failed: {e}")
        print(f"[red]AI Error: {e}[/red]")
        return None

def explain_changes(diff: str):
    client = get_client()
    if not client: return None

    prompt = f"""
    Explain these code changes to a non-technical person in plain English.
    Imagine explaining to a project manager or designer who doesn't code.
    
    Diff (truncated):
    {diff[:10000]}
    
    Provide:
    - summary: One paragraph overview
    - key_changes: 3-5 bullet points of the most important changes
    """
    
    try:
        logger.info("Generating change explanation")
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
        logger.error(f"Change explanation failed: {e}")
        print(f"[red]AI Error: {e}[/red]")
        return None

def explain_command(command: str):
    """Explain what a git command does - educational feature"""
    client = get_client()
    if not client: return None

    prompt = f"""
    Explain this git command to a beginner who is learning Git:
    
    Command: {command}
    
    Provide a beginner-friendly explanation including:
    - what_it_does: Simple 1-2 sentence explanation
    - use_cases: 2-3 common scenarios when you'd use this
    - risks: Any potential dangers or things to watch out for
    - related_commands: 2-3 related commands they should learn next
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CommandExplanation,
                temperature=0.3,
            )
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Command explanation failed: {e}")
        return None