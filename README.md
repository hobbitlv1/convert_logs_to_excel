# Log Parser to Excel Converter

Python utility for parsing ASCII table-formatted model specification logs and converting them to structured CSV output. Automatically categorizes models by parameter size and sorts data for analysis.

## Features

- Parses multiple ASCII tables (METADATA, ARCHITECTURE, TOKENIZER, ESTIMATE) from log files
- Handles box-drawing formatted tables with varying column counts
- Categorizes models: Small (<1B), Medium (1-10B), Large (10-100B), Ultra-Large (100B+)
- Sorts by size category and parameter count
- CSV output with UTF-8 BOM encoding and semicolon delimiters
- Handles malformed data, misaligned columns, encoding errors
- Dynamic column discovery across different log formats

## Installation

### Linux/macOS

```bash
git clone https://github.com/hobbitlv1/convert_logs_to_excel && cd convert_logs_to_excel

python3 -m venv logtoexcel
source logtoexcel/bin/activate

pip install pandas
```

### Windows

```cmd
git clone https://github.com/hobbitlv1/convert_logs_to_excel && cd convert_logs_to_excel

python -m venv logtoexcel
logtoexcel\Scripts\activate

pip install pandas
```

## Usage

Place `.txt` log files in script directory and run:

```bash
# Linux/macOS
python3 convert_logs_to_excel.py

# Windows
python convert_logs_to_excel.py
```

Output: `models.csv` with all extracted data.

### Input Format

Box-drawing formatted ASCII tables with pipe delimiters:

```
+---------------------------------------+
| METADATA                              |
+-------+------+------+------------+----+
|  TYPE | NAME | ARCH | PARAMETERS |... |
+-------+------+------+------------+----+
| model | bert | bert |   22.57 M  |... |
+-------+------+------+------------+----+

+------------------------------------------------+
| ARCHITECTURE                                   |
+-----------------+---------------+--------+-----+
| MAX CONTEXT LEN | EMBEDDING LEN | LAYERS | ... |
+-----------------+---------------+--------+-----+
|       512       |      384      |    6   | ... |
+-----------------+---------------+--------+-----+
```

### Output Format

Semicolon-delimited CSV with UTF-8 BOM encoding:

```csv
"file";"METADATA_TYPE";"METADATA_NAME";"METADATA_ARCH";"METADATA_PARAMETERS";"MODEL_SIZE_CATEGORY";"ARCHITECTURE_MAX CONTEXT LEN"
"all-minilm_22m.txt";"model";"all-MiniLM-L6-v2";"bert";"22.57 M";"Small (<1B)";"512"
```

## Implementation

### Processing Pipeline

1. **File Discovery** - Glob `*.txt` files, process alphabetically, track column order
2. **Block Splitting** - Split by blank lines, each block = one table
3. **Table Parsing** - Extract pipe-delimited rows, map headers to values, handle mismatches
4. **Parameter Parsing** - Regex `([0-9]+(?:\.[0-9]+)?)\s*([KMBkmb])`, convert to raw counts
5. **Categorization** - Small (<10⁹), Medium (10⁹–10¹⁰), Large (10¹⁰–10¹¹), Ultra-Large (≥10¹¹)
6. **Output** - Sort by category/params, reorder columns, export CSV

### Key Functions

**`split_blocks(text)`** - Break file into logical table sections

**`parse_block(block)`** - Convert table to dict, returns `(label, {col: val})`

**`parse_parameters(value)`** - Convert "7.24 B" → 7,240,000,000

**`size_category(params)`** - Map param count to category string

**`parse_file(path)`** - Process single file, return flat record with prefixed keys

**`main()`** - Orchestrate processing, generate sorted CSV output

### Design Notes

- **Column Prefixing**: `METADATA_TYPE` vs `ESTIMATE_TYPE` prevents collisions
- **Dynamic Columns**: Auto-generates `EXTRA_N` when data exceeds headers
- **Encoding**: `errors="ignore"` for robust parsing
- **ESTIMATE Tables**: Uses predefined `ESTIMATE_COLUMNS` for complex multi-row headers

## Customization

### Modify Size Thresholds

```python
def size_category(params: float | None) -> str:
    if params is None:
        return "Unknown"
    if params < 500_000_000:
        return "Tiny (<500M)"
```

### Change CSV Format

```python
df.to_csv(
    output_path,
    sep=",",                    # Comma delimiter
    quoting=csv.QUOTE_MINIMAL,
    encoding="utf-8",           # Remove BOM
)
```

### Add Table Type Handling

```python
if label == "YOUR_TABLE":
    columns = YOUR_COLUMN_LIST
```

## Troubleshooting

### No data to write

**Cause**: No `.txt` files or unparseable content

**Fix**: 
- Verify `.txt` files in script directory
- Check pipe-delimited table structure
- Test with `all-minilm_22m.txt` example

### PermissionError on output

**Cause**: `models.csv` open in Excel

**Fix**: Close file and rerun (script auto-generates fallback filename)

### Missing/incorrect data

**Cause**: Malformed tables or misaligned columns

**Fix**:
- Verify box-drawing structure: `+---+` and `| col |`
- Check blank line separators
- ESTIMATE tables use predefined columns for complex headers

### Parameter parsing fails

**Cause**: Non-standard format

**Fix**: Regex expects optional whitespace between number and unit (`7.24 B` or `7.24B`)

```python
match = re.match(r"([0-9]+(?:\.[0-9]+)?)\s*([KMBkmb])", text)
```
