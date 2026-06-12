import csv
import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("outputs/submission_c4_v7.csv", encoding="utf-8") as f:
    v7 = list(csv.DictReader(f))
with open("teamate_hightst_submission.csv", encoding="utf-8-sig") as f:
    tm = list(csv.DictReader(f))
with open("train.csv", encoding="utf-8") as f:
    train = list(csv.DictReader(f))

tm_desc_set = set(r["description"] for r in tm if r["repo_path"] != "empty")
augmented = [r for r in v7 if r["repo_path"] != "empty" and r["description"] not in tm_desc_set]

BT = chr(96)  # backtick

print(f"Augmented rows: {len(augmented)}")
print(f"Train rows total: {len(train)}")
print(f"Teammate rows total: {sum(1 for r in tm if r['repo_path'] != 'empty')}")

# Check backtick usage
n_train_bt = sum(1 for r in train if BT in r.get("description", ""))
n_tm_bt = sum(1 for r in tm if BT in r.get("description", ""))
n_aug_bt = sum(1 for r in augmented if BT in r["description"])
print(f"\nBacktick usage:")
print(f"  train.csv: {n_train_bt}/{len(train)}")
print(f"  teammate: {n_tm_bt}/{len(tm)}")
print(f"  augmented: {n_aug_bt}/{len(augmented)}")

# Print augmented rows containing backticks
print("\nAugmented rows containing backticks:")
for i, r in enumerate(augmented):
    if BT in r["description"]:
        print(f"  #{i+1} {r['repo_path']}: {r['description'][:170]}")
