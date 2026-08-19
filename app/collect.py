from app.pipeline import run_collection

if __name__ == "__main__":
    reports = run_collection()
    for row in reports:
        print(f"{row['marketplace']}: {row['status']} fetched={row['fetched']} kept={row['kept']} error={row.get('error')}")
