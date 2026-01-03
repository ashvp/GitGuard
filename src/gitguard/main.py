import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.console import Console
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import logging
from datetime import datetime

from .gemini import (
    get_git_plan, 
    get_fix_plan, 
    generate_commit_message, 
    audit_code, 
    explain_changes,
    explain_command
)
from .git_ops import (
    create_checkpoint, 
    run_git_commands, 
    rollback_last, 
    is_git_repo, 
    get_staged_diff,
    get_diff,
    list_backup_branches,
    delete_branch,
    gather_context,
    sanitize_git_input
)

load_dotenv()

# Setup logging
def setup_logging():
    log_dir = Path.home() / '.gitguard' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f'gitguard_{datetime.now():%Y%m%d}.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout) if os.getenv('GITGUARD_DEBUG') else logging.NullHandler()
        ]
    )

setup_logging()
logger = logging.getLogger(__name__)

app = typer.Typer(help="GitGuard: AI-Powered Git Safety Copilot for Learning")
console = Console()

def get_risk_color(risk: str):
    risk = risk.upper()
    if risk == "LOW": return "green"
    if risk == "MEDIUM": return "yellow"
    if risk == "HIGH": return "red"
    return "white"

def display_plan(plan):
    """Display execution plan with beautiful formatting."""
    risk_color = get_risk_color(plan['risk'])
    
    plan_text = f"[bold]Interpreted Action:[/bold]\n"
    plan_text += f"• {plan['summary']}\n\n"
    plan_text += f"[bold]Risk Level:[/bold] [{risk_color}]{plan['risk'].upper()}[/{risk_color}]\n\n"
    
    if plan.get('explanation'):
        plan_text += f"[bold cyan]💡 Learning Note:[/bold cyan]\n{plan['explanation']}\n\n"
    
    plan_text += f"[bold]Planned Commands:[/bold]\n"
    for i, cmd in enumerate(plan['commands'], 1):
        plan_text += f"  {i}. [cyan]{cmd}[/cyan]\n"

    print(
        Panel(
            plan_text,
            title="[bold]Proposed Execution Plan[/bold]",
            border_style=risk_color,
            padding=(1, 2)
        )
    )

