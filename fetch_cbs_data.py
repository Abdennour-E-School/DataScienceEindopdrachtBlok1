import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


API_ROOT = "https://opendata.cbs.nl/ODataApi/OData"
FEED_ROOT = "https://opendata.cbs.nl/ODataFeed/OData"
DATASET_IDS = ("86358NED", "86270NED", "85036NED", "85984NED")
PAGE_SIZE = 5000
TIMEOUT_SECONDS = 60
WFS_URL = "https://service.pdok.nl/cbs/wijkenbuurten/2025/wfs/v1_0"


def get_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
    response = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
        raise ValueError(f"Onverwacht CBS API-antwoord van {response.url}")
    return payload


def save_collection(
    session: requests.Session,
    url: str,
    output_path: Path,
    limit: int | None = None,
    paged: bool = False,
    dynamic_fields: bool = False,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    next_url: str | None = url
    offset = 0
    row_count = 0
    writer: csv.DictWriter | None = None
    buffered_rows: list[dict] | None = [] if dynamic_fields else None

    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        while next_url:
            page_size = min(PAGE_SIZE, limit - row_count) if limit is not None else PAGE_SIZE
            if paged:
                params = {
                    "$format": "json",
                    "$top": page_size,
                    "$skip": offset,
                }
            else:
                params = {"$top": page_size} if limit is not None else None
            payload = get_json(session, next_url, params=params)
            rows = payload["value"]

            if buffered_rows is not None:
                buffered_rows.extend(rows)
            elif rows and writer is None:
                writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
                writer.writeheader()

            if writer is not None and buffered_rows is None:
                writer.writerows(rows)

            row_count += len(rows)
            if limit is not None and row_count >= limit:
                break

            if paged and len(rows) == page_size:
                offset += len(rows)
                next_url = url
            else:
                next_url = None

    if buffered_rows:
        fieldnames = list(dict.fromkeys(key for row in buffered_rows for key in row))
        with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(buffered_rows)

    return row_count


def fetch_dataset(
    session: requests.Session,
    dataset_id: str,
    output_dir: Path,
    limit: int | None,
) -> None:
    dataset_url = f"{API_ROOT}/{dataset_id}"
    dataset_dir = output_dir / dataset_id
    catalog = get_json(session, dataset_url)
    table_counts: dict[str, int] = {}

    data_count = save_collection(
        session,
        f"{FEED_ROOT}/{dataset_id}/TypedDataSet",
        dataset_dir / "TypedDataSet.csv",
        limit=limit,
        paged=True,
    )
    table_counts["TypedDataSet"] = data_count
    print(f"{dataset_id}: TypedDataSet ({data_count} rijen)")

    for table in catalog["value"]:
        table_name = table["name"]
        if table_name in {"TypedDataSet", "UntypedDataSet"}:
            continue

        row_count = save_collection(
            session,
            f"{FEED_ROOT}/{dataset_id}/{table_name}",
            dataset_dir / "codebooks" / f"{table_name}.csv",
            limit=limit,
            paged=True,
            dynamic_fields=True,
        )
        table_counts[table_name] = row_count
        print(f"{dataset_id}: {table_name} ({row_count} rijen)")

    manifest = {
        "dataset_id": dataset_id,
        "api_url": dataset_url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "row_counts": table_counts,
        "limited_to": limit,
    }
    (dataset_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def ring_centroid(ring: list[list[float]]) -> tuple[float, float, float]:
    area_twice = 0.0
    longitude_sum = 0.0
    latitude_sum = 0.0
    for first, second in zip(ring, ring[1:]):
        cross = first[0] * second[1] - second[0] * first[1]
        area_twice += cross
        longitude_sum += (first[0] + second[0]) * cross
        latitude_sum += (first[1] + second[1]) * cross

    if area_twice == 0:
        longitude = sum(point[0] for point in ring) / len(ring)
        latitude = sum(point[1] for point in ring) / len(ring)
        return longitude, latitude, 0.0

    longitude = longitude_sum / (3 * area_twice)
    latitude = latitude_sum / (3 * area_twice)
    return longitude, latitude, abs(area_twice) / 2


def feature_centroid(geometry: dict) -> tuple[float, float, float]:
    if geometry["type"] == "Polygon":
        polygons = [geometry["coordinates"]]
    else:
        polygons = geometry["coordinates"]

    weighted_longitude = 0.0
    weighted_latitude = 0.0
    total_area = 0.0
    fallback_points: list[list[float]] = []

    for polygon in polygons:
        ring = polygon[0]
        longitude, latitude, area = ring_centroid(ring)
        weighted_longitude += longitude * area
        weighted_latitude += latitude * area
        total_area += area
        fallback_points.extend(ring)

    if total_area == 0:
        return (
            sum(point[0] for point in fallback_points) / len(fallback_points),
            sum(point[1] for point in fallback_points) / len(fallback_points),
            0.0,
        )
    return weighted_longitude / total_area, weighted_latitude / total_area, total_area


def fetch_municipality_centroids(
    session: requests.Session,
    output_dir: Path,
) -> None:
    output_path = output_dir / "geography" / "municipality_centroids.csv"
    woz_path = output_dir / "85036NED" / "TypedDataSet.csv"
    municipality_codes = set()
    with woz_path.open(encoding="utf-8-sig", newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            code = row["RegioS"].strip()
            if (
                code.startswith("GM")
                and row["Eigendom"].strip() == "T001132"
                and row["Perioden"].strip() == "2025JJ00"
                and row["GemiddeldeWOZWaardeVanWoningen_1"].strip()
                not in {"", ".", "..", "...", "...."}
            ):
                municipality_codes.add(code)

    if output_path.exists():
        with output_path.open(encoding="utf-8-sig", newline="") as csv_file:
            existing_codes = [row["RegioS"].strip() for row in csv.DictReader(csv_file)]
        if len(existing_codes) == len(set(existing_codes)) and set(existing_codes) == municipality_codes:
            print(f"Kaartcoördinaten bestaan al: {output_path}")
            return

    centroid_totals: dict[str, dict[str, float]] = {}
    codes = sorted(municipality_codes)
    batch_size = 25
    for start in range(0, len(codes), batch_size):
        batch = codes[start : start + batch_size]
        conditions = "".join(
            f"<fes:PropertyIsEqualTo><fes:ValueReference>gemeentecode</fes:ValueReference>"
            f"<fes:Literal>{code}</fes:Literal></fes:PropertyIsEqualTo>"
            for code in batch
        )
        if len(batch) > 1:
            conditions = f"<fes:Or>{conditions}</fes:Or>"
        filter_xml = (
            '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">'
            f"{conditions}</fes:Filter>"
        )
        response = session.get(
            WFS_URL,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": "wijkenbuurten:gemeenten",
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "propertyName": "gemeentecode",
                "FILTER": filter_xml,
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        for feature in response.json()["features"]:
            properties = feature["properties"]
            code = properties["gemeentecode"]
            longitude, latitude, area = feature_centroid(feature["geometry"])
            totals = centroid_totals.setdefault(
                code,
                {"longitude": 0.0, "latitude": 0.0, "area": 0.0},
            )
            weight = area if area else 1.0
            totals["longitude"] += longitude * weight
            totals["latitude"] += latitude * weight
            totals["area"] += weight
        print(f"Kaartcoördinaten: {min(start + batch_size, len(codes))}/{len(codes)}")

    found_codes = set(centroid_totals)
    missing_codes = municipality_codes - found_codes
    if missing_codes:
        raise ValueError(f"Geen kaartgeometrie gevonden voor: {sorted(missing_codes)}")

    centroids = [
        {
            "RegioS": code,
            "Latitude": totals["latitude"] / totals["area"],
            "Longitude": totals["longitude"] / totals["area"],
        }
        for code, totals in sorted(centroid_totals.items())
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["RegioS", "Latitude", "Longitude"],
        )
        writer.writeheader()
        writer.writerows(centroids)


def fetch_neighborhood_centroids(
    session: requests.Session,
    output_dir: Path,
) -> None:
    output_path = output_dir / "geography" / "neighborhood_centroids.csv"
    woz_path = output_dir / "85984NED" / "TypedDataSet.csv"
    nearby_path = output_dir / "86270NED" / "TypedDataSet.csv"
    missing_markers = {"", ".", "..", "...", "...."}

    with woz_path.open(encoding="utf-8-sig", newline="") as csv_file:
        woz_reader = csv.DictReader(csv_file)
        woz_rows = list(woz_reader)
    woz_column = next(
        column for column in (woz_reader.fieldnames or [])
        if column.startswith("GemiddeldeWOZWaardeVanWoningen_")
    )
    woz_codes = {
        row["WijkenEnBuurten"].strip()
        for row in woz_rows
        if row["SoortRegio_2"].strip() == "Buurt"
        and row[woz_column].strip() not in missing_markers
    }

    with nearby_path.open(encoding="utf-8-sig", newline="") as csv_file:
        nearby_codes = {
            row["WijkenEnBuurten"].strip()
            for row in csv.DictReader(csv_file)
            if row["SoortRegio_2"].strip() == "Buurt"
        }
    target_codes = nearby_codes & woz_codes

    if output_path.exists():
        with output_path.open(encoding="utf-8-sig", newline="") as csv_file:
            existing_codes = {
                row["WijkenEnBuurten"].strip() for row in csv.DictReader(csv_file)
            }
        if existing_codes == target_codes:
            print(f"Buurtcoördinaten bestaan al: {output_path}")
            return

    filter_xml = (
        '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">'
        "<fes:PropertyIsEqualTo><fes:ValueReference>jaar</fes:ValueReference>"
        "<fes:Literal>2025</fes:Literal></fes:PropertyIsEqualTo></fes:Filter>"
    )
    centroid_totals: dict[str, dict[str, float]] = {}
    page_size = 1000
    for offset in range(0, 100000, page_size):
        response = session.get(
            WFS_URL,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": "wijkenbuurten:buurten",
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "propertyName": "buurtcode",
                "FILTER": filter_xml,
                "count": page_size,
                "startIndex": offset,
            },
            timeout=120,
        )
        response.raise_for_status()
        features = response.json()["features"]
        if not features:
            break

        for feature in features:
            code = feature["properties"]["buurtcode"]
            if code not in target_codes:
                continue
            longitude, latitude, area = feature_centroid(feature["geometry"])
            totals = centroid_totals.setdefault(
                code,
                {"longitude": 0.0, "latitude": 0.0, "area": 0.0},
            )
            weight = area if area else 1.0
            totals["longitude"] += longitude * weight
            totals["latitude"] += latitude * weight
            totals["area"] += weight
        print(f"Buurtgeometrie: {min(offset + len(features), 7683)}/7683 features")
        if len(features) < page_size:
            break

    centroids = [
        {
            "WijkenEnBuurten": code,
            "Latitude": totals["latitude"] / totals["area"],
            "Longitude": totals["longitude"] / totals["area"],
        }
        for code, totals in sorted(centroid_totals.items())
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["WijkenEnBuurten", "Latitude", "Longitude"],
        )
        writer.writeheader()
        writer.writerows(centroids)
    print(f"Buurtcoördinaten: {len(centroids)}/{len(target_codes)} gekoppelde buurten")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Haal CBS StatLine-tabellen en codeboeken op als CSV."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "raw",
        help="Map voor de opgehaalde bestanden (standaard: data/raw).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximaal aantal rijen per tabel; bedoeld voor een proefdownload.",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit moet minimaal 1 zijn")

    with requests.Session() as session:
        session.headers.update({"User-Agent": "DataScienceMinor-CBS-data-fetcher/1.0"})
        for dataset_id in DATASET_IDS:
            fetch_dataset(session, dataset_id, args.output_dir, args.limit)
        if args.limit is None:
            fetch_municipality_centroids(session, args.output_dir)
            fetch_neighborhood_centroids(session, args.output_dir)


if __name__ == "__main__":
    main()
