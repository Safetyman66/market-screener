#!/usr/bin/env python3
"""
Corp Acuity // Resilient GitHub Synchronisation Engine
Automates conflict-free sync between local workspace and remote repository.
Favors local execution artifacts and code over stale remote workflow outputs.
Enforces UTF-8 stream decoding to prevent Windows charmap exceptions.
"""

import subprocess
import sys

def run_git(args, check=True):
    try:
        res = subprocess.run(
            ["git"] + args,
            check=check,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True
        )
        return res.stdout.strip(), res.returncode
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() if e.stderr else "Unknown Git error"
        print(f"[!] Warning: Git command 'git {' '.join(args)}' returned error:\n{err_msg}")
        if check:
            sys.exit(1)
        return err_msg, e.returncode

def sync_repository(commit_msg="Auto-sync market intelligence, code, and knowledge base"):
    print("[*] Initialising Resilient Git Sync...")

    # 1. Ensure local identity is configured
    run_git(["config", "--local", "user.name", "github-actions[bot]"], check=False)
    run_git(["config", "--local", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)

    # 2. Stage all current local work (code, templates, feeds)
    print("[*] Staging all local assets and scanner data...")
    run_git(["add", "-A"])

    # 3. Commit locally first so your work is never lost or tangled in stash
    has_changes = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0
    if has_changes:
        print(f"[*] Committing local updates: '{commit_msg}'")
        run_git(["commit", "-m", f"{commit_msg} [skip ci]"])
    else:
        print("[+] Working tree is already clean. Proceeding to fetch...")

    # 4. Fetch the remote tracking branch
    print("[*] Fetching updates from remote origin...")
    run_git(["fetch", "origin", "main"])

    # 5. Pull & Merge with automated local conflict preference (-X ours)
    # If GitHub Actions wrote a new terminal_feed.json, your local version will silently win.
    print("[*] Merging remote branch (favoring local artifacts on any conflict)...")
    merge_out, code = run_git(["merge", "origin/main", "-X", "ours", "--no-edit"], check=False)

    if code != 0:
        print("[!] Merge encountered unmerged binary assets. Forcing local resolution...")
        run_git(["checkout", "--ours", "."], check=False)
        run_git(["add", "-A"])
        run_git(["commit", "-m", "Auto-resolve merge artifacts favoring local workspace [skip ci]"], check=False)

    # 6. Push cleanly to main
    print("[*] Pushing fully reconciled state to origin/main...")
    push_out, push_code = run_git(["push", "origin", "main"], check=False)
    
    if push_code != 0:
        print("[!] Standard push rejected. Retrying with safe fast-forward re-sync...")
        run_git(["pull", "--rebase", "-X", "theirs", "origin", "main"], check=False)
        run_git(["push", "origin", "main"])

    print("[+] Sync complete! All local code, KB articles, and live feeds are live on GitHub.")

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Auto-sync market intelligence, code, and knowledge base"
    sync_repository(msg)