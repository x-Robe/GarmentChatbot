import csv
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
CSV_FILE = BASE_DIR / "data/products.csv"
JSON_FILE = BASE_DIR / "data/products.json"


def convert_csv_to_json() -> None:
    if not CSV_FILE.exists():
        raise FileNotFoundError(
            f"CSV file was not found: {CSV_FILE}"
        )

    products = []

    with CSV_FILE.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        required_columns = {"id", "image_path"}
        actual_columns = set(reader.fieldnames or [])

        missing_columns = required_columns - actual_columns

        if missing_columns:
            raise ValueError(
                "Missing required CSV columns: "
                + ", ".join(sorted(missing_columns))
            )

        for row_number, row in enumerate(reader, start=2):
            product_id = row["id"].strip()
            image_path = row["image_path"].strip()

            if not product_id:
                print(f"Skipping row {row_number}: missing id")
                continue

            if not image_path:
                print(
                    f"Skipping row {row_number}: "
                    "missing image_path"
                )
                continue

            try:
                product_id = int(product_id)
            except ValueError:
                print(
                    f"Skipping row {row_number}: "
                    f"invalid id '{product_id}'"
                )
                continue

            products.append(
                {
                    "id": product_id,
                    "image_path": image_path,
                }
            )

    with JSON_FILE.open(
        mode="w",
        encoding="utf-8",
    ) as json_file:
        json.dump(
            products,
            json_file,
            indent=2,
            ensure_ascii=False,
        )

    print(f"Created: {JSON_FILE}")
    print(f"Total products: {len(products)}")


if __name__ == "__main__":
    convert_csv_to_json()