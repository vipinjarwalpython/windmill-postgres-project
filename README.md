# Windmill Orders ETL Automation Project

This is a complete beginner-friendly ETL automation project using GitHub Actions, Windmill Workflow, Python, PostgreSQL, pandas, and SMTP email.

The pipeline extracts ecommerce orders from PostgreSQL, transforms them with pandas, generates a CSV report, stores analytics-ready data back into PostgreSQL, emails the CSV report, and uses GitHub Actions to trigger the Windmill workflow automatically on every push to `main`.

## Architecture

```text
Developer pushes code to main
            |
            v
GitHub Actions workflow
            |
            v
Windmill workflow API
            |
            v
orders_etl_pipeline
            |
            +--> 1. extract_orders.py
            |       Reads orders from PostgreSQL
            |
            +--> 2. transform_orders.py
            |       Adds GST and final amount using pandas
            |
            +--> 3. save_csv.py
            |       Creates /tmp/orders_report.csv
            |
            +--> 4. store_analytics.py
            |       Inserts transformed rows into analytics_orders
            |
            +--> 5. send_email.py
                    Sends CSV report using SMTP
```

## Project Structure

```text
project/
|
+-- .github/
|   +-- workflows/
|       +-- deploy.yml
|
+-- sql/
|   +-- init.sql
|
+-- README.md
|
+-- windmill/
    +-- scripts/
        +-- extract_orders.py
        +-- transform_orders.py
        +-- save_csv.py
        +-- store_analytics.py
        +-- send_email.py
```

## What The Pipeline Does

1. Reads ecommerce orders from the `orders` table.
2. Calculates `order_amount`, `gst_amount`, and `final_amount`.
3. Creates a CSV report at `/tmp/orders_report.csv`.
4. Loads transformed data into `analytics_orders`.
5. Sends the report by email as a CSV attachment.
6. Runs automatically from GitHub Actions when code is pushed to `main`.

## Requirements

- PostgreSQL database
- Windmill workspace
- GitHub repository
- SMTP email account
- Python packages in Windmill:
  - `pandas`
  - `psycopg2-binary`

## PostgreSQL Setup

Create a PostgreSQL database. Example:

```bash
createdb ecommerce_etl
```

Run the SQL file:

```bash
psql -d ecommerce_etl -f sql/init.sql
```

The SQL file creates:

- `orders`: source ecommerce orders
- `analytics_orders`: transformed analytics table

It also inserts realistic sample ecommerce order records.

Example database URL:

```text
postgresql://postgres:your_password@localhost:5432/ecommerce_etl
```

For a hosted database, replace host, port, username, password, and database name with your provider details.

## Windmill Setup

### 1. Create Windmill Variables

In Windmill, create these variables or secrets:

```text
DATABASE_URL=postgresql://postgres:your_password@your_host:5432/ecommerce_etl
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=receiver@example.com
```

For Gmail, use an app password instead of your normal Gmail password.

### 2. Create Windmill Scripts

In Windmill, create five Python scripts under your preferred path, for example under `u/admin/`.

Create each script and paste the matching file content:

```text
u/admin/extract_orders       -> windmill/scripts/extract_orders.py
u/admin/transform_orders     -> windmill/scripts/transform_orders.py
u/admin/save_csv             -> windmill/scripts/save_csv.py
u/admin/store_analytics      -> windmill/scripts/store_analytics.py
u/admin/send_email           -> windmill/scripts/send_email.py
```

Make sure each script uses Python 3 and has these dependencies available:

```text
pandas
psycopg2-binary
```

### 3. Create Windmill Workflow

Create a workflow named:

```text
orders_etl_pipeline
```

Use these workflow steps in this exact order:

```text
1. extract_orders
2. transform_orders
3. save_csv
4. store_analytics
5. send_email
```

### 4. Exact Step Input Mappings

Use these input mappings in Windmill:

```text
Step 1: extract_orders
Inputs:
No inputs
```

```text
Step 2: transform_orders
Inputs:
extract_result = results.extract_orders
```

```text
Step 3: save_csv
Inputs:
transform_result = results.transform_orders
```

