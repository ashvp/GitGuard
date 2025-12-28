# GitGuard: The AI-Assisted Safety Copilot

> **Version control systems are unforgiving. GitGuard bridges the gap between powerful functionality and developer safety.**

GitGuard is an AI-powered CLI tool designed to interpret your intent, evaluate risk, and guarantee a safe rollback mechanism before any Git command is executed. It acts as a dedicated safety and reasoning layer for your version control workflow.

![GitGuard Demo](https://placehold.co/800x400/1e1e1e/3b82f6?text=GitGuard+CLI+Demo)

## 🚀 The Problem

Git is powerful but dangerous. Operations like `reset`, `rebase`, and `force push` can permanently delete work, creating a culture of fear among junior developers and resulting in:
*   Fear of advanced features.
*   Messy, unorganized commit histories.
*   Dependency on senior leads for simple fixes.
*   Real productivity costs due to "Git avoidance."

## 🛡️ Our Solution

**GitGuard** is an AI copilot that:
1.  **Interprets Intent:** You describe what you want in plain English.
2.  **Evaluates Risk:** Automatically flags operations as Safe, Medium, or High risk.
3.  **Guarantees Recovery:** Creates automatic checkpoints before *every* command.
4.  **Enforces Safety:** Requires explicit confirmation for destructive actions.

## ✨ Key Features

*   **🧠 NLP Interpretation:** "Undo my last commit but keep changes" -> `git reset --soft HEAD~1`
*   **🚦 Risk Classification:** Know before you go. Is this safe, or will it rewrite history?
*   **💾 Automatic Checkpoints:** Every operation is backed up locally.
*   **⏪ One-Command Undo:** Made a mistake? `gitguard rollback` takes you back instantly.
*   **🔒 Privacy First:** Your code stays local. Only abstract intent strings are sent to the AI.

## 📦 Installation

### Prerequisites
*   Python 3.9+
*   A Google Gemini API Key (Get one [here](https://aistudio.google.com/))

### Install via pip / uv

```bash
# Clone the repository
git clone https://github.com/yourusername/gitguard-cli.git
cd gitguard-cli

# Install dependencies (using uv is recommended)
uv sync

# Install the package in editable mode
uv pip install -e .
```

### Configuration

Create a `.env` file in the project root or set the environment variable:

```bash
GEMINI_API_KEY="your_api_key_here"
```

## 💻 Usage

### 1. Run a Command
Describe what you want to do. GitGuard will analyze it and propose a plan.

```bash
gitguard run "delete the feature-login branch"
```

**Output:**
```text
GitGuard interpreting intent: "delete the feature-login branch"

[Proposed Execution Plan]
• Summary: Delete the local branch named 'feature-login'
• Risk Level: HIGH
• Planned Commands:
  $ git branch -d feature-login

Proceed with this plan? [y/N]: y
✓ Safety checkpoint created: gitguard-backup-20231027_103000
Running: git branch -d feature-login
✓ Done
Success! Operation completed safely.
Undo anytime with: gitguard rollback
```

### 2. Rollback
If anything goes wrong, revert to the state before the last GitGuard operation.

```bash
gitguard rollback
```

## 🏗️ Architecture

*   **CLI Interface (Typer/Rich):** Handles user interaction and local execution.
*   **Intent Engine (Gemini 1.5 Flash):** Translates natural language into structured Git plans using **Structured Outputs**.
*   **Safety Layer:** Manages local checkpoints (custom branches) and enforces confirmation.

## 🤝 Contributing

We welcome contributions! Please see `CONTRIBUTING.md` for details.

1.  Fork the repo
2.  Create your feature branch (`git checkout -b feature/amazing-feature`)
3.  Commit your changes (`git commit -m 'Add some amazing feature'`)
4.  Push to the branch (`git push origin feature/amazing-feature`)
5.  Open a Pull Request

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---
**Team Innovaide** | built with ❤️ for safer engineering.
