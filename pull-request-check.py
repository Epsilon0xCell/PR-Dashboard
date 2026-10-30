"""Export a repository's pull requests to a CSV file.

Asks for a repository (user/repo) and an output file name, walks the
GitHub API's pull request list, and writes one row per pull request.

Two API facts shape this code:

- The list endpoint does not return a pull request's comment count or
  changed-file count. The first version of this script read both fields
  from the list response anyway, so every CSV it produced had 0 in those
  two columns. They are now fetched per pull request from the detail
  endpoint, which is the only place the API publishes them. The cost is
  one extra request per pull request, so big repositories take a while.
- Unauthenticated callers get 60 requests an hour. The pagination loop
  watches the rate-limit headers and waits for the reset instead of
  failing halfway through an export.
"""
import csv
import time

import requests

API = "https://api.github.com"
# I cap the walk at 10 pages. At the default page size that gives me
# the newest 300 pull requests, and it stops a huge repo from burning
# the whole unauthenticated rate budget on one export.
MAX_PAGES = 10


def _raise_for_status(response, url):
    if response.status_code == 200:
        return
    # I raise with the message from the error body because that body is
    # a dict, not a list. If I let the caller iterate it, the export
    # fails later with a type error that hides the real API problem.
    try:
        message = response.json().get("message", "")
    except ValueError:
        message = ""
    raise RuntimeError(
        f"GitHub API returned HTTP {response.status_code} for {url}"
        + (f": {message}" if message else ""))


def _get(url):
    # I set a timeout here and in the page walk below. Without one a
    # stalled connection would hang the export with no error at all.
    response = requests.get(url, timeout=30)
    _raise_for_status(response, url)
    return response


def get_pull_requests(repo):
    pull_requests = []
    page = 1
    while page <= MAX_PAGES:
        url = f"{API}/repos/{repo}/pulls?page={page}"
        # I call requests.get directly here instead of my _get helper
        # because I have to read the rate limit headers before I decide
        # if this response is an error worth raising on.
        response = requests.get(url, timeout=30)
        # I read the header with .get and a default because an error
        # page or a proxy can strip it. A KeyError here used to kill the
        # whole export over a header I only need for one check.
        remaining = int(response.headers.get("X-RateLimit-Remaining", "1"))
        if response.status_code in (403, 429) and remaining == 0:
            # I handle the rate limit here, before _raise_for_status
            # sees it. The limit arrives as an error status, so if I
            # raised first I would never get the chance to wait. I
            # retry the same page after the reset instead of skipping
            # it, or that page of pull requests would just be missing.
            reset_time = int(response.headers.get("X-RateLimit-Reset", "0"))
            # I add one second past the reset and I never wait less
            # than one second, even if the reset time is already past.
            wait_time = max(reset_time - int(time.time()) + 1, 1)
            print(f"API rate limit exceeded. Waiting for {wait_time} seconds.")
            time.sleep(wait_time)
            continue
        _raise_for_status(response, url)
        data = response.json()
        # An empty page is how I know the walk is done. I do not keep
        # paging until MAX_PAGES once the repo has no more to give.
        if not data:
            break
        pull_requests.extend(data)
        page += 1
    return pull_requests


def get_pull_request_detail(repo, number):
    return _get(f"{API}/repos/{repo}/pulls/{number}").json()


def get_pull_request_data(repo, pull_request):
    # I use "or {}" here and not .get with a {} default. The closed_by
    # key is present but null on a pull request nobody closed, and a
    # default only helps when the key is missing entirely.
    user_closed = (pull_request.get("closed_by") or {}).get("login")
    # I fetch the detail record after I read the list fields because
    # the count fields I need only exist on that second request.
    detail = get_pull_request_detail(repo, pull_request["number"])
    return (
        pull_request["number"],
        pull_request["created_at"],
        pull_request["closed_at"],
        pull_request["user"]["login"],
        user_closed,
        pull_request["state"],
        detail.get("comments", 0),
        detail.get("changed_files", 0),
    )


def main():
    repo = input("Enter the name of the GitHub repository (e.g. user/repo): ")
    filename = input("Enter the name of the CSV file: ")
    try:
        pull_requests = get_pull_requests(repo)
        # I pass newline="" because the csv module wants to control
        # line endings itself. Without it the file gets blank rows on
        # some platforms.
        with open(filename, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            # I keep this header order matched to the tuple order in
            # get_pull_request_data. The csv writer does no checking,
            # so a drift between the two would mislabel every column
            # without raising anything.
            writer.writerow(["PR Number", "Date Opened", "Date Closed",
                             "User Opened", "User Closed", "Status",
                             "Number of Comments", "Number of Files Changed"])
            for pull_request in pull_requests:
                writer.writerow(get_pull_request_data(repo, pull_request))
        print(f"Data from pull requests in repository {repo} has been saved to {filename}.")
    except Exception as exc:
        # I catch broadly here because this is an interactive tool. I
        # would rather print one plain error line than dump a traceback
        # on the person who typed the repo name.
        print(f"An error occurred: {exc}")


if __name__ == "__main__":
    main()
