import argparse
import asyncio
import io
import json
import os
import statistics
import zipfile
from collections import defaultdict

import aiohttp
from gidgethub.aiohttp import GitHubAPI
from gidgethub.sansio import accept_format

GH_API = "https://api.github.com"
GH_OWNER = "reizio"
GH_REPO = "benchmarks"
GH_USERNAME = "ReeseBot"

# A variant of gidgethub.getiter with the support for
# custom element iterators (e.g artifacts)
async def getiter(gh, url, identifier, **url_vars):
    data = b""
    accept = accept_format()
    data, more = await gh._make_request("GET", url, url_vars, data, accept)

    if isinstance(data, dict) and identifier in data:
        data = data[identifier]

    for item in data:
        yield item

    if more:
        async for item in getiter(gh, more, identifier, **url_vars):
            yield item


async def collect_reports(gh, session, auth):
    total_count = 0
    async for artifact in getiter(
        gh,
        f"/repos/{GH_OWNER}/{GH_REPO}/actions/artifacts",
        "artifacts",
        per_page=100,
    ):
        async with session.get(
            f"{GH_API}/repos/{GH_OWNER}/{GH_REPO}/actions"
            f"/artifacts/{artifact['id']}/zip",
            auth=auth,
        ) as resp:
            buffer = io.BytesIO(await resp.read())

        zip_obj = zipfile.ZipFile(buffer)
        assert len(zip_obj.filelist) == 1
        assert zip_obj.filelist[0].filename == "benchmark_report.json"

        with zip_obj.open("benchmark_report.json") as stream:
            report = json.load(stream)

        yield artifact["updated_at"], report


def process_results(original_results):
    results = defaultdict(dict)
    for date, report in original_results.items():
        for key, timings in report.items():
            results[key][date] = statistics.fmean(timings)
    return results


async def runner(data_file):
    auth = aiohttp.BasicAuth(GH_USERNAME, os.getenv("GITHUB_TOKEN"))

    async with aiohttp.ClientSession() as session:
        gh = GitHubAPI(
            session, "ReeseBot", oauth_token=os.getenv("GITHUB_TOKEN")
        )

        results = {
            date: report
            async for date, report in collect_reports(gh, session, auth)
        }
        with open(data_file, "w") as stream:
            json.dump(process_results(results), stream, indent=4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-file", type=str, default="static/results.json")

    options = parser.parse_args()
    asyncio.run(runner(options.data_file))


if __name__ == "__main__":
    main()
