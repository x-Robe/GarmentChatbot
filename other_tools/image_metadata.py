import csv
from pathlib import Path

output_file = Path("../data/products.csv")
output_file.parent.mkdir(parents=True, exist_ok=True)

with output_file.open("w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["id", "image_path"])

    for image_id in range(1, 2001):
        writer.writerow([
            image_id,
            f"data/images/tshirt/{image_id}.jpg",
        ])

print(f"Created: {output_file.resolve()}")