from __future__ import annotations

import csv # For CSV writing operations
import re # Regular expressions for pattern matching
from pathlib import Path # Object-oriented file system paths
from typing import Dict, List, Tuple # Type hinting for better code clarity

import pandas as pd # for efficient data manipulation and CSV generation

"""
Defines a constant list of expected column headers for "ESTIMATE" table blocks. 
This list ensures consistent parsing when the estimate table has a specific structure 
that might not be clearly labeled in the source files.
"""
ESTIMATE_COLUMNS: List[str] = [
    "ARCH",
    "CONTEXT SIZE",
    "BATCH SIZE (L / P)",
    "FLASH ATTENTION",
    "MMAP LOAD",
    "EMBEDDING ONLY",
    "RERANKING",
    "DISTRIBUTABLE",
    "OFFLOAD LAYERS",
    "FULL OFFLOADED",
    "RAM LAYERS (I + T + O)",
    "RAM UMA",
    "RAM NONUMA",
    "VRAM0 LAYERS (T + O)",
    "VRAM0 UMA",
    "VRAM0 NONUMA",
]


def split_blocks(text: str) -> List[List[str]]:
    """Break the ASCII table output into logical blocks separated by blank lines."""

    # Initialize storage for completed blocks and the current block being built
    blocks: List[List[str]] = []
    current: List[str] = []

    # Process the text line by line
    for line in text.splitlines():
        # Check if we've hit a blank line (block separator)
        if line.strip() == "":
            # If we have accumulated lines, save them as a complete block
            if current:
                blocks.append(current)
                current = [] # Reset for the next block
        else:
            # Non-blank line: add it to current block, removing trailing newlines
            current.append(line.rstrip("\n"))

    # Don't forget the last block if the file doesn't end with a blank line
    if current:
        blocks.append(current)
    return blocks


def parse_block(block: List[str]) -> Tuple[str | None, Dict[str, str]]:
    """Convert a single table block into a mapping of column -> value.
    Assumes a label row followed by header rows and a final data row."""
    
    # Extract only lines that look like table rows (start with pipe character)
    rows = [line for line in block if line.startswith("|")]

    # If no table structure found, return empty results
    if not rows:
        return None, {}

    # Parse each row: remove outer pipes, split on inner pipes, strip whitespace
    # This converts "| Cell1 | Cell2 |" into ["Cell1", "Cell2"]
    parsed = [[cell.strip() for cell in row.strip("|").split("|")] for row in rows]

    # First cell of first row is the table label (e.g., "METADATA", "ESTIMATE")
    label = parsed[0][0].upper()

    # Skip the label row and filter out any malformed rows (single cell or empty)
    table_rows = [r for r in parsed[1:] if len(r) > 1]

    # If only a label exists with no actual table data, return early
    if not table_rows:
        return label, {}

    # The last row contains the actual data values
    data_row = table_rows[-1]

    # For ESTIMATE tables, use predefined columns (headers might be malformed)
    # For other tables, use the first data row as column headers
    if label == "ESTIMATE":
        columns = ESTIMATE_COLUMNS
    else:
        columns = table_rows[0]

    # Normalize column names: collapse multiple spaces into single spaces
    # Handles headers like "CONTEXT    SIZE" -> "CONTEXT SIZE"
    columns = [" ".join(col.split()) for col in columns]

    # Handle column/data mismatches to prevent data loss:
    # If more data cells than headers: generate placeholder names (EXTRA_0, EXTRA_1, ...)
    if len(columns) < len(data_row):
        columns = columns + [f"EXTRA_{i}" for i in range(len(columns), len(data_row))]

    # If more headers than data: truncate excess headers
    elif len(columns) > len(data_row):
        columns = columns[: len(data_row)]

    # Pair each column name with its corresponding data value
    values = dict(zip(columns, data_row))
    return label, values


def parse_file(path: Path) -> Dict[str, str] | None:
    """Parse a single txt file into a flat record with prefixed column names."""

    # Read entire file content, ignoring any encoding errors
    # Because any data is better than nothing
    text = path.read_text(errors="ignore")

    # Skip completely empty files
    if not text.strip():
        return None

    # Initialize record with the filename as an identifier
    record: Dict[str, str] = {"file": path.name}

    # Process each logical block (table) in the file
    for block in split_blocks(text):
        # Extract table label and column-value pairs
        label, values = parse_block(block)

        # Skip blocks that couldn't be parsed successfully
        if not label or not values:
            continue

        # Add each value to the record with a prefixed key
        # This prevents collisions: METADATA_TYPE vs ESTIMATE_TYPE are different columns
        for col, val in values.items():
            key = f"{label}_{col}"
            record[key] = val
    return record


