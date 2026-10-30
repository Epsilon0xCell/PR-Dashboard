"""Advance the merged-pull-request counter in status.md by one.

The scheduled workflow (.github/workflows/update.yaml) runs this every
few minutes and opens a pull request with the result, which is how the
count climbed into the thousands: the number is a running total kept in
status.md itself, not a value recomputed from the API. That design is
why this script only ever reads the first line of one small file.

status.md is data, not just output. Its exact shape is rendered on the
profile, so the write format below does not change: the count line, a
<br>, "Currently:", a <br>, and the PR.png image line.
"""

STATUS_FILE = "status.md"
IMAGE_LINE = "![goal](PR.png)"

# The original guard compared the count against 10**32 - 1 and wrote
# nothing past it. The workflow would need geological time to get there,
# but the ceiling is kept so the file's behavior at the boundary is the
# same as it has always been.
MAX_COUNT = 99999999999999999999999999999999


def read_count(path):
    """Return the first integer on the first line of the status file."""
    with open(path, "r") as fh:
        text = fh.readline()
    return [int(word) for word in text.split() if word.isdigit()][0]


def write_status(path, first_line):
    with open(path, "w") as fh:
        fh.write(first_line)
        fh.write("<br>")
        fh.write("Currently:")
        fh.write("<br>")
        fh.write(IMAGE_LINE)


def main():
    try:
        count = read_count(STATUS_FILE) + 1
    except Exception:
        # Every failure lands here on purpose: a missing status.md (the
        # very first run), an empty one, or a first line with no number in
        # it. All of them mean "no count yet", and the counter this
        # workflow exists to advance restarts at 1 rather than the run
        # failing and the count freezing forever. The singular wording of
        # the restart line is the file's historical format; keep it.
        write_status(STATUS_FILE, "1 pull request merged")
        return
    if count <= MAX_COUNT:
        write_status(STATUS_FILE, f"{count} pull requests merged")


if __name__ == "__main__":
    main()
