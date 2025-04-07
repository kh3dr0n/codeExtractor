#!/usr/bin/env python3
import re
import os
import argparse
import sys
import logging

# Regex to find the filename marker line: **`path/to/filename.ext`:**
# REVISED to allow extra text before/after backticks but within **:**
FILENAME_MARKER_REGEX = re.compile(
    r"^\s*\*\*\s*(?:.*?)`([^`]+)`(?:.*?)\s*:\*\*\s*$", # Allows extra text like "1." or "(Test)"
    re.MULTILINE
)

def find_next_fence(text, start_pos, fences=("```", "~~~")):
    """Finds the starting index of the next occurrence of any fence marker."""
    next_pos = -1
    for fence in fences:
        pos = text.find(fence, start_pos)
        if pos != -1:
            if next_pos == -1 or pos < next_pos:
                next_pos = pos
    return next_pos

def code_extractor(markdown_content, output_dir):
    """
    Manually parses markdown to find markers and extract subsequent code blocks.
    """
    found_files_count = 0
    current_pos = 0 # Keep track of where we are in the main string

    logging.info(f"Manually searching for filename markers and associated code blocks...")

    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        logging.info(f"Error: Cannot create base output directory '{output_dir}': {e}", file=sys.stderr)
        sys.exit(1)

    while current_pos < len(markdown_content):
        # Find the next filename marker from the current position
        marker_match = FILENAME_MARKER_REGEX.search(markdown_content, pos=current_pos)

        if not marker_match:
            # No more markers found in the rest of the file
            break

        marker_start_pos = marker_match.start()
        marker_end_pos = marker_match.end()
        # Group 1 still correctly captures only the path inside backticks
        relative_filepath = marker_match.group(1).strip()
        relative_filepath = relative_filepath.strip('/\\')

        logging.info(f"\nFound marker for: '{relative_filepath}' (ends at index {marker_end_pos})")

        if not relative_filepath:
            logging.info(f"Warning: Found marker near position {marker_start_pos} with empty filename. Skipping.")
            current_pos = marker_end_pos # Move past this invalid marker
            continue

        # --- Find the start of the code block ---
        # Search for the beginning of the opening fence line (\n``` or \n~~~)
        # Allows a blank line between marker and fence
        search_after_marker_pos = marker_end_pos
        next_newline_pos = markdown_content.find('\n', search_after_marker_pos)

        if next_newline_pos == -1:
             logging.info(f"Warning: No newline found after marker for '{relative_filepath}'. Cannot find code block. Skipping rest of file.")
             break # Cannot proceed

        # Look for ``` or ~~~ immediately after the newline (allowing leading spaces)
        potential_fence_line_start = next_newline_pos + 1
        fence_line_end = markdown_content.find('\n', potential_fence_line_start)
        if fence_line_end == -1: fence_line_end = len(markdown_content) # Handle case of last line

        fence_line = markdown_content[potential_fence_line_start:fence_line_end].strip()
        opening_fence = None
        if fence_line.startswith("```"):
            opening_fence = "```"
        elif fence_line.startswith("~~~"):
             opening_fence = "~~~"

        # Check if this fence immediately follows the marker (ignoring whitespace)
        intervening_text = markdown_content[marker_end_pos:potential_fence_line_start]
        if opening_fence and intervening_text.strip() == "":
            code_start_index = fence_line_end + 1
            logging.debug(f"Found opening fence '{opening_fence}' at line start index {potential_fence_line_start}. Code starts at {code_start_index}.")
            

            # --- Find the end of the code block ---
            # Search for the closing fence line (\n``` or \n~~~) followed by newline or EOF
            closing_fence_str = "\n" + opening_fence # Search for newline followed by the *same* fence type
            closing_fence_index = markdown_content.find(closing_fence_str, code_start_index)

            if closing_fence_index != -1:
                # Check if this closing fence is truly on a line by itself (allow whitespace)
                closing_line_start = closing_fence_index + 1 # Start of the potential closing line content
                closing_line_end = markdown_content.find('\n', closing_line_start)
                if closing_line_end == -1: closing_line_end = len(markdown_content)

                closing_line_content = markdown_content[closing_line_start:closing_line_end].strip()

                # Ensure the stripped closing line *exactly* matches the opening fence marker
                if closing_line_content == opening_fence:
                    # Found valid closing fence
                    code_content = markdown_content[code_start_index:closing_fence_index] # Extract code up to the newline before closing fence
                    logging.debug(f"Found closing fence '{opening_fence}' starting at newline index {closing_fence_index}.")

                    # --- Save the file ---
                    output_filepath = os.path.join(output_dir, relative_filepath)
                    output_filedir = os.path.dirname(output_filepath)

                    try:
                        if output_filedir:
                            os.makedirs(output_filedir, exist_ok=True)
                    except OSError as e:
                        logging.info(f"Error: Cannot create directory '{output_filedir}' for file '{relative_filepath}': {e}", file=sys.stderr)
                        current_pos = closing_line_end # Move past this block
                        continue

                    try:
                        # Use .strip() on final code to remove potential leading/trailing whitespace from capture
                        code_to_write = code_content.strip()
                        if code_to_write:
                             with open(output_filepath, 'w', encoding='utf-8') as f:
                                f.write(code_to_write)
                             logging.info(f"  Saved: '{output_filepath}'")
                             found_files_count += 1
                        else:
                             logging.info(f"  Skipped empty code block for: '{relative_filepath}'")

                    except IOError as e:
                        logging.error(f"Error writing file '{output_filepath}': {e}", file=sys.stderr)
                    except Exception as e:
                        logging.error(f"An unexpected error occurred while writing '{output_filepath}': {e}", file=sys.stderr)

                    # Advance position past the processed code block
                    current_pos = closing_line_end

                else:
                     # Found \n``` but the line had other content or didn't exactly match (e.g., ``` closing ```)
                     logging.info(f"Warning: Found potential closing fence marker near {closing_fence_index} for '{relative_filepath}', but line content '{closing_line_content}' doesn't exactly match fence '{opening_fence}'. Still searching...")
                     # Need to advance past this false positive to continue search correctly
                     current_pos = closing_fence_index + 1 # Continue search after the newline of the false positive

            else:
                # Opening fence found, but no closing fence found later
                logging.info(f"Warning: Found opening fence for '{relative_filepath}' but could not find closing fence '{opening_fence}' on its own line. Skipping file.")
                current_pos = code_start_index # Move past the opening fence at least

        else:
            # No opening fence found immediately after marker
            logging.info(f"Warning: Marker found for '{relative_filepath}', but no opening code fence (``` or ~~~) found immediately after (ignoring whitespace).")
            # Advance position past the marker we just processed
            current_pos = marker_end_pos

    # --- End of while loop ---

    if found_files_count == 0:
        logging.error("\nNo files were extracted using manual parsing. Check marker format (**`path/file`:** with potential extra text), code block start/end (``` on its own line), and intervening whitespace.")
    else:
        logging.info(f"\nSuccessfully extracted {found_files_count} file(s).")


def main():
    parser = argparse.ArgumentParser(
        description="Extracts specific fenced code blocks from Markdown based on preceding filename markers (**`path/file.ext`:**) using manual parsing.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
    parser.add_argument(
        "input_file",
        help="Path to the input Markdown file."
        )
    parser.add_argument(
        "-o", "--output-dir",
        default="output_files", # Default dir name
        help="Directory where the extracted files (with structure) will be saved."
        )

    args = parser.parse_args()

    input_filepath = args.input_file
    output_directory = args.output_dir

    if not os.path.isfile(input_filepath):
        logging.error(f"Error: Input file not found: '{input_filepath}'", file=sys.stderr)
        sys.exit(1)

    logging.info(f"Reading Markdown from: '{input_filepath}'")
    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        # Normalize line endings (still useful for consistency)
        markdown_content = markdown_content.replace('\r\n', '\n').replace('\r', '\n')
    except Exception as e:
        logging.error(f"Error reading input file '{input_filepath}': {e}", file=sys.stderr)
        sys.exit(1)

    code_extractor(markdown_content, output_directory)
    logging.info("Processing complete.")

if __name__ == "__main__":
    main()