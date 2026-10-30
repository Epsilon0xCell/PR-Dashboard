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
MAX_PAGES = 10  # at the API's default page size, the newest 300 PRs


def _raise_for_status(response, url):
    if response.status_code == 200:
        return
    # Error responses are JSON with a message, not a list. Raise with that
    # message instead of letting the caller iterate an error dict and fail
    # later with a confusing type error.
    try:
        message = response.json().get("message", "")
    except ValueError:
        message = ""
    raise RuntimeError(
        f"GitHub API returned HTTP {response.status_code} for {url}"
        + (f": {message}" if message else ""))


def _get(url):
    response = requests.get(url, timeout=30)
    _raise_for_status(response, url)
    return response


def get_pull_requests(repo):
    pull_requests = []
    page = 1
    while page <= MAX_PAGES:
        url = f"{API}/repos/{repo}/pulls?page={page}"
        response = requests.get(url, timeout=30)
        # .get with a default: an error page or a proxy can strip these
        # headers, and a KeyError here used to kill the whole export.
        remaining = int(response.headers.get("X-RateLimit-Remaining", "1"))
        if response.status_code in (403, 429) and remaining == 0:
            # Rate limiting arrives as an error status, so it has to be
            # handled here, before _get turns non-200 responses into
            # exceptions. Wait for the reset and retry the same page.
            reset_time = int(response.headers.get("X-RateLimit-Reset", "0"))
            wait_time = max(reset_time - int(time.time()) + 1, 1)
            print(f"API rate limit exceeded. Waiting for {wait_time} seconds.")
            time.sleep(wait_time)
            continue
        _raise_for_status(response, url)
        data = response.json()
        if not data:
            break
        pull_requests.extend(data)
        page += 1
    return pull_requests


def get_pull_request_detail(repo, number):
    return _get(f"{API}/repos/{repo}/pulls/{number}").json()


def get_pull_request_data(repo, pull_request):
    # closed_by is present but null on a pull request nobody closed, and
    # dict.get with a {} default does not cover an explicit null, which is
    # why this uses "or {}" instead.
    user_closed = (pull_request.get("closed_by") or {}).get("login")
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
        with open(filename, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["PR Number", "Date Opened", "Date Closed",
                             "User Opened", "User Closed", "Status",
                             "Number of Comments", "Number of Files Changed"])
            for pull_request in pull_requests:
                writer.writerow(get_pull_request_data(repo, pull_request))
        print(f"Data from pull requests in repository {repo} has been saved to {filename}.")
    except Exception as exc:
        print(f"An error occurred: {exc}")


if __name__ == "__main__":
    main()