def parse_parameters(value: str | float | int | None) -> float | None:
    """
    Convert strings like '22.57 M' or '1.78 B' into a raw parameter count.

    Model size categories follow Table 1 of 3733702.pdf:
    - Small: <1B parameters
    - Medium: 1B–10B
    - Large: 10B–100B
    - Ultra-Large: >=100B
    """

    # Handle None or missing values gracefully
    if value is None:
        return None

    # Convert to string and remove leading/trailing whitespace
    text = str(value).strip()

    # Empty strings can't be parsed
    if not text:
        return None

    # Regex pattern matches: "22.57 M" or "1.78B" or "500 K"
    # Group 1: The numeric part (integer or decimal)
    # Group 2: The unit letter (K/M/B, case-insensitive)
    match = re.match(r"([0-9]+(?:\.[0-9]+)?)\s*([KMBkmb])", text)

    # If format doesn't match, we can't parse it
    if not match:
        return None

    # Extract the numeric amount and convert to float
    amount = float(match.group(1))

    # Extract unit and normalize to uppercase
    unit = match.group(2).upper()

    # Map unit letters to their multipliers
    multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(unit)

    # If somehow an invalid unit got through the regex (shouldn't happen), return None
    if multiplier is None:
        return None
    
    # Calculate and return raw parameter count
    return amount * multiplier


def size_category(params: float | None) -> str:

    if params is None:
        return "Unknown"
    
    # Small models: fewer than 1 billion parameters
    if params < 1_000_000_000:
        return "Small (<1B)"
    
    # Medium models: 1 billion to 10 billion parameters
    if params < 10_000_000_000:
        return "Medium (1-10B)"
    
    # Large models: 10 billion to 100 billion parameters
    if params < 100_000_000_000:
        return "Large (10-100B)"
    
    # Ultra-large models: 100 billion or more parameters
    return "Ultra-Large (100B+)"


def main() -> None:
    # Set working directory to current directory
    root = Path(".")

    # Storage for all parsed records (one per file)
    records: List[Dict[str, str]] = []

    # Track column order as we discover new columns
    # Start with 'file' as the first column (identifier)
    column_order: List[str] = ["file"]
    
    # Process all .txt files in sorted order (alphabetical by filename)
    for txt_path in sorted(root.glob("*.txt")):
        # Parse this file into a flat dictionary
        record = parse_file(txt_path)

        # Skip files that couldn't be parsed or were empty
        if not record:
            print(f"Skipping {txt_path.name}: no readable data found.")
            continue

        # Track any new columns we haven't seen before
        # This preserves order of first appearance across all files
        for key in record:
            if key not in column_order:
                column_order.append(key)

        # Add this file's record to our collection
        records.append(record)

    # If no files were successfully parsed, nothing to do
    if not records:
        print("No data to write.")
        return

    # Convert list of dictionaries into a pandas DataFrame for easier manipulation
    df = pd.DataFrame(records)

    # Compute raw parameter counts from the METADATA_PARAMETERS column
    # apply() runs parse_parameters() on each cell value
    params_raw = df["METADATA_PARAMETERS"].apply(parse_parameters)

    # Create a new column with size categories
    df["MODEL_SIZE_CATEGORY"] = params_raw.apply(size_category)

    # Insert the derived column next to its source column for logical grouping
    # Find where METADATA_PARAMETERS appears in our column order
    if "METADATA_PARAMETERS" in column_order:
        insert_at = column_order.index("METADATA_PARAMETERS") + 1

    # Fallback: add at the end if METADATA_PARAMETERS doesn't exist
    else:
        insert_at = len(column_order)

    # Insert MODEL_SIZE_CATEGORY at the calculated position
    for col in ["MODEL_SIZE_CATEGORY"]:
        if col not in column_order:
            column_order.insert(insert_at, col)
            insert_at += 1 # If adding multiple columns, keep them contiguous

    # Define sort order for size categories
    bucket_order = {
        "Small (<1B)": 0,
        "Medium (1-10B)": 1,
        "Large (10-100B)": 2,
        "Ultra-Large (100B+)": 3,
        "Unknown": 4, # Put unparseable models at the end
    }

    # Create temporary columns for sorting purposes
    # Map each category to its numeric order
    df["_bucket_order"] = df["MODEL_SIZE_CATEGORY"].map(bucket_order).fillna(4)

    # Store raw parameter counts for secondary sort
    df["_params_sort"] = params_raw

    # Sort by category first, then by exact parameter count within category
    # This creates natural groupings: all Small models together, sorted 7B→8B→9B
    df = df.sort_values(
        by=["_bucket_order", "_params_sort"],
        ascending=[True, True],
    ).drop(columns=["_bucket_order", "_params_sort"]) # Remove temporary columns

    # Reorder DataFrame columns to match our tracked order
    # (By default, DataFrame columns appear in arbitrary order)
    df = df.reindex(columns=column_order)

    # Define output path
    output_path = root / "models.csv"

    try:
        # Write DataFrame to CSV with specific formatting:
        df.to_csv(
            output_path,
            index=False,            # Don't write row numbers as a column
            sep=";",
            quoting=csv.QUOTE_ALL,  # Quote all fields (handles semicolons in data)
            encoding="utf-8-sig",   # UTF-8 with BOM (makes Excel recognize UTF-8)
        )
        print(f"Wrote {len(df)} rows to {output_path}")
    except PermissionError:
        # Handle case where models.csv is open in Excel (file locked on Windows)
        fallback_path = root / "models.csv"
        df.to_csv(
            fallback_path,
            index=False,
            sep=";",
            quoting=csv.QUOTE_ALL,
            encoding="utf-8-sig",
        )
        print(
            f"models.csv is locked (likely open). Wrote {len(df)} rows to {fallback_path} instead."
        )


if __name__ == "__main__":
    main()
