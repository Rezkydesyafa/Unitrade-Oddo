import json, subprocess, sys, time

REPO = sys.argv[1] if len(sys.argv) > 1 else "Rezkydesyafa/Unitrade-Oddo"

with open("github_issues.json", "r", encoding="utf-8") as f:
    issues = json.load(f)

print(f"Total issues: {len(issues)}")
print(f"Repo: {REPO}")
print()

ok = 0
fail = 0

for i, issue in enumerate(issues, 1):
    labels = ",".join(issue["labels"])
    cmd = [
        "gh", "issue", "create",
        "--repo", REPO,
        "--title", issue["title"],
        "--body", issue["body"],
        "--label", labels,
        "--milestone", issue["milestone"],
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        url = result.stdout.strip()
        print(f"[{i:02d}/45] OK  {issue['title'][:55]}...")
        ok += 1
    else:
        print(f"[{i:02d}/45] ERR {issue['title'][:55]}")
        print(f"       {result.stderr.strip()[:80]}")
        fail += 1
    time.sleep(0.4)

print()
print(f"Selesai! Berhasil: {ok} | Gagal: {fail}")
