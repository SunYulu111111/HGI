"""One-off checkpoint free-freq report for index=0, GENERAL_1."""

from simulation import simulation

CHECKPOINTS = (10000, 50000, 100000, 1000000)

rows = simulation(
    spin_times=1_000_000,
    index=0,
    general_index=1,
    choose_index=1,
    report_interval=10_000,
    print_updates=False,
)

print("INDEX=0, GENERAL_1, choose_index=1")
print(f"{'SPIN':>10}  {'触发Free':>10}  {'Free频率':>12}")
for row in rows:
    if row["SPIN"] in CHECKPOINTS:
        freq_pct = row["Free频率"] * 100
        print(f"{row['SPIN']:>10}  {row['触发Free']:>10}  {freq_pct:>11.4f}%")
