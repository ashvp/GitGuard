import os
import json
import pathlib
import subprocess
import shlex
import re
from git import Repo
from datetime import datetime, timedelta
import typer
from rich import print
import logging

logger = logging.getLogger(__name__)

MAX_CHECKPOINTS = 10
CHECKPOINT_RETENTION_DAYS = 30

def is_git_repo():
    return os.path.exists('.git')

def get_repo():
    return Repo('.')

def get_current_branch():
    """Returns the current active branch name with better edge case handling."""
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True, 
            text=True, 
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        # Detached HEAD state
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, 
                text=True, 
                check=True
            )
            return f"detached@{result.stdout.strip()}"
        except:
            # Brand new repo, no commits yet
            return "main (no commits yet)"

def get_remotes():
    """Returns a list of configured remotes."""
    try:
        result = subprocess.run(
            ["git", "remote"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip().splitlines()
    except:
        return []

def gather_context():
    """Gather comprehensive git repository context."""
    context = {
        "os": os.name,  # 'posix' or 'nt'
        "branch": get_current_branch(),
        "remotes": get_remotes(),
        "has_uncommitted": False,
        "has_untracked": False,
        "ahead": 0,
        "behind": 0
    }
    
    try:
        # Check for uncommitted/untracked changes
        result = subprocess.run(
            ["git", "status", "--porcelain"], 
            capture_output=True, 
            text=True,
            check=True
        )
        status_output = result.stdout.strip()
        context["has_uncommitted"] = bool(status_output)
        context["has_untracked"] = "??" in status_output
        
        # Check ahead/behind status
        result = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
            capture_output=True, 
            text=True, 
            check=False
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if len(parts) == 2:
                context["ahead"] = int(parts[0])
                context["behind"] = int(parts[1])
    except Exception as e:
        logger.warning(f"Could not gather full context: {e}")
    
    return context

def sanitize_git_input(user_input: str, input_type: str = "general") -> str:
    """
    Sanitize user input for safe use in git commands.
    
    Args:
        user_input: The raw user input
        input_type: Type hint for validation (url, branch, tag, general)
    
    Returns:
        Sanitized input string
        
    Raises:
        ValueError: If input contains dangerous characters
    """
    if not user_input:
        raise ValueError("Input cannot be empty")
    
    user_input = user_input.strip()
    
    # Check for shell metacharacters
    dangerous_chars = [';', '&', '|', '$', '`', '(', ')', '<', '>', '\n', '\r', '\x00']
    for char in dangerous_chars:
        if char in user_input:
            raise ValueError(f"Invalid character in input: {repr(char)}")
    
    # Type-specific validation
    if input_type == "url":
        # Git URLs should start with http(s):// or git@
        if not re.match(r'^(https?://|git@)', user_input):
            raise ValueError("Invalid git URL format. Must start with http://, https://, or git@")
        # Basic URL sanity check
        if ' ' in user_input:
            raise ValueError("URLs cannot contain spaces")
            
    elif input_type == "branch":
        # Git branch naming rules
        if not re.match(r'^[a-zA-Z0-9/_.-]+$', user_input):
            raise ValueError("Branch names can only contain letters, numbers, /, _, ., and -")
        if user_input.startswith('-'):
            raise ValueError("Branch names cannot start with -")
        if '..' in user_input or user_input.endswith('.lock'):
            raise ValueError("Invalid branch name pattern")
    
    elif input_type == "tag":
        # Similar rules to branches
        if not re.match(r'^[a-zA-Z0-9/_.-]+$', user_input):
            raise ValueError("Tag names can only contain letters, numbers, /, _, ., and -")
    
    return user_input

def create_checkpoint():
    """Create a backup branch before risky operations with automatic cleanup."""
    try:
        # Check if there are any commits
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            print("[yellow]Skipping checkpoint - no commits yet[/yellow]")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_branch = f"gitguard-backup-{timestamp}"
        
        subprocess.run(
            ["git", "branch", backup_branch],
            check=True,
            capture_output=True
        )
        logger.info(f"Created checkpoint branch: {backup_branch}")

        # Try to stash current changes
        stash_result = subprocess.run(
            ["git", "stash", "create"],
            capture_output=True,
            text=True,
            check=False
        )
        stash_hash = stash_result.stdout.strip()
        
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
        checkpoints.insert(0, new_checkpoint)
        
        # Auto-cleanup: Keep only MAX_CHECKPOINTS most recent
        if len(checkpoints) > MAX_CHECKPOINTS:
            for old_checkpoint in checkpoints[MAX_CHECKPOINTS:]:
                try:
                    subprocess.run(
                        ["git", "branch", "-D", old_checkpoint['ref']],
                        capture_output=True,
                        check=False
                    )
                    logger.info(f"Auto-deleted old checkpoint: {old_checkpoint['ref']}")
                except:
                    pass
            checkpoints = checkpoints[:MAX_CHECKPOINTS]
        
        # Auto-cleanup: Delete checkpoints older than CHECKPOINT_RETENTION_DAYS
        cutoff_date = datetime.now() - timedelta(days=CHECKPOINT_RETENTION_DAYS)
        checkpoints_to_keep = []
        for cp in checkpoints:
            try:
                cp_date = datetime.strptime(cp['created'], "%Y%m%d_%H%M%S")
                if cp_date >= cutoff_date:
                    checkpoints_to_keep.append(cp)
                else:
                    subprocess.run(
                        ["git", "branch", "-D", cp['ref']],
                        capture_output=True,
                        check=False
                    )
                    logger.info(f"Auto-deleted expired checkpoint: {cp['ref']}")
            except:
                checkpoints_to_keep.append(cp)  # Keep if we can't parse date
        
        checkpoints = checkpoints_to_keep
        
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoints, f, indent=2)
        
        msg = f"[green]✓[/green] Checkpoint created: {backup_branch}"
        if stash_hash:
            msg += " (with local changes saved)"
        print(msg)
        return backup_branch
        
    except Exception as e:
        logger.error(f"Checkpoint creation failed: {e}")
        print(f"[yellow]Warning: Could not create checkpoint: {e}[/yellow]")
        return None

def validate_git_command(cmd: str) -> bool:
    """
    Validate that a command is a safe git command.
    
    Returns:
        True if valid, False otherwise
    """
    try:
        parts = shlex.split(cmd)
    except ValueError:
        logger.warning(f"Command failed to parse: {cmd}")
        return False
    
    if not parts:
        return False
    
    # Must be a git command
    if parts[0] != 'git':
        logger.warning(f"Non-git command rejected: {parts[0]}")
        return False
    
    # Check for shell operators that shouldn't be in a single command
    dangerous_patterns = ['&&', '||', ';', '|', '>', '<', '>>']
    for pattern in dangerous_patterns:
        if pattern in cmd:
            logger.warning(f"Command contains dangerous pattern {pattern}: {cmd}")
            return False
    
    # Check for command substitution
    if '$(' in cmd or '`' in cmd:
        logger.warning(f"Command contains substitution: {cmd}")
        return False
    
    return True

def run_git_commands(commands):
    """
    Execute git commands with enhanced security.
    
    Args:
        commands: List of git command strings
        
    Raises:
        subprocess.CalledProcessError: If a command fails
    """
    print("\n[bold]Executing Git Commands:[/bold]")
    
    for cmd in commands:
        # Security validation
        if not validate_git_command(cmd):
            print(f"[bold red]Security check failed for command:[/bold red] {cmd}")
            raise ValueError(f"Command failed security validation: {cmd}")
        
        print(f"[bold blue]Executing:[/bold blue] [cyan]{cmd}[/cyan]")
        
        try:
            # Parse command safely
            cmd_parts = shlex.split(cmd)
            
            # Execute without shell
            result = subprocess.run(
                cmd_parts,
                check=True,
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            
            if result.stdout:
                print(f"[dim]{result.stdout.strip()}[/dim]")
            
            logger.info(f"Command succeeded: {cmd}")
            print(f"[green]✓ Done[/green]")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {cmd} | Error: {e.stderr}")
            print(f"[red]Error executing command '{cmd}':[/red]")
            if e.stderr:
                print(f"[red]{e.stderr.strip()}[/red]")
            raise

def rollback_last():
    """Rollback to the most recent checkpoint."""
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
            repo.git.reset('--hard', last['ref'])
            logger.info(f"Rolled back to: {last['ref']}")
            print(f"[bold green]✅ Success![/bold green] Repository rolled back to [cyan]{last['ref']}[/cyan].")
            
            if last.get('stash'):
                print("[blue]Restoring local changes...[/blue]")
                try:
                    repo.git.stash('apply', last['stash'])
                    print("[green]✓ Local changes restored.[/green]")
                except Exception as e:
                    print(f"[yellow]Warning: Could not restore local changes cleanly: {e}[/yellow]")

            checkpoints.pop(0)
            with open(checkpoint_file, 'w') as f:
                json.dump(checkpoints, f, indent=2)
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            print(f"[bold red]Rollback failed:[/bold red] {e}")
    else:
        print("[yellow]Rollback cancelled.[/yellow]")

def get_staged_diff():
    """Get diff of staged changes."""
    try:
        return subprocess.check_output(["git", "diff", "--cached"], text=True)
    except:
        return ""

def get_diff():
    """Get diff of all changes."""
    try:
        return subprocess.check_output(["git", "diff", "HEAD"], text=True)
    except:
        return ""

def list_backup_branches():
    """List all GitGuard checkpoint branches."""
    repo = get_repo()
    return [b.name for b in repo.branches if b.name.startswith("gitguard-backup-")]

def delete_branch(branch_name):
    """Delete a branch safely."""
    try:
        subprocess.run(["git", "branch", "-D", branch_name], check=True, capture_output=True)
        logger.info(f"Deleted branch: {branch_name}")
        return True
    except:
        logger.error(f"Failed to delete branch: {branch_name}")
        return False