@app.command()
def run(
    intent: str = typer.Argument(..., help="What do you want to do? (e.g. 'undo last commit')"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show plan without executing"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompts")
):
    """
    Interpret natural language intent and execute git commands safely.
    
    Examples:
      gitguard run "undo last commit"
      gitguard run "push to github" --dry-run
      gitguard run "create new branch for feature"
    """
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        print("[dim]Hint: Run 'git init' to create a new repository[/dim]")
        raise typer.Exit(1)
    
    logger.info(f"User intent: {intent}")
    print(f"\n[bold blue]GitGuard[/bold blue] interpreting intent: [italic]'{intent}'[/italic]")
    
    # Gather context
    context = gather_context()
    logger.info(f"Context: {context}")

    # Get AI plan
    with console.status("[bold blue]Thinking...", spinner="dots"):
        plan = get_git_plan(intent, context)
    
    if not plan.get("commands"):
        print("[red]Could not determine any commands to run.[/red]")
        print("[dim]Try rephrasing your request or being more specific.[/dim]")
        return

    # Handle missing info prompt from initial plan
    if plan.get('missing_info_prompt'):
        print(f"\n[bold cyan]Input Required:[/bold cyan] {plan['missing_info_prompt']}")
        user_input = typer.prompt("Value")
        
        # Determine input type from prompt
        input_type = "general"
        if "url" in plan['missing_info_prompt'].lower():
            input_type = "url"
        elif "branch" in plan['missing_info_prompt'].lower():
            input_type = "branch"
        
        try:
            sanitized_input = sanitize_git_input(user_input, input_type)
            new_commands = []
            for cmd in plan['commands']:
                new_commands.append(cmd.replace("{INPUT}", sanitized_input))
            plan['commands'] = new_commands
        except ValueError as e:
            print(f"[bold red]Invalid input:[/bold red] {e}")
            return

    # Display plan
    display_plan(plan)
    
    # Dry run mode
    if dry_run:
        print("\n[yellow]Dry run mode - no changes made[/yellow]")
        print("[dim]Remove --dry-run flag to execute these commands[/dim]")
        return
    
    # Confirm and execute with retry logic
    if force or typer.confirm("\nProceed with this plan?", default=False):
        
        # Create checkpoint ONCE before starting (if MEDIUM or HIGH risk)
        checkpoint = None
        if plan['risk'].upper() in ['MEDIUM', 'HIGH']:
            try:
                checkpoint = create_checkpoint()
            except Exception as e:
                logger.warning(f"Checkpoint creation failed: {e}")
                print(f"[yellow]Warning: Checkpoint failed ({e}), proceeding anyway...[/yellow]")

        current_commands = plan['commands']
        attempt = 0
        max_retries = 3
        command_history = []
        seen_command_sets = set()  # Prevent infinite loops

        while attempt < max_retries:
            # Check for duplicate command sets
            cmd_signature = "|".join(current_commands)
            if cmd_signature in seen_command_sets:
                print("[bold red]AI is suggesting the same commands repeatedly. Stopping.[/bold red]")
                logger.error("Detected command loop")
                break
            seen_command_sets.add(cmd_signature)
            
            try:
                run_git_commands(current_commands)
                command_history.extend(current_commands)
                print(f"\n[bold green]✅ Success![/bold green] Operation completed safely.")
                if checkpoint:
                    print(f"[dim]Undo anytime with: gitguard rollback[/dim]")
                return
            
            except Exception as e:
                attempt += 1
                logger.error(f"Command execution failed (attempt {attempt}): {e}")
                print(f"\n[bold red]Execution failed (Attempt {attempt}/{max_retries}).[/bold red]")
                print(f"[red]Error: {e}[/red]")

                if attempt >= max_retries:
                    print("\n[bold red]Max retries reached.[/bold red]")
                    print("[yellow]You may need to fix this manually.[/yellow]")
                    if checkpoint:
                        print(f"[dim]Consider rolling back with: gitguard rollback[/dim]")
                    break

                print("\n[bold yellow]Consulting AI for a fix...[/bold yellow]")
                
                with console.status("[bold yellow]Analyzing error...", spinner="dots"):
                    context = gather_context()  # Re-gather in case state changed
                    fix_plan = get_fix_plan(intent, current_commands, str(e), command_history, context)
                
                if not fix_plan or not fix_plan.get('commands'):
                    print("[red]AI could not determine a fix.[/red]")
                    print("[yellow]You may need to resolve this manually.[/yellow]")
                    if checkpoint:
                        print(f"[dim]Consider rolling back with: gitguard rollback[/dim]")
                    break

                # Handle missing info in fix
                if fix_plan.get('missing_info_prompt'):
                    print(f"\n[bold cyan]Input Required:[/bold cyan] {fix_plan['missing_info_prompt']}")
                    user_input = typer.prompt("Value")
                    
                    input_type = "general"
                    if "url" in fix_plan['missing_info_prompt'].lower():
                        input_type = "url"
                    elif "branch" in fix_plan['missing_info_prompt'].lower():
                        input_type = "branch"
                    
                    try:
                        sanitized_input = sanitize_git_input(user_input, input_type)
                        new_commands = []
                        for cmd in fix_plan['commands']:
                            new_commands.append(cmd.replace("{INPUT}", sanitized_input))
                        fix_plan['commands'] = new_commands
                    except ValueError as e:
                        print(f"[bold red]Invalid input:[/bold red] {e}")
                        break

                print("\n[bold]AI Suggested Fix:[/bold]")
                display_plan(fix_plan)

                if force or typer.confirm("\nApply this fix?", default=True):
                    command_history.extend(current_commands)
                    current_commands = fix_plan['commands']
                else:
                    print("[yellow]Fix cancelled by user.[/yellow]")
                    if checkpoint:
                        print(f"[dim]You can rollback with: gitguard rollback[/dim]")
                    break

        # If we broke out of the loop due to failure, offer rollback
        if attempt >= max_retries and checkpoint:
            if typer.confirm("\nWould you like to rollback to the checkpoint?", default=True):
                rollback_last()
    else:
        print("\n[yellow]Cancelled. No changes made to your repository.[/yellow]")

@app.command()
def rollback():
    """
    Undo the last GitGuard operation using safety checkpoints.
    
    This will revert your repository to the state before the last
    risky operation was performed.
    """
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)
    rollback_last()

@app.command()
def commit():
    """
    Generate a conventional commit message from staged changes.
    
    GitGuard will analyze your staged changes and create a properly
    formatted commit message following Conventional Commits specification.
    """
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)

    diff = get_staged_diff()
    if not diff:
        print("[yellow]No staged changes found.[/yellow]")
        print("[dim]Stage your files first: git add <files>[/dim]")
        return

    print("[bold blue]Generating commit message...[/bold blue]")
    
    with console.status("[bold blue]Analyzing changes...", spinner="dots"):
        msg = generate_commit_message(diff)
    
    if not msg:
        print("[red]Failed to generate message.[/red]")
        return

    print(f"\n[bold green]Subject:[/bold green] {msg['subject']}")
    print(f"[bold green]Body:[/bold green]\n{msg['body']}")
    
    if typer.confirm("\nCommit with this message?", default=True):
        full_msg = f"{msg['subject']}\n\n{msg['body']}"
        # Escape quotes for shell
        full_msg = full_msg.replace('"', '\\"')
        run_git_commands([f'git commit -m "{full_msg}"'])
        print("[green]✓ Committed successfully![/green]")
    else:
        print("[yellow]Commit cancelled.[/yellow]")
        print("[dim]You can commit manually with: git commit[/dim]")

