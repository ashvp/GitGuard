# GitGuard: Natural Language Git with Built-In Safety
<p align="center">
  <img src="https://img.shields.io/pypi/v/gitguard-cli" />
  <img src="https://img.shields.io/pypi/pyversions/gitguard-cli" />
  <img src="https://img.shields.io/pypi/l/gitguard-cli" />
  <img src="https://img.shields.io/pypi/dm/gitguard-cli" />
</p>


> **Version control systems are unforgiving. GitGuard bridges the gap between powerful functionality and developer safety. GitGuard lets you describe Git actions in plain English and safely converts them into real Git commands with explanations and automatic rollback checkpoints.**

GitGuard is an AI-powered CLI tool designed to interpret your intent, evaluate risk, and provide automatic recovery checkpoints before risky Git operations are executed. It acts as a dedicated safety and reasoning layer for your version control workflow.

![GitGuard Demo](https://placehold.co/800x400/1e1e1e/3b82f6?text=GitGuard+CLI+Demo)

## 🛡️ Why GitGuard?

Git is powerful but dangerous. Operations like `reset`, `rebase`, and `force push` can permanently delete work. GitGuard is an AI copilot that:
1.  **Interprets Intent:** Describe what you want in plain English.
2.  **Evaluates Risk:** Automatically flags operations as Safe, Medium, or High risk.
3.  **Enables Recovery:** Creates automatic checkpoints (and stashes local work) before operations.
4.  **Teaches Git:** Explains what each command does so you learn while you work.

## 🤔 Why Not Git Aliases?

Git aliases automate commands.
GitGuard reasons about intent, evaluates risk, and prepares recovery checkpoints.

Git aliases blindly expand commands.
GitGuard evaluates intent, explains impact, creates a recovery point, then asks for confirmation.

## 🚀 Installation

### 1. Install (recommended via pipx)
```
pipx install gitguard-cli
```
# or
```
pip install gitguard-cli
```

### 2. Set your API Key
GitGuard requires a Google Gemini API Key. [Get one for free here](https://aistudio.google.com/).

**Windows (PowerShell):**
```powershell
$env:GEMINI_API_KEY="your_api_key_here"
```

**Linux / macOS:**
```bash
export GEMINI_API_KEY="your_api_key_here"
```

## ✨ Features

### 🧠 Natural Language Git (`run`)
Describe your intent, and GitGuard will generate a safe plan.
```bash
gitguard run "undo my last commit but keep the files"
```

### ⏪ Zero-Risk Rollback (`rollback`)
Made a mistake? Revert your repository AND your uncommitted local changes instantly.
```bash
gitguard rollback
```

### 📝 AI Commit Messages (`commit`)
Automatically generate semantic, high-quality commit messages from your staged changes.
```bash
gitguard commit
```

### 🧐 AI Code Auditor (`audit`)
Scan your staged code for hardcoded secrets, API keys, and common bugs before you commit.
```bash
gitguard audit
```

### 🗣️ Explain My Work (`explain`)
Generates a plain-English summary of your changes—perfect for PR descriptions or standups.
```bash
gitguard explain
```

### 🧠 Learn Mode (`learn`)
Don't just run commands, understand them.
```bash
gitguard learn "git rebase -i HEAD~3"
```

## 💻 Usage Example

```text
> gitguard run "push my changes"

[Interpreted Action]
• This will push your local 'main' branch to the remote 'origin'.
• Risk Level: MEDIUM

💡 Learning Note:
Pushing sends your local commits to a central server so others can see them.

Planned Commands:
  1. git push origin main

Proceed with this plan? [y/N]: y
✓ Checkpoint created: gitguard-backup-20251230_1400
Executing: git push origin main
✓ Done
Success! Operation completed safely.
```

## 🔐 Privacy & Security

- GitGuard does not upload your repository.
- Only high-level intent and minimal command context are sent to the AI API.
- No code is stored or logged by GitGuard.

## ⚠️ Limitations & Notes

- GitGuard does not replace Git expertise; it adds a safety layer.
- All commands require user confirmation before execution.
- AI interpretation may occasionally need clarification for complex workflows.
- Currently tested primarily on Git repositories using standard workflows.

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---
**Built with ❤️ by ashvp for safer engineering.**
---