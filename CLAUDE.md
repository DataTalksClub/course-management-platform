@AGENTS.md

## CRITICAL: File Editing on Windows

### ⚠️ MANDATORY: Always Use Backslashes on Windows for File Paths

When using Edit or MultiEdit tools on Windows, you MUST use backslashes (`\`) in file paths, NOT forward slashes (`/`).

❌ WRONG - Will cause errors:
```
Edit(file_path: "D:/repos/project/file.tsx", ...)
MultiEdit(file_path: "D:/repos/project/file.tsx", ...)
```

✅ CORRECT - Always works:
```
Edit(file_path: "D:\repos\project\file.tsx", ...)
MultiEdit(file_path: "D:\repos\project\file.tsx", ...)
```

### ⚠️ "File has been unexpectedly modified" Error

If you get this error: **"File has been unexpectedly modified. Read it again before attempting to write it"**

**Root cause:** The file was modified after you last read it (by linter, formatter, git, or external process).

**Solution: Re-read the file immediately before editing:**

```bash
# 1. Read the file again
Read(file_path: "path\to\file.txt")

# 2. Then immediately edit
Edit(file_path: "path\to\file.txt", old_string="...", new_string="...")
```

**Tool requirements:**

| Tool | Rule |
|------|------|
| **Edit** | Must `Read` immediately before - `old_string` must match current content |
| **Write** | Must `Read` once per conversation before first write |

**Common triggers:**
- Linters/formatters running on save
- Git operations (checkout, merge, rebase)
- File watchers or build processes

**Tip:** If this happens repeatedly, consider disabling auto-formatting for files you're actively editing with Claude Code.

