#!/bin/bash
set -e

MAX_ITERATIONS=${1:-20}
COMPLETION_PROMISE=${2:-<promise>COMPLETE</promise>}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🚀 gralph loop starting"
echo "   Project: $PROJECT_ROOT"
echo "   Max iterations: $MAX_ITERATIONS"

cd "$PROJECT_ROOT"

for ((i=1; i<=$MAX_ITERATIONS; i++)); do
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "  Iteration $i / $MAX_ITERATIONS"
    echo "════════════════════════════════════════════════════════════"

    PROMPT="@gralph/PRD.md @gralph/progress.txt @gralph/PROMPT.md
1. Find the highest-priority unchecked task (- [ ]) and implement it.
2. Run the verification command for that task.
3. If verification passes, mark the task done: change '- [ ]' to '- [x]' in PRD.md.
4. Append what you learned to progress.txt.
5. Commit your changes with a descriptive message.
ONLY WORK ON A SINGLE TASK PER ITERATION.
If all tasks are complete (no more '- [ ]'), output: $COMPLETION_PROMISE"

    result=$(claude --dangerously-skip-permissions --print "$PROMPT" 2>&1) || true

    echo "$result"

    if [[ "$result" == *"$COMPLETION_PROMISE"* ]]; then
        echo ""
        echo "✅ PRD complete after $i iterations!"
        exit 0
    fi
done

echo ""
echo "⚠️  Reached max iterations ($MAX_ITERATIONS). Some tasks may be incomplete."
echo "Review gralph/PRD.md and run 'gralph run' again if needed."
