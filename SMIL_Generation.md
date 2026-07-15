# gen_abr_smil.py

A Python utility that automatically generates Wowza Streaming Engine SMIL files for Adaptive Bitrate (ABR) video renditions.

The script scans a directory (or processes a single ABR rendition basename), extracts media metadata using **ffprobe**, and generates one Wowza-compatible `.smil` file for each detected Adaptive Bitrate rendition set.

## Features

- Recursively scans directories for MP4 renditions
- Automatically groups renditions into ABR sets
- Extracts media metadata using `ffprobe`
- Validates that each rendition contains:
  - One video stream
  - One audio stream
  - Video bitrate
  - Audio bitrate
- Sorts renditions by ascending video bitrate
- Generates Wowza-compatible SMIL files
- Produces human-readable XML
- Supports generating one or many SMIL files in a single run

## Workflow

```text
Start
  │
  ▼
Verify ffprobe is installed
  │
  ▼
Parse command-line arguments
  │
  ▼
Determine input type
  │
  ├─ Directory
  │      │
  │      ▼
  │  Scan recursively for MP4 files
  │
  └─ Basename
         │
         ▼
Use supplied basename
  │
  ▼
Locate matching renditions
  │
  ▼
Extract stream metadata
  │
  ▼
Validate streams and bitrates
  │
  ▼
Sort renditions by bitrate
  │
  ▼
Generate Wowza SMIL file
  │
  ▼
Repeat for remaining ABR groups
  │
  ▼
Complete
```

Each rendition group is processed independently. If one group contains invalid media files, processing continues with the remaining groups.

## Requirements

- Python 3
- FFmpeg (`ffprobe`)
- lxml

Install the required Python package:

```bash
pip install lxml
```

Verify that FFmpeg is installed:

```bash
ffprobe -version
```

## Expected Naming Convention

The script expects rendition filenames to follow a common Adaptive Bitrate naming convention.

The bitrate portion of each filename **must** match the pattern:

```text
_<bitrate>k
```

where `<bitrate>` is a numeric bitrate in kilobits per second.

Examples:

```text
movie_500k.mp4
movie_1000k.mp4
movie_1500k.mp4
movie_2500k.mp4
```

or

```text
movie_500k_s.mp4
movie_1000k_s.mp4
movie_1500k_s.mp4
```

All files sharing the same basename are grouped into a single SMIL file.

For example:

```text
movie_500k.mp4
movie_1000k.mp4
movie_1500k.mp4
```

produces:

```text
movie.smil
```

## Usage

Generate SMIL files for every rendition set in a directory:

```bash
python3 gen_abr_smil.py /path/to/videos
```

Generate a SMIL file for a single ABR rendition set:

```bash
python3 gen_abr_smil.py /path/to/videos/movie
```

Write generated SMIL files to another directory:

```bash
python3 gen_abr_smil.py /path/to/videos \
    --output-dir /path/to/output
```

## Generated Output

For the following renditions:

```text
movie_500k.mp4
movie_1000k.mp4
movie_1500k.mp4
```

the script generates:

```text
movie.smil
```

containing entries similar to:

```xml
<video src="movie_500k.mp4" ... />
<video src="movie_1000k.mp4" ... />
<video src="movie_1500k.mp4" ... />
```

ordered by increasing video bitrate.

## Validation

Each rendition must contain:

- One video stream
- One audio stream
- A valid video bitrate
- A valid audio bitrate

Files that fail validation are skipped.

If no valid renditions remain for an ABR group, a SMIL file is not generated for that group.

## Output Directory

By default, SMIL files are written to the same directory as the source media.

An alternate output location may be specified using:

```bash
--output-dir <directory>
```

The output directory is created automatically if it does not already exist.

## Error Handling

The script reports errors for individual rendition groups while continuing to process the remaining groups whenever possible.

Examples include:

- Missing video stream
- Missing audio stream
- Missing bitrate information
- Invalid media files
- Missing `ffprobe`
- No valid renditions found

## Notes

- Renditions are automatically sorted by ascending video bitrate.
- Renditions whose filenames contain `"mobile"` are ignored.
- XML output is formatted with pretty printing for readability.
- One SMIL file is generated for each detected ABR rendition group.
