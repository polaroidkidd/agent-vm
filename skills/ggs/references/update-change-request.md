# Update a Pull or Merge Request

Read [provider-routing.md](provider-routing.md) before reading or changing remote
review state.

## Address Feedback

1. Fetch the current change request metadata, review comments, unresolved threads, and
   check status through the selected provider interface.
2. Classify each item as actionable, a question, already addressed, or requiring user
   direction. Verify technically questionable feedback before changing code.
3. Implement only the requested fixes and run focused verification.
4. Stage paths explicitly and review the staged diff.
5. Prefer a new atomic commit after review has started so reviewers retain context.
   Amend only when explicitly requested or when no review context would be lost.
6. Push normally; after an authorized history rewrite, use `--force-with-lease`.

Reply to the specific thread with a concise explanation and commit identifier when the
provider supports threaded replies. Resolve a thread only after the issue is fixed,
the question is answered, or a suggestion is declined with a clear reason. Do not
resolve items that await information or reviewer confirmation.

If the connected interface can read comments but cannot reply or resolve threads,
report that limitation instead of using an unapproved fallback tool.

## Update Metadata

Re-read the project template before changing the title or description. Preserve its
structure and summarize the full change request, including later fixes. Keep a
ticket-derived prefix when repository policy uses one.

Change draft state, reviewers, assignees, labels, milestones, or target branch only
when supported and authorized. Before marking ready, verify local checks, remote
required checks, description completeness, and unresolved actionable feedback.
