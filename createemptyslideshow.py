import argparse
from pathlib import Path
import re
import json
import os

def sanitize_folder_name(name: str) -> Path:
    """Sanitize folder path to prevent directory traversal and invalid names."""
    # Normalize path and split into components
    normalized = os.path.normpath(name)
    parts = Path(normalized).parts
    
    safe_parts = []
    for part in parts:
        # Block dangerous path components
        if part in ('', '.', '..'):
            raise ValueError(f"Invalid path component: '{part}'")
        # Restrict to safe characters (alphanumeric, underscore, hyphen, dot, space)
        if not re.fullmatch(r'[\w\-\. ]+', part):
            raise ValueError(f"Invalid characters in folder name: '{part}'")
        safe_parts.append(part)
    
    # Reconstruct path and verify it's relative
    safe_path = Path(*safe_parts)
    if safe_path.is_absolute():
        raise ValueError("Absolute paths are not allowed")
    
    return safe_path

def create_slides(folder_name: str, num_slides: int, with_transition: bool = True):
    """Create slide{i}.html and optionally transition.json in assets/slideshows/<folder_name>/."""
    if num_slides < 1:
        raise ValueError("Number of slides must be at least 1.")

    safe_folder = sanitize_folder_name(folder_name)
    base_path = Path("slideshows") / safe_folder
    
    # Prevent directory traversal beyond slideshows/
    if not str(base_path.resolve()).startswith(str(Path("slideshows").resolve())):
        raise ValueError("Path traversal attempt detected")
    
    base_path.mkdir(parents=True, exist_ok=True)

    for i in range(1, num_slides + 1):
        html_file = base_path / f"slide{i}.html"
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Slide {i}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .slide-content {{ max-width: 800px; margin: 0 auto; }}
    </style>
</head>
<body>
    <div class="slide-content">
        <h1>Slide {i}</h1>
        <p><!-- Add your content here --></p>
    </div>
</body>
</html>
"""
        html_file.write_text(html_content, encoding="utf-8")
        print(f"Created: {html_file}")

    if with_transition:
        transition_file = base_path / "transition.json"
        if not transition_file.exists():
            transition_data = {
                str(i): {"effect": "none", "duration": 0} 
                for i in range(1, num_slides + 1)
            }
            transition_file.write_text(json.dumps(transition_data, indent=4), encoding="utf-8")
            print(f"Created: {transition_file}")
        else:
            print(f"Skipped (already exists): {transition_file}")

def main():
    parser = argparse.ArgumentParser(
        description="Create slide files and transition configuration in slideshows/<folder>/"
    )
    parser.add_argument("folder", help="Subfolder path inside 'slideshows/' (relative path only)")
    parser.add_argument("num_slides", type=int, help="Number of slides to generate (≥1)")
    parser.add_argument("--no-transition", action="store_true", 
                        help="Skip generation of transition.json file")

    args = parser.parse_args()
    with_transition = not args.no_transition

    try:
        create_slides(args.folder, args.num_slides, with_transition)
        print(f"\n✅ Successfully created {args.num_slides} slide(s) in slideshows/{args.folder}/")
        if with_transition:
            print("✅ transition.json file generated")
        else:
            print("⚠️  transition.json generation skipped")
    except (ValueError, OSError) as e:
        print(f"❌ Critical error: {e}")
        exit(1)

if __name__ == "__main__":
    main()