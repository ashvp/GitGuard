import typer
from rich import print
from rich.panel import Panel
from rich.table import Table
import os
from dotenv import load_dotenv

from .gemini import get_git_plan, get_fix_plan, generate_commit_message, audit_code, explain_changes
from .git_ops import (
    create_checkpoint, 
    run_git_commands, 
    rollback_last, 
    is_git_repo, 
    get_staged_diff,
    get_diff,
    list_backup_branches,
    delete_branch
)

load_dotenv()
app = typer.Typer(help="GitGuard: The AI Assisted Safety Copilot")

def get_risk_color(risk: str):
    risk = risk.upper()
    if risk == "LOW": return "green"
    if risk == "MEDIUM": return "yellow"
    if risk == "HIGH": return "red"
    return "white"

def display_plan(plan):
    risk_color = get_risk_color(plan['risk'])
    
    plan_text = f"[bold]Interpreted Action:[/bold]\n"
    plan_text += f"• {plan['summary']}\n\n"
    plan_text += f"[bold]Risk Level:[/bold] [{risk_color}]{plan['risk'].upper()}[/{risk_color}]\n\n"
    plan_text += f"[bold]Planned Commands:[/bold]\n"
    for cmd in plan['commands']:
        plan_text += f"  [cyan]$ {cmd}[/cyan]\n"

    print(Panel(
        plan_text,
        title="[bold]Proposed Execution Plan[/bold]",
        border_style=risk_color,
        padding=(1, 2)
    ))

@app.command()
def run(intent: str = typer.Argument(..., help="What do you want to do? (e.g. 'undo last commit')")):
    """
    Interpret intent, evaluate risk, and execute git commands with safety.
    """
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)
    
    print(f"\n[bold blue]GitGuard[/bold blue] interpreting intent: [italic]'{intent}'[/italic]")
    
    # 1. Get AI plan
    with typer.progressbar(length=100, label="Thinking...") as progress:
        plan = get_git_plan(intent)
        progress.update(100)
    
    if not plan.get("commands"):
        print("[red]Could not determine any commands to run.[/red]")
        return

    # 2. Show beautiful plan
    display_plan(plan)
    
    # 3. Confirm and Execute with Retry Logic
    if typer.confirm("\nProceed with this plan?", default=False):
        
        # Create checkpoint ONCE before starting
        try:
            checkpoint = create_checkpoint()
            print(f"[green]✓ Safety checkpoint created: {checkpoint}[/green]")
        except Exception as e:
            print(f"[yellow]Warning: Checkpoint failed ({e}), proceeding anyway...[/yellow]")

        current_commands = plan['commands']
        attempt = 0
        max_retries = 3
        command_history = [] 

        while attempt < max_retries:
            try:
                run_git_commands(current_commands)
                command_history.extend(current_commands)
                print(f"\n[bold green]Success![/bold green] Operation completed safely.")
                print(f"[dim]Undo anytime with: gitguard rollback[/dim]")
                return
            
            except Exception as e:
                attempt += 1
                print(f"\n[bold red]Execution failed (Attempt {attempt}/{max_retries}).[/bold red]")
                print(f"[red]Error: {e}[/red]")

                if attempt >= max_retries:
                    print("\n[bold red]Max retries reached.[/bold red]")
                    break

                print("\n[bold yellow]Consulting AI for a fix...[/bold yellow]")
                with typer.progressbar(length=100, label="Analyzing error...") as progress:
                    fix_plan = get_fix_plan(intent, current_commands, str(e), command_history)
                    progress.update(100)
                
                if not fix_plan or not fix_plan.get('commands'):
                    print("[red]AI could not find a fix.[/red]")
                    break

                # Handle User Input (e.g. repo URL)
                if fix_plan.get('missing_info_prompt'):
                    print(f"\n[bold cyan]Input Required:[/bold cyan] {fix_plan['missing_info_prompt']}")
                    user_input = typer.prompt("Value")
                    
                    # Inject input into commands
                    new_commands = []
                    for cmd in fix_plan['commands']:
                        new_commands.append(cmd.replace("{INPUT}", user_input))
                    fix_plan['commands'] = new_commands

                print("\n[bold]AI Suggested Fix:[/bold]")
                display_plan(fix_plan)

                if typer.confirm("\nApply this fix?", default=True):
                    command_history.extend(current_commands)
                    current_commands = fix_plan['commands']
                else:
                    print("[yellow]Fix cancelled by user.[/yellow]")
                    break

        if typer.confirm("\nWould you like to rollback to the checkpoint immediately?", default=True):
            rollback_last()
    else:
        print("\n[yellow]Cancelled. No changes made to your repository.[/yellow]")

