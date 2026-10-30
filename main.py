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

# I keep the original guard that compared the count against 10**32 - 1
# and wrote nothing past it. The workflow would need geological time to
# get there, but I keep the ceiling so the file acts at the boundary the
# same way it always has.
MAX_COUNT = 99999999999999999999999999999999


def read_count(path):
    """Return the first integer on the first line of the status file."""
    # I only read the first line because that is the only line that holds
    # the count. The rest of the file is fixed display text.
    with open(path, "r") as fh:
        text = fh.readline()
    # I pick the first token that is all digits and ignore the words
    # around it. If no token matches, the index fails on purpose and my
    # caller treats that as no count yet.
    return [int(word) for word in text.split() if word.isdigit()][0]


def write_status(path, first_line):
    # I write the pieces with no newline and no extra spaces between
    # them. The rendered profile page depends on that tight shape, so I
    # do not pretty print this file.
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
        # I let every failure land here on purpose. A missing status.md
        # on the very first run, an empty file, and a first line with no
        # number in it all mean the same thing to me: no count yet. I
        # restart at 1 instead of letting the run fail and the count
        # freeze forever. I keep the singular wording on the restart
        # line because that is the format this file has always used.
        write_status(STATUS_FILE, "1 pull request merged")
        return
    # I write nothing when the count passes the ceiling. I do not clamp
    # it and I do not wrap it, because a silent no write keeps the last
    # honest count in place.
    if count <= MAX_COUNT:
        write_status(STATUS_FILE, f"{count} pull requests merged")


if __name__ == "__main__":
    main()
