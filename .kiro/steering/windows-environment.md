# Windows Environment Preferences

This project runs on Windows with PowerShell as the shell environment.

## Command Restrictions

- **Never use Unix-only commands** such as `tail`, `head`, `grep`, `cat`, `find`, `ls`, etc. as standalone shell commands — these do not work in PowerShell.
- Use PowerShell equivalents or the available IDE tools instead:
  - Instead of `tail -n 20 file.txt` → use `readFile` tool with `start_line`/`end_line` parameters
  - Instead of `grep pattern file` → use `grepSearch` tool
  - Instead of `ls` → use `listDirectory` tool
  - Instead of `cat file` → use `readFile` tool
- When running shell commands via `executePwsh`, always use PowerShell-compatible syntax.

## fsWrite Tool Requirements

- The `fsWrite` tool requires the `text` parameter to contain **non-empty content**.
- Empty strings (`""`) will fail with the error: "Either the text arg was not provided or text content provided exceeded the write file limit."
- When creating placeholder files (like `.gitkeep`), always include at least a comment or single character of content.
