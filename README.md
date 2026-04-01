# Veterinary Inventory Intake MVP

This project is a local MVP for receiving scanned shipment documents at a veterinary hospital. It watches an `Incoming` folder for new PDFs, moves them through a simple workflow, extracts structured draft data, and gives staff a lightweight review queue before manual entry into ezyVet.

Phase 1 intentionally stops at the review queue. There is no ezyVet integration yet.

## Architecture

The app uses a small, boring stack:

- `Flask` for the local web UI
- `SQLite` for persistence
- `watchdog` to monitor the `Incoming` folder
- A pluggable extraction provider interface
- A default `mock` extractor so the flow can be tested without OCR credentials

Current extraction behavior:

- If the PDF contains readable embedded text, the app will try to parse vendor, document metadata, and line items.
- If the PDF is image-only, the app now shows a clear warning instead of inventing fake line items.
- For image-only scans, the next real upgrade is adding an OCR provider or having the scanner export searchable PDFs.

Core runtime flow:

1. A PDF is saved into the configured `Incoming` folder.
2. The watcher detects the new file.
3. The processor waits until the file size stops changing.
4. A periodic folder sweep also checks `Incoming` for any PDFs that may have been added in bulk or missed by Windows file events.
5. The file is moved to `Processing`.
6. The configured extraction provider returns structured data.
7. The app stores raw extraction JSON plus normalized fields in SQLite.
8. The record appears in the review queue as `pending_review`.
9. Staff reviews the lines and sets a final status:
   - `ready_for_ezyvet_entry`
   - `needs_manager_review`
   - `incomplete`
10. After final review, the PDF is moved into `Reviewed`.
11. If processing fails, the PDF is moved into `Error`.

## Project Layout

```text
InventoryAutomation/
|-- app/
|   |-- __init__.py
|   |-- config.py
|   |-- models.py
|   |-- routes.py
|   |-- services/
|   |   |-- document_processor.py
|   |   |-- extraction.py
|   |   `-- watcher.py
|   |-- static/
|   |   `-- styles.css
|   `-- templates/
|       |-- base.html
|       |-- queue.html
|       `-- review.html
|-- scripts/
|   `-- create_sample_pdf.py
|-- storage/
|   |-- incoming/
|   |-- processing/
|   |-- reviewed/
|   `-- error/
|-- .env.example
|-- requirements.txt
|-- run.py
`-- README.md
```

## Configuration

Copy `.env.example` to `.env` and adjust values if needed.

Important variables:

- `DATABASE_PATH`: SQLite file location
- `WATCH_FOLDER`: folder the app monitors for incoming PDFs
- `PROCESSING_FOLDER`: working folder during extraction
- `REVIEWED_FOLDER`: destination after human review
- `ERROR_FOLDER`: destination for failures
- `EXTRACTION_PROVIDER`: current value is `mock`
- `WATCHER_ENABLED`: set to `false` if you only want the UI without background watching
- `FILE_STABILITY_CHECK_INTERVAL`: seconds between file size checks
- `FILE_STABILITY_REQUIRED_PASSES`: number of unchanged checks before processing starts
- `WATCH_FOLDER_SCAN_INTERVAL`: seconds between background sweeps of the incoming folder for missed or bulk-added PDFs

All relative paths are resolved from the project root, so the defaults work well for one local Windows machine.

## How To Run

1. Create and activate a virtual environment.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install dependencies.

```powershell
pip install -r requirements.txt
```

3. Create your `.env` file.

```powershell
Copy-Item .env.example .env
```

4. Start the app.

```powershell
python run.py
```

5. Open the UI in your browser:

```text
http://127.0.0.1:5000
```

## Developer Setup

For another developer to work on this project locally:

1. Clone the repository.
2. Open a terminal in the project folder.
3. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

4. Create a local environment file:

```powershell
Copy-Item .env.example .env
```

5. Start the app:

```powershell
python run.py
```

Notes for collaborators:

- `.env` is not committed, so each developer keeps local settings private.
- the SQLite database is local and not committed
- scanned PDFs in the workflow folders are not committed
- the `storage` subfolders are kept in git with `.gitkeep` files so the app starts cleanly after cloning

## How To Test With A Sample PDF

Option 1: Generate a sample invoice PDF directly into the `Incoming` folder.

```powershell
python scripts\create_sample_pdf.py
```

Option 2: Drop any `.pdf` into the folder configured by `WATCH_FOLDER`.

Default folder:

```text
storage\incoming
```

Once the file is detected:

- it will move into `storage\processing`
- a draft record will be created in SQLite
- the document will appear on the queue page as `pending_review`

Open the record, confirm the extracted lines, enter actual quantities, lot numbers, expiration dates, and discrepancy notes, then assign a final status.

## Review UI

The review page shows:

- PDF filename
- a link to open the stored PDF
- vendor
- document number
- date
- document type
- extracted line items
- confirmation checkbox for each line
- presence checkbox for each line
- actual quantity received
- batch / lot number
- expiration date
- discrepancy notes
- final record status

## Queue Page

The queue page lists all records and supports filtering by status.

Typical statuses:

- `pending_review`
- `ready_for_ezyvet_entry`
- `needs_manager_review`
- `incomplete`
- `error`

## Swapping In A Real Extraction API Later

The extraction layer is isolated behind the `ExtractionProvider` interface in `app/services/extraction.py`.

To connect a real provider later:

1. Add a new provider class implementing `extract(pdf_path: str) -> dict`.
2. Return the same normalized payload keys:
   - `vendor_name`
   - `document_type`
   - `document_number`
   - `document_date`
   - `line_items`
3. Register the provider in `provider_from_name`.
4. Set `EXTRACTION_PROVIDER` in `.env`.

The rest of the workflow does not need to change because the database and UI consume normalized fields plus the raw JSON payload.

## Notes

- This MVP is designed for local use on one Windows machine.
- It assumes the scanner software only saves PDFs into the watched folder.
- It does not perform OCR itself.
- The app now tries embedded PDF text first, then uses local Windows OCR for image-only scanned PDFs.
