import os
import json
import pathlib
from git import Repo
from datetime import datetime
import typer  # ← ADDED THIS

def is_git_repo():
    return os.path.exists('.git')

def get_repo():
    return Repo('.')

def create_checkpoint():
    """Create a backup branch before risky operations"""
    try:
        # Check if there are any commits
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False
        )
        
        # If no commits exist (exit code 128), skip checkpoint
        if result.returncode != 0:
            print("[yellow]Skipping checkpoint - no commits yet[/yellow]")
            return None
        
        # Create backup branch
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_branch = f"gitguard-backup-{timestamp}"
        
        subprocess.run(
            ["git", "branch", backup_branch],
            check=True,
            capture_output=True
        )
        
        print(f"[green]✓[/green] Checkpoint created: {backup_branch}")
        return backup_branch
        
    except Exception as e:
        print(f"[yellow]Warning: Could not create checkpoint: {e}[/yellow]")
        return None

import subprocess

def run_git_commands(commands):
    print("\n[bold]Executing Git Commands:[/bold]",commands)
    for cmd in commands:
        print(f"[bold blue]Executing:[/bold blue] [cyan]{cmd}[/cyan]")
        try:
            # Using subprocess.run with shell=True for easier command execution of strings
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            if result.stdout:
                print(f"[dim]{result.stdout.strip()}[/dim]")
            print(f"[green]✓ Done[/green]")
        except subprocess.CalledProcessError as e:
            print(f"[red]Error executing command '{cmd}':[/red]")
            if e.stderr:
                print(f"[red]{e.stderr.strip()}[/red]")
            raise

def rollback_last():
    checkpoint_file = pathlib.Path('.git') / 'gitguard' / 'checkpoints.json'
    if not checkpoint_file.exists():
        print("[bold red]No checkpoints found![/bold red]")
        return
    
    try:
        with open(checkpoint_file) as f:
            checkpoints = json.load(f)
    except:
        print("[bold red]Error:[/bold red] Invalid checkpoint file.")
        return
    
    if not checkpoints:
        print("[yellow]No checkpoints available for rollback.[/yellow]")
        return
    
    last = checkpoints[0]
    print(f"\n[bold yellow]Rollback Target:[/bold yellow] {last['ref']} (Created: {last['created']})")
    
    if typer.confirm(f"Are you sure you want to revert the repository state to this checkpoint?", default=False):
        repo = get_repo()
        try:
            # We hard reset to the checkpoint branch's state
            repo.git.reset('--hard', last['ref'])
            print(f"[bold green]✅ Success![/bold green] Repository rolled back to [cyan]{last['ref']}[/cyan].")
            
            # Optional: Remove the checkpoint branch after rollback? 
            # Usually safer to keep it for a bit, but for MVP we can clean up
            # repo.git.branch('-D', last['ref'])
            
            # Remove used checkpoint from tracking
            checkpoints.pop(0)
            with open(checkpoint_file, 'w') as f:
                json.dump(checkpoints, f, indent=2)
        except Exception as e:
            print(f"[bold red]Rollback failed:[/bold red] {e}")
    else:
        print("[yellow]Rollback cancelled.[/yellow]")