@app.command()
def audit():
    """
    Audit staged code for potential issues before committing.
    
    Checks for:
    - Hardcoded secrets (API keys, passwords)
    - Debug statements left in code
    - TODO comments
    - Obvious bugs
    """
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)

    diff = get_staged_diff()
    if not diff:
        print("[yellow]No staged changes to audit.[/yellow]")
        print("[dim]Stage your files first: git add <files>[/dim]")
        return

    print("[bold blue]Auditing code...[/bold blue]")
    
    with console.status("[bold blue]Scanning for issues...", spinner="dots"):
        result = audit_code(diff)
    
    if not result:
        print("[red]Audit failed.[/red]")
        return

    color = "green" if result['passed'] else "red"
    
    if result['issues']:
        issues_text = "\n".join(f"• {i}" for i in result['issues'])
    else:
        issues_text = "No issues found! ✓"
    
    print(Panel(
        issues_text,
        title=f"[bold {color}]Audit Result: {result['severity']}[/bold {color}]",
        border_style=color,
        padding=(1, 2)
    ))
    
    if not result['passed']:
        print("\n[bold red]⚠️  Warning: Issues found![/bold red]")
        print("[yellow]Consider fixing these issues before committing.[/yellow]")
    else:
        print("\n[bold green]✓ Code looks good![/bold green]")

@app.command()
def clean():
    """
    Cleanup old GitGuard checkpoint branches.
    
    This removes backup branches created by GitGuard to free up space.
    """
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)
        
    branches = list_backup_branches()
    if not branches:
        print("[green]No checkpoints found. Everything is clean! ✓[/green]")
        return

    table = Table(title="GitGuard Checkpoints")
    table.add_column("#", style="dim")
    table.add_column("Branch Name", style="cyan")
    
    for i, b in enumerate(branches, 1):
        table.add_row(str(i), b)
    
    print(table)
    print(f"\n[yellow]Total: {len(branches)} checkpoint(s)[/yellow]")
    
    if typer.confirm(f"Delete all {len(branches)} checkpoint branches?", default=False):
        deleted = 0
        for b in branches:
            if delete_branch(b):
                print(f"[green]✓ Deleted {b}[/green]")
                deleted += 1
            else:
                print(f"[red]✗ Failed to delete {b}[/red]")
        print(f"\n[green]Cleaned up {deleted}/{len(branches)} checkpoints.[/green]")
    else:
        print("[yellow]Cancelled.[/yellow]")

@app.command()
def explain():
    """
    Explain your changes in plain English.
    
    GitGuard will analyze your git diff and explain what changed
    in a way that non-technical people can understand.
    """
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)

    diff = get_diff()
    if not diff:
        print("[yellow]No changes found to explain.[/yellow]")
        print("[dim]Make some changes first, then try again.[/dim]")
        return

    print("[bold blue]Analyzing changes...[/bold blue]")
    
    with console.status("[bold blue]Reading diff...", spinner="dots"):
        expl = explain_changes(diff)
    
    if not expl:
        print("[red]Failed to explain.[/red]")
        return

    key_changes_text = "\n".join(f"• {k}" for k in expl['key_changes'])
    
    print(Panel(
        f"{expl['summary']}\n\n[bold cyan]Key Changes:[/bold cyan]\n{key_changes_text}",
        title="[bold]Plain English Explanation[/bold]",
        border_style="blue",
        padding=(1, 2)
    ))

@app.command()
def learn(command: str = typer.Argument(..., help="Git command to learn about")):
    """
    Learn what a git command does.
    
    Examples:
      gitguard learn "git reset --hard"
      gitguard learn "git rebase -i"
    """
    print(f"[bold blue]Learning about:[/bold blue] [cyan]{command}[/cyan]\n")
    
    with console.status("[bold blue]Fetching explanation...", spinner="dots"):
        explanation = explain_command(command)
    
    if not explanation:
        print("[red]Failed to get explanation.[/red]")
        return
    
    # Display structured explanation
    print(Panel(
        f"[bold]What it does:[/bold]\n{explanation['what_it_does']}\n\n"
        f"[bold cyan]Common use cases:[/bold cyan]\n" + 
        "\n".join(f"• {uc}" for uc in explanation['use_cases']) + "\n\n"
        f"[bold yellow]⚠️  Potential risks:[/bold yellow]\n{explanation['risks']}\n\n"
        f"[bold green]Related commands to learn:[/bold green]\n" +
        "\n".join(f"• {rc}" for rc in explanation['related_commands']),
        title="[bold]Command Explanation[/bold]",
        border_style="blue",
        padding=(1, 2)
    ))

@app.command()
def status():
    """
    Show GitGuard status and system info.
    """
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)
    
    context = gather_context()
    checkpoints = list_backup_branches()
    
    table = Table(title="GitGuard Status", show_header=False)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")
    
    table.add_row("Current Branch", context['branch'])
    table.add_row("Remotes", ", ".join(context['remotes']) if context['remotes'] else "None")
    table.add_row("Uncommitted Changes", "Yes" if context['has_uncommitted'] else "No")
    table.add_row("Untracked Files", "Yes" if context['has_untracked'] else "No")
    
    if context['ahead'] or context['behind']:
        sync_status = []
        if context['ahead']:
            sync_status.append(f"{context['ahead']} ahead")
        if context['behind']:
            sync_status.append(f"{context['behind']} behind")
        table.add_row("Sync Status", ", ".join(sync_status))
    
    table.add_row("Checkpoints", str(len(checkpoints)))
    
    print(table)

if __name__ == "__main__":
    app()