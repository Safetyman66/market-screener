#!/usr/bin/env python3
"""
GitHub Repository Synchronisation Utility
Automates git status check, stashing local changes, pull (with rebase), 
pop stash, staging all modified/new files, commit, and push.
"""

import subprocess
import sys

def run_git_command(args):
    try:
        result = subprocess.run(
            ["git"] + args,
            check=True,
            text=True,
            capture_output=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git command 'git {' '.join(args)}' failed: {e.stderr.strip()}")
        sys.exit(1)

def synchronise_repository(commit_message="Auto-sync market intelligence, code, and knowledge base"):
    print("[*] Checking git repository status...")
    
    # Configure user identity locally
    run_git_command(["config", "--local", "user.name", "github-actions[bot]"])
    run_git_command(["config", "--local", "user.email", "github-actions[bot]@users.noreply.github.com"])

    # Stash any local changes first to prevent pull blockages
    print("[*] Stashing any local changes...")
    stash_result = run_git_command(["stash"])
    has_stashed = "No local changes to save" not in stash_result

    print("[*] Pulling latest remote changes (rebase mode)...")
    run_git_command(["pull", "--rebase", "origin", "main"])

    if has_stashed:
        print("[*] Restoring stashed local changes...")
        try:
            run_git_command(["stash", "pop"])
        except Exception:
            print("[!] Note: Stash pop had merge conflicts or applied cleanly. Please check status if needed.")

    # Stage ALL modified, added, and deleted files (code, templates, KB articles, datasets)
    print("[*] Staging all repository changes (code, KB articles, data feeds)...")
    run_git_command(["add", "-A"])

    # Check if there are actually staged changes to commit
    staged_check = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
    if staged_check.returncode == 0:
        print("[+] No staged changes to commit. Working tree sync complete.")
        return

    print(f"[*] Committing changes with message: '{commit_message}'")
    run_git_command(["commit", "-m", f"{commit_message} [skip ci]"])

    print("[*] Pushing synchronised updates to remote origin...")
    run_git_command(["push", "origin", "main"])

    print("[+] GitHub repository synchronisation completed successfully.")

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Deploy Risk Protocols module, nav.js engine, and scanner updates"
    synchronise_repository(msg)