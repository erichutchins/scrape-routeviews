# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#     "aiofiles",
#     "grex",
#     "httpx",
#     "orjson",
#     "packaging",
#     "pyasn",
#     "zstandard",
# ]
# ///

import asyncio
import datetime
import tempfile
from collections import defaultdict
from ipaddress import ip_network
from typing import Generator

import httpx
import orjson
import zstandard as zstd
from grex import RegExpBuilder
from packaging.version import InvalidVersion, Version
from pyasn import mrtx


def ip_sort_key(ip: str):
    try:
        # Try parsing as an IPv4 address, using Version for numeric sorting
        return (0, Version(ip.partition("/")[0]))
    except InvalidVersion:
        # Fallback to lexicographic sorting for IPv6
        return (1, ip)


def build_filename() -> str:
    """Generate URL for the latest RouteViews RIB file (last even-numbered hour)."""
    now = datetime.datetime.now(datetime.UTC)
    while now.hour % 2 != 0:
        now -= datetime.timedelta(hours=1)

    return now.strftime("https://routeviews.org/bgpdata/%Y.%m/RIBS/rib.%Y%m%d.%H00.bz2")


def extract_even_ipv4_networks(network: str) -> Generator[str, None, None]:
    """Generator of even IPv4 networks from a CIDR block."""
    net = ip_network(network, strict=False)
    if not net.version == 4:
        return

    prefix = net.prefixlen

    if prefix <= 8:
        for subnet in net.subnets(new_prefix=8):
            yield f"{subnet.network_address.exploded.split('.')[0]}."
    elif prefix <= 16:
        for subnet in net.subnets(new_prefix=16):
            octets = subnet.network_address.exploded.split(".")
            yield f"{octets[0]}.{octets[1]}."
    elif prefix <= 24:
        for subnet in net.subnets(new_prefix=24):
            octets = subnet.network_address.exploded.split(".")
            yield f"{octets[0]}.{octets[1]}.{octets[2]}."
    else:
        # If the network is more specific than /24, extract all /32 ips
        # including the network and broadcast addresses
        yield str(net.network_address)
        for ip in net.hosts():
            yield str(ip)
        yield str(net.broadcast_address)


def build_asn_to_even_prefixes(asn_dict: dict) -> dict:
    """Build a dictionary mapping even ASNs to their prefixes."""
    even_asn_dict = defaultdict(set)
    for asn, prefixes in asn_dict.items():
        for prefix in prefixes:
            for even_chunk in extract_even_ipv4_networks(prefix):
                if not even_chunk:
                    continue
                even_asn_dict[asn].add(even_chunk)

    return even_asn_dict


def build_asn_to_regex(asn_dict: dict) -> dict:
    """Build a dictionary mapping ASNs to their regex patterns."""
    even_asn_dict = build_asn_to_even_prefixes(asn_dict)

    return {
        asn: RegExpBuilder(list(prefixes)).without_end_anchor().build()
        for asn, prefixes in even_asn_dict.items()
    }


async def download_rib_file(url: str, output_path: str):
    """Download the RouteViews RIB file using async streaming."""
    async with httpx.AsyncClient(timeout=600) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)
    print(f"Downloaded: {output_path}")


async def parse_rib_to_dict(rib_file: str) -> dict:
    """Parse the RIB file using pyasn and return ASN to prefix mappings as JSON."""
    prefixes = mrtx.parse_mrt_file(
        rib_file, print_progress=False, skip_record_on_error=True
    )

    asn_dict = defaultdict(list)
    for prefix, asn in prefixes.items():
        if isinstance(asn, set):
            for set_asn in asn:
                asn_dict[int(set_asn)].append(prefix)
        else:
            asn_dict[int(asn)].append(prefix)

    # sort the prefix lists in "version" order which effectively
    # sorts each octet of an ipv4. ipv6 addresses are sorted lexicographically
    sorted_asn_dict = {
        asn: sorted(prefixes, key=ip_sort_key) for asn, prefixes in asn_dict.items()
    }

    return sorted_asn_dict


async def main():
    url = build_filename()
    print(f"Downloading: {url}")

    with tempfile.TemporaryDirectory() as tmpdir:
        rib_path = f"{tmpdir}/rib.bz2"

        await download_rib_file(url, rib_path)

        asn_dict = await parse_rib_to_dict(rib_path)

    # Save to JSON
    output_json_path = "routeviews_asn_prefixes.json"
    with open(output_json_path, "wb") as json_file:
        json_file.write(
            orjson.dumps(
                asn_dict,
                option=orjson.OPT_NON_STR_KEYS
                | orjson.OPT_SORT_KEYS
                | orjson.OPT_STRICT_INTEGER
                | orjson.OPT_INDENT_2,
            )
        )

    print(f"ASN-Prefix JSON saved: {output_json_path}")

    # Save a compressed version
    compressed_json_path = "routeviews_asn_prefixes.json.zstd"
    with open(compressed_json_path, "wb") as fh:
        cctx = zstd.ZstdCompressor(level=8)
        with cctx.stream_writer(fh) as compressor:
            compressor.write(
                orjson.dumps(
                    asn_dict,
                    option=orjson.OPT_NON_STR_KEYS
                    | orjson.OPT_SORT_KEYS
                    | orjson.OPT_STRICT_INTEGER,
                )
            )

    print(f"Compressed ASN-Prefix JSON saved: {compressed_json_path}")

    # Build a dictionary mapping even ASNs to their prefixes
    # Convert sets to sorted lists for JSON serialization
    asn_regex = build_asn_to_regex(asn_dict)

    # Save the even ASN dictionary to JSON
    asn_regex_json_path = "routeviews_asn_grex.json.zstd"
    with open(asn_regex_json_path, "wb") as fh:
        cctx = zstd.ZstdCompressor(level=8)
        with cctx.stream_writer(fh) as compressor:
            compressor.write(
                orjson.dumps(
                    asn_regex,
                    option=orjson.OPT_NON_STR_KEYS
                    | orjson.OPT_SORT_KEYS
                    | orjson.OPT_STRICT_INTEGER,
                )
            )

    print(f"Even ASN-GREX JSON saved: {asn_regex_json_path}")


if __name__ == "__main__":
    asyncio.run(main())
