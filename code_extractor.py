#!/usr/bin/env python3
import re
import os
import argparse
import sys

# Regex 1: Find lines that start and end with **, capturing the whole line content.
# Allows any characters between the ** markers.
FILENAME_MARKER_LINE_REGEX = re.compile(
    r"^\s*\*([^\n]+)\*\s*$", # Simpler: Match **, capture content until next **, ensure end of line
    re.MULTILINE
)
# Note: The above might be too simple if ** occurs mid-text often.
# Let's try one that specifically looks for ** at start and end of the significant content.
FILENAME_MARKER_LINE_REGEX = re.compile(
    r"^\s*(\*\*.+?\*\*)\s*$", # Capture the whole marker including **...**
    re.MULTILINE
)


# Regex 2: Extract content within the first pair of backticks `...` found inside a line.
FILENAME_EXTRACT_REGEX = re.compile(r"`([^`]+)`")


def extract_files_manually(markdown_content, output_dir):
    """
    Manually parses markdown to find markers (flexible format) and extracts
    subsequent code blocks.
    """
    found_files_count = 0
    current_pos = 0 # Keep track of where we are in the main string

    print(f"Manually searching for filename marker lines (**...**) and associated code blocks...")

    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        print(f"Error: Cannot create base output directory '{output_dir}': {e}", file=sys.stderr)
        sys.exit(1)

    while current_pos < len(markdown_content):
        # Find the next potential marker line from the current position
        marker_line_match = FILENAME_MARKER_LINE_REGEX.search(markdown_content, pos=current_pos)

        if not marker_line_match:
            break # No more potential marker lines

        # Get the full matched line (including **) and its position
        marker_line_content = marker_line_match.group(1) # Content including **...**
        marker_start_pos = marker_line_match.start()     # Start index of the matched line
        marker_end_pos = marker_line_match.end()         # End index of the matched line (after \n potentially)

        # Now extract the filename from within the backticks in this line
        filename_extract_match = FILENAME_EXTRACT_REGEX.search(marker_line_content)

        if not filename_extract_match:
            # This **...** line didn't contain `filename`, skip it
            print(f"DEBUG: Skipping line ending at {marker_end_pos} - no `filename` found within: {repr(marker_line_content)}")
            current_pos = marker_end_pos # Move past this non-conforming line
            continue

        # Found a valid filename within the marker line
        relative_filepath = filename_extract_match.group(1).strip()
        relative_filepath = relative_filepath.strip('/\\')

        print(f"\nFound marker for: '{relative_filepath}' (from line: {repr(marker_line_content.strip())}, ends at index {marker_end_pos})")

        if not relative_filepath:
            print(f"Warning: Found marker line near position {marker_start_pos} but extracted empty filename. Skipping.")
            current_pos = marker_end_pos # Move past this invalid marker
            continue

        # --- Find the start of the code block (manual parsing logic remains the same) ---
        search_after_marker_pos = marker_end_pos
        next_newline_pos = markdown_content.find('\n', search_after_marker_pos)

        if next_newline_pos == -1:
             print(f"Warning: No newline found after marker for '{relative_filepath}'. Cannot find code block. Skipping rest of file.")
             break

        potential_fence_line_start = next_newline_pos + 1
        fence_line_end = markdown_content.find('\n', potential_fence_line_start)
        if fence_line_end == -1: fence_line_end = len(markdown_content)

        fence_line = markdown_content[potential_fence_line_start:fence_line_end].strip()
        opening_fence = None
        if fence_line.startswith("```"):
            opening_fence = "```"
        elif fence_line.startswith("~~~"):
             opening_fence = "~~~"

        intervening_text = markdown_content[marker_end_pos:potential_fence_line_start]
        if opening_fence and intervening_text.strip() == "":
            code_start_index = fence_line_end + 1
            print(f"DEBUG: Found opening fence '{opening_fence}' at line start index {potential_fence_line_start}. Code starts at {code_start_index}.")

            # --- Find the end of the code block ---
            closing_fence = "\n" + opening_fence
            closing_fence_index = markdown_content.find(closing_fence, code_start_index)

            if closing_fence_index != -1:
                closing_line_start = closing_fence_index + 1
                closing_line_end = markdown_content.find('\n', closing_line_start)
                if closing_line_end == -1: closing_line_end = len(markdown_content)

                closing_line_content = markdown_content[closing_line_start:closing_line_end].strip()

                if closing_line_content == opening_fence:
                    code_content = markdown_content[code_start_index:closing_fence_index]
                    print(f"DEBUG: Found closing fence '{opening_fence}' starting at newline index {closing_fence_index}.")

                    # --- Save the file ---
                    output_filepath = os.path.join(output_dir, relative_filepath)
                    output_filedir = os.path.dirname(output_filepath)

                    try:
                        if output_filedir:
                            os.makedirs(output_filedir, exist_ok=True)
                    except OSError as e:
                        print(f"Error: Cannot create directory '{output_filedir}' for file '{relative_filepath}': {e}", file=sys.stderr)
                        current_pos = closing_line_end
                        continue

                    try:
                        code_to_write = code_content.strip()
                        if code_to_write:
                             with open(output_filepath, 'w', encoding='utf-8') as f:
                                f.write(code_to_write)
                             print(f"  Saved: '{output_filepath}'")
                             found_files_count += 1
                        else:
                             print(f"  Skipped empty code block for: '{relative_filepath}'")

                    except IOError as e:
                        print(f"Error writing file '{output_filepath}': {e}", file=sys.stderr)
                    except Exception as e:
                        print(f"An unexpected error occurred while writing '{output_filepath}': {e}", file=sys.stderr)

                    current_pos = closing_line_end # Advance past processed block

                else:
                     print(f"Warning: Found potential closing fence marker near {closing_fence_index} for '{relative_filepath}', but line content '{closing_line_content}' doesn't match fence '{opening_fence}'. Still searching...")
                     current_pos = closing_fence_index + 1 # Continue search after the false positive

            else:
                print(f"Warning: Found opening fence for '{relative_filepath}' but could not find closing fence '{opening_fence}' on its own line. Skipping file.")
                current_pos = code_start_index

        else:
            print(f"Warning: Marker line found ending at {marker_end_pos} for '{relative_filepath}', but no opening code fence (``` or ~~~) found immediately after (ignoring whitespace).")
            current_pos = marker_end_pos # Advance past the marker line

    # --- End of while loop ---

    if found_files_count == 0:
        print("\nNo files were extracted using manual parsing. Check marker format (**...`filename`...**), code block start/end (``` on its own line), and intervening whitespace.")
    else:
        print(f"\nSuccessfully extracted {found_files_count} file(s).")


def main():
    parser = argparse.ArgumentParser(
        description="Extracts specific fenced code blocks from Markdown based on preceding filename markers (**...`path/file.ext`...**). Handles multiple marker formats.",
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
        print(f"Error: Input file not found: '{input_filepath}'", file=sys.stderr)
        sys.exit(1)

    print(f"Reading Markdown from: '{input_filepath}'")
    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        # Normalize line endings
        markdown_content = markdown_content.replace('\r\n', '\n').replace('\r', '\n')
    except Exception as e:
        print(f"Error reading input file '{input_filepath}': {e}", file=sys.stderr)
        sys.exit(1)

    extract_files_manually(markdown_content, output_directory)
    print("Processing complete.")

if __name__ == "__main__":
    main()