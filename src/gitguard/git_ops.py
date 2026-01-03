import os
import json
import pathlib
import subprocess
from git import Repo
from datetime import datetime
import typer
from rich import print

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

        # Snapshot local changes (stash) without modifying working dir
        # git stash create returns a commit hash if there are changes
        stash_result = subprocess.run(
            ["git", "stash", "create"],
            capture_output=True,
            text=True,
            check=False
        )
        stash_hash = stash_result.stdout.strip()
        
        # Save to checkpoints.json
        checkpoint_dir = pathlib.Path('.git') / 'gitguard'
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_file = checkpoint_dir / 'checkpoints.json'
        
        checkpoints = []
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file) as f:
                    checkpoints = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        new_checkpoint = {
            "ref": backup_branch,
            "created": timestamp,
            "stash": stash_hash if stash_hash else None
        }
        # Insert at the beginning so rollback_last (checkpoints[0]) gets the latest
        checkpoints.insert(0, new_checkpoint)
        
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoints, f, indent=2)
        
        msg = f"[green]✓[/green] Checkpoint created: {backup_branch}"
        if stash_hash:
            msg += " (with local changes saved)"
        print(msg)
        return backup_branch
        
    except Exception as e:
        print(f"[yellow]Warning: Could not create checkpoint: {e}[/yellow]")
        return None

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
            
            # Restore local changes if they were stashed
            if last.get('stash'):
                print("[blue]Restoring local changes...[/blue]")
                try:
                    repo.git.stash('apply', last['stash'])
                    print("[green]✓ Local changes restored.[/green]")
                except Exception as e:
                    print(f"[yellow]Warning: Could not restore local changes cleanly: {e}[/yellow]")

            # Remove used checkpoint from tracking
            checkpoints.pop(0)
            with open(checkpoint_file, 'w') as f:
                json.dump(checkpoints, f, indent=2)
        except Exception as e:
            print(f"[bold red]Rollback failed:[/bold red] {e}")
    else:
        print("[yellow]Rollback cancelled.[/yellow]")

def get_staged_diff():
    try:
        return subprocess.check_output(["git", "diff", "--cached"], text=True)
    except:
        return ""

def get_diff():
    try:
        # Diff of working directory vs HEAD
        return subprocess.check_output(["git", "diff", "HEAD"], text=True)
    except:
        return ""

def list_backup_branches():
    repo = get_repo()
    return [b.name for b in repo.branches if b.name.startswith("gitguard-backup-")]

def delete_branch(branch_name):
    try:
        subprocess.run(["git", "branch", "-D", branch_name], check=True, capture_output=True)
        return True
    except:
        return False
