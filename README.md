# Scheduled automation runner

Private source and operational data are stored separately.

Queue selection creates separate jobs for Telegram checks, approved review replies,
and deferred stock verification. Matrix fail-fast is disabled: a failed worker keeps
its failed status without cancelling the other workers. Each worker has a separate
process and diagnostic record. A failed queue lookup launches only that worker for
its own error reporting and does not hide work in the other queues.

Daily stock writes and deferred stock writes share `bot-stock-and-commands` for
compatibility with previous stock runs. Read-only Telegram checks use their own
group. Advertising and finance share their economics writer group. Other tasks
have their own groups. Running jobs are not cancelled and pending jobs are queued.

Stock validation runs stock, stock-limit and sales-cache tests. Advertising runs
its own validation; the manual full-source probe still checks all tests.

Run the offline failure-injection checks with:

```sh
python -m unittest test_runner_isolation.py
```
