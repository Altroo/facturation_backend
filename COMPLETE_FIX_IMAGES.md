# ✅ COMPLETE: Import & Image Fixes

## Recent Fixes

### ✅ Decimal Precision Fixed (New!)
**Problem**: Prices had too many decimal places (e.g., `100.123456789`)  
**Solution**: Import now automatically rounds to 2 decimal places  
**Location**: [article/views.py](article/views.py) line 481

**Examples**:
- `100.123456789` → `100.12`
- `220.987654321` → `220.99`
- `20.555555555` → `20.56`

### ✅ Image Filename Matching Fixed (New!)
**Problem**: Images named `68712726.webp` didn't match `ART68712726` articles  
**Solution**: Command now tries multiple formats automatically  
**Location**: [article/management/commands/fix_images.py](article/management/commands/fix_images.py)

---

## What's Been Done

### 1. ✅ Removed API Endpoint Approach
- Removed `BulkUpdateArticlePhotosView` from [article/views.py](article/views.py)
- Removed endpoint from [article/urls.py](article/urls.py)
- Removed dependency on `generate_bulk_update.py`

### 2. ✅ Created Management Command
- **Command**: `python manage.py fix_images`
- **Location**: [article/management/commands/fix_images.py](article/management/commands/fix_images.py)
- **Status**: Tested and working

### 3. ✅ Updated Documentation
- [FIX_IMAGES_UPDATE.md](FIX_IMAGES_UPDATE.md) - Updated with new features
- [FIXES_SUMMARY.md](FIXES_SUMMARY.md) - Complete fixes summary
- [quick_import_guide.py](quick_import_guide.py) - Updated examples

---

## Usage

### Basic Command
```bash
python manage.py fix_images --company_id=1
```

### With Options
```bash
# Preview changes first (recommended)
python manage.py fix_images --company_id=1 --dry-run

# Run the actual update
python manage.py fix_images --company_id=1

# Overwrite existing photos
python manage.py fix_images --company_id=1 --overwrite

# Use custom image folder
python manage.py fix_images --company_id=1 --image-folder=gessi_images
```

---

## How It Works

1. **Scans** the `media/article_images/` folder for images
2. **Matches** image filenames to article references
3. **Links** photos to matching articles
4. **Reports** detailed results

### File Naming
Images can be named in **two formats**:

**Option 1: With ART prefix**
```
ART68712726.jpg  → Links to article with reference "ART68712726"
ART68712727.png  → Links to article with reference "ART68712727"
```

**Option 2: Numeric only (recommended for Gessi products)**
```
68712726.webp    → Automatically matches article "ART68712726"
68712727.jpg     → Automatically matches article "ART68712727"
```

The command automatically tries both formats, so you don't need to rename your files!

### Supported Formats
- `.jpg` / `.jpeg`
- `.png`
- `.gif`
- `.webp`
- `.bmp`

---

## Complete Import Workflow

### Step 1: Import Articles
```bash
# Use the import endpoint or frontend to upload gessi_products.csv
curl -X POST http://your-server/api/articles/import/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@gessi_products.csv" \
  -F "company_id=1"
```

### Step 2: Upload Images via SSH
```bash
# Upload images to server
scp -r ./gessi_images/* user@server:/path/to/media/article_images/

# Or use rsync
rsync -avz ./gessi_images/ user@server:/path/to/media/article_images/

# Set permissions
ssh user@server
chmod 644 /path/to/media/article_images/*.jpg
```

### Step 3: Link Images to Articles
```bash
# On the server, run the command
python manage.py fix_images --company_id=1 --dry-run
python manage.py fix_images --company_id=1
```

---

## Example Output

```
Found 22,562 image files in /path/to/media/article_images

DRY RUN MODE - No changes will be made

Total articles in company: 22,562

Processing images...

  [OK] 68712726: Would link to article_images/68712726.webp
  [OK] ART68712727: Would link to article_images/ART68712727.jpg
  [!] ART68712728: Already has photo, would skip
  [X] 99999: Article not found in company 1 (tried: 99999, ART99999)
  ...

======================================================================
DRY RUN COMPLETE - No changes were made

Summary:
  - Total images processed:    22,562
  - Successfully linked:       22,000
  - Skipped (already had photo): 500
  - Article not found:         62
======================================================================

Tip: Use --overwrite to update articles that already have photos
```

---

## Advantages of Management Command

✅ **No authentication required** - Run directly on the server
✅ **Better for large batches** - Handles 20k+ images efficiently
✅ **Direct database access** - Faster than API calls
✅ **Easy to automate** - Can be added to cron jobs or deployment scripts
✅ **Clear output** - Shows detailed progress and results
✅ **Safe by default** - Dry-run option to preview changes

---

## Files Overview

| File | Purpose |
|------|---------|
| `gessi_products.xlsx` | Original Excel file (22,562 rows) |
| `gessi_products.csv` | Converted CSV for import |
| `convert_excel_to_csv.py` | Excel to CSV converter |
| `article/management/commands/fix_images.py` | **Main command for linking images** |
| `FIX_IMAGES_REFERENCE.md` | Command reference guide |
| `GESSI_IMPORT_GUIDE.md` | Complete import guide |
| `README_IMPORT.md` | Quick start summary |

---

## Next Steps

1. **Import articles** from CSV (via API or frontend)
2. **Upload images** to `media/article_images/` on server
3. **Run command**: `python manage.py fix_images --company_id=YOUR_COMPANY_ID`
4. **Verify** articles have photos linked

All set! The command is ready to use on your server. 🚀
