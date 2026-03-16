# Quickstart: Fix Census Validation Warning Persistence

## Problem

When re-uploading a corrected census file with the same filename, validation warnings from the first upload persist because the browser's file input doesn't fire `onChange` for duplicate filenames.

## Fix

Reset the file input's value after each upload in `DataSourcesSection.tsx`.

## How to Test

1. Launch PlanAlign Studio: `planalign studio`
2. Open a workspace and navigate to Data Sources
3. Upload a census CSV that triggers a warning (e.g., missing `hire_date` column)
4. Fix the CSV to include the missing column
5. Re-upload the same filename
6. **Expected**: Previous warnings clear, fresh validation runs, no stale warnings shown

## File to Modify

- `planalign_studio/components/config/DataSourcesSection.tsx` — add `fileInputRef.current.value = ''` after upload success and error handlers

## Verification

- Manual test: Re-upload same file → onChange fires → warnings refresh
- Manual test: Upload file with warnings → upload corrected file → warnings clear
- Manual test: Upload fails → warnings from previous upload are cleared
