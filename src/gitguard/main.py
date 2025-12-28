import typer
from rich import print
from rich.panel import Panel
import os
from dotenv import load_dotenv

from .gemini import get_git_plan
from .git_ops import create_checkpoint, run_git_commands, rollback_last, is_git_repo

load_dotenv()
app = typer.Typer(help="GitGuard: The AI Assisted Safety Copilot")

def get_risk_color(risk: str):
    risk = risk.upper()
    if risk == "LOW": return "green"
    if risk == "MEDIUM": return "yellow"
    if risk == "HIGH": return "red"
    return "white"

@app.command()
def run(intent: str = typer.Argument(..., help="What do you want to do? (e.g. 'undo last commit')")):
    """
    Interpret intent, evaluate risk, and execute git commands with safety.
    """
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)
    
    print(f"\n[bold blue]GitGuard[/bold blue] interpreting intent: [italic]\"{intent}\"[/italic]")
    
    # 1. Get AI plan
    with typer.progressbar(length=100, label="Thinking...") as progress:
        plan = get_git_plan(intent)
        progress.update(100)
    
    if not plan.get("commands"):
        print("[red]Could not determine any commands to run.[/red]")
        return

    # 2. Show beautiful plan
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
    
    # 3. Confirm
    if typer.confirm("\nProceed with this plan?", default=False):
        try:
            checkpoint = create_checkpoint()
            print(f"[green]✓ Safety checkpoint created: {checkpoint}[/green]")
            run_git_commands(plan['commands'])
            print(f"\n[bold green]Success![/bold green] Operation completed safely.")
            print(f"[dim]Undo anytime with: gitguard rollback[/dim]")
        except Exception as e:
            print(f"\n[bold red]Execution failed.[/bold red]", e)
            if typer.confirm("Would you like to rollback to the checkpoint immediately?", default=True):
                rollback_last()
    else:
        print("\n[yellow]Cancelled. No changes made to your repository.[/yellow]")

@app.command()
def rollback():
    """
    Undo the last GitGuard operation using safety checkpoints.
    """
    if not is_git_repo():
        print("[bold red]Error:[/bold red] Not a git repository.")
        raise typer.Exit(1)
    rollback_last()


if __name__ == "__main__":
    app()