```text
Step 4: store_analytics
Inputs:
transform_result = results.transform_orders
```

```text
Step 5: send_email
Inputs:
transform_result = results.transform_orders
save_csv_result = results.save_csv
```

If your Windmill UI uses step IDs instead of script names, set the IDs to:

```text
extract_orders
transform_orders
save_csv
store_analytics
send_email
```

That keeps the mappings easy to read.

## GitHub Actions Setup

The file `.github/workflows/deploy.yml` runs on every push to `main`.

Add these GitHub repository secrets:

```text
WINDMILL_TOKEN
WINDMILL_WORKSPACE
WINDMILL_BASE_URL
```

Example values:

```text
WINDMILL_TOKEN=your_windmill_api_token
WINDMILL_WORKSPACE=your_workspace_id
WINDMILL_BASE_URL=https://app.windmill.dev
```

The GitHub Action calls this Windmill API endpoint:

```text
${WM_BASE_URL}/api/w/${WM_WS}/jobs/run/f/u/admin/orders_etl_pipeline
```

The action fails if:

- Any required secret is missing
- The Windmill API returns a non-2xx response
- The response does not look like a Windmill job response

## Running The Project

### Run manually from Windmill

1. Open the `orders_etl_pipeline` workflow.
2. Click Run.
3. Confirm each step succeeds.
4. Check the email inbox configured in `EMAIL_TO`.
5. Check the `analytics_orders` table.

Verify analytics data:

```sql
SELECT *
FROM analytics_orders
ORDER BY analytics_id;
```

### Run automatically from GitHub

Commit and push to the `main` branch:

```bash
git add .
git commit -m "Add orders ETL automation project"
git push origin main
```

GitHub Actions will call Windmill, and Windmill will run the ETL workflow.

## Example Outputs

Example transformed fields:

```text
quantity = 2
unit_price = 799.00
order_amount = 1598.00
gst_amount = 287.64
final_amount = 1885.64
```

Example summary:

```json
{
  "total_orders": 10,
  "total_quantity": 17,
  "total_order_amount": 33083.0,
  "total_gst_amount": 5954.94,
  "total_final_amount": 39037.94,
  "top_category": "Electronics"
}
```

Example email body:

```text
The orders ETL pipeline completed successfully.

Summary:
- Orders processed: 10
- CSV rows generated: 10
- Total quantity sold: 17
- Total order amount: 33083.0
- Total GST amount: 5954.94
- Total final amount: 39037.94
- Top category by revenue: Electronics
```

## Common Errors And Fixes

### `DATABASE_URL is missing`

Fix: Add `DATABASE_URL` as a Windmill variable or secret.

### `psycopg2 module not found`

Fix: Add `psycopg2-binary` as a dependency in the Windmill script settings.

### `pandas module not found`

Fix: Add `pandas` as a dependency in the Windmill script settings.

### `connection refused`

Fix: Confirm the PostgreSQL host, port, username, password, and database name are correct. If PostgreSQL is on your laptop, hosted Windmill cannot reach `localhost`; use a hosted database or network-accessible database.

### `authentication failed`

Fix: Check the PostgreSQL username and password in `DATABASE_URL`.

### `SMTP authentication failed`

Fix: For Gmail, enable two-factor authentication and create an app password. Use the app password as `SMTP_PASSWORD`.

### `Windmill workflow trigger failed`

Fix: Check that these GitHub secrets are correct:

```text
WINDMILL_TOKEN
WINDMILL_WORKSPACE
WINDMILL_BASE_URL
```

Also confirm the workflow path exists:

```text
u/admin/orders_etl_pipeline
```

### CSV file not found

Fix: Make sure `save_csv` runs before `send_email`, and use this mapping:

```text
save_csv_result = results.save_csv
```

## Notes For Beginners

- ETL means Extract, Transform, Load.
- PostgreSQL stores the source and analytics data.
- pandas is used for calculations.
- Windmill runs the Python scripts as workflow steps.
- SMTP sends the email report.
- GitHub Actions starts the Windmill workflow automatically after a push.