@app.command()
def rollback():
    """Undo the last GitGuard operation using safety checkpoints."""
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)
    rollback_last()

@app.command()
def commit():
    """Generate a conventional commit message from staged changes."""
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)

    diff = get_staged_diff()
    if not diff:
        print("[yellow]No staged changes found. Stage your files first (git add ...).[/yellow]")
        return

    print("[bold blue]Generating commit message...[/bold blue]")
    with typer.progressbar(length=100, label="Thinking...") as progress:
        msg = generate_commit_message(diff)
        progress.update(100)
    
    if not msg:
        print("[red]Failed to generate message.[/red]")
        return

    print(f"\n[bold green]Subject:[/bold green] {msg['subject']}")
    print(f"[bold green]Body:[/bold green]\n{msg['body']}")
    
    if typer.confirm("\nCommit with this message?", default=True):
        full_msg = f"{msg['subject']}\n\n{msg['body']}"
        run_git_commands([f'git commit -m "{full_msg}"'])
    else:
        print("[yellow]Commit cancelled.[/yellow]")

@app.command()
def audit():
    """Audit staged code for secrets, bugs, and TODOs."""
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)

    diff = get_staged_diff()
    if not diff:
        print("[yellow]No staged changes to audit.[/yellow]")
        return

    print("[bold blue]Auditing code...[/bold blue]")
    with typer.progressbar(length=100, label="Scanning...") as progress:
        result = audit_code(diff)
        progress.update(100)
    
    if not result:
        print("[red]Audit failed.[/red]")
        return

    color = "green" if result['passed'] else "red"
    print(Panel(
        "\n".join(f"- {i}" for i in result['issues']),
        title=f"[bold {color}]Audit Result: {result['severity']}[/bold {color}]",
        border_style=color
    ))
    
    if not result['passed']:
        print("[bold red]Warning: Issues found![/bold red]")

@app.command()
def clean():
    """Cleanup old GitGuard checkpoints."""
    branches = list_backup_branches()
    if not branches:
        print("[green]No checkpoints found.[/green]")
        return

    table = Table(title="GitGuard Checkpoints")
    table.add_column("Branch Name", style="cyan")
    for b in branches:
        table.add_row(b)
    
    print(table)
    
    if typer.confirm(f"Delete all {len(branches)} checkpoint branches?", default=False):
        for b in branches:
            if delete_branch(b):
                print(f"[green]Deleted {b}[/green]")
            else:
                print(f"[red]Failed to delete {b}[/red]")
    else:
        print("[yellow]Cancelled.[/yellow]")

@app.command()
def explain():
    """Explain changes in plain English."""
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)

    diff = get_diff()
    if not diff:
        print("[yellow]No changes found to explain.[/yellow]")
        return

    print("[bold blue]Analyzing changes...[/bold blue]")
    with typer.progressbar(length=100, label="Reading diff...") as progress:
        expl = explain_changes(diff)
        progress.update(100)
    
    if not expl:
        print("[red]Failed to explain.[/red]")
        return

    print(Panel(
        f"{expl['summary']}\n\n[bold]Key Changes:[/bold]\n" + "\n".join(f"- {k}" for k in expl['key_changes']),
        title="[bold]Explanation[/bold]",
        border_style="blue"
    ))

if __name__ == "__main__":
    app()