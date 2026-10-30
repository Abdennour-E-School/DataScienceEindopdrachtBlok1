from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUTPUT = ROOT / "data" / "processed" / "gemeente_voorzieningen_woz.csv"
NEIGHBORHOOD_OUTPUT = ROOT / "data" / "processed" / "buurt_voorzieningen_woz.csv"
MISSING_MARKERS = {"", ".", "..", "...", "...."}
FACILITY_COLUMNS = [
    "AfstandTotHuisartsenpraktijk_5",
    "AfstandTotApotheek_10",
    "AfstandTotZiekenhuis_11",
    "AfstandTotGroteSupermarkt_24",
    "AfstandTotKinderdagverblijf_52",
    "AfstandTotSchool_60",
]


def read_csv(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    for column in data.select_dtypes(include="object"):
        data[column] = data[column].str.strip()
    return data


def add_codebook_label(
    data: pd.DataFrame,
    code_column: str,
    codebook_path: Path,
    label_column: str,
) -> pd.DataFrame:
    codebook = read_csv(codebook_path)[["Key", "Title"]].rename(
        columns={"Key": code_column, "Title": label_column}
    )
    return data.merge(
        codebook,
        on=code_column,
        how="left",
        validate="many_to_one",
    )


def to_number(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values.replace(MISSING_MARKERS, pd.NA), errors="coerce")


def prepare_neighborhood_data() -> pd.DataFrame:
    woz = read_csv(RAW / "85984NED" / "TypedDataSet.csv")
    woz_column = next(
        column for column in woz.columns
        if column.startswith("GemiddeldeWOZWaardeVanWoningen_")
    )
    density_column = next(
        column for column in woz.columns if column.startswith("Bevolkingsdichtheid_")
    )
    address_density_column = next(
        column for column in woz.columns if column.startswith("Omgevingsadressendichtheid_")
    )
    woz = woz.loc[
        woz["SoortRegio_2"].eq("Buurt"),
        ["WijkenEnBuurten", woz_column, density_column, address_density_column],
    ].copy()
    codebook = read_csv(RAW / "85984NED" / "codebooks" / "WijkenEnBuurten.csv")
    neighborhood_codes = codebook[["Key", "Title", "Municipality"]].rename(
        columns={
            "Key": "WijkenEnBuurten",
            "Title": "BuurtNaam",
            "Municipality": "GemeenteCode",
        }
    )
    woz = woz.merge(
        neighborhood_codes,
        on="WijkenEnBuurten",
        how="left",
        validate="one_to_one",
    )
    woz["WOZ_2024_euro"] = to_number(woz[woz_column]) * 1000
    woz["Bevolkingsdichtheid_2024"] = to_number(woz[density_column])
    woz["Omgevingsadressendichtheid_2024"] = to_number(woz[address_density_column])
    woz["RegioS"] = woz["WijkenEnBuurten"]

    facilities = read_csv(RAW / "86270NED" / "TypedDataSet.csv")
    facilities = facilities.loc[
        facilities["SoortRegio_2"].eq("Buurt"),
        ["WijkenEnBuurten", "Gemeentenaam_1", *FACILITY_COLUMNS],
    ].rename(columns={"Gemeentenaam_1": "GemeenteNaam"})
    for column in FACILITY_COLUMNS:
        facilities[column] = to_number(facilities[column])

    result = facilities.merge(
        woz[
            [
                "WijkenEnBuurten",
                "RegioS",
                "BuurtNaam",
                "GemeenteCode",
                "WOZ_2024_euro",
                "Bevolkingsdichtheid_2024",
                "Omgevingsadressendichtheid_2024",
            ]
        ],
        on="WijkenEnBuurten",
        how="left",
        validate="one_to_one",
    )
    centroids = read_csv(RAW / "geography" / "neighborhood_centroids.csv")
    result = result.merge(
        centroids,
        on="WijkenEnBuurten",
        how="left",
        validate="one_to_one",
    )
    NEIGHBORHOOD_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(NEIGHBORHOOD_OUTPUT, index=False, encoding="utf-8-sig")
    print(
        f"Opgeslagen: {NEIGHBORHOOD_OUTPUT.relative_to(ROOT)} "
        f"({len(result)} buurten; WOZ ontbreekt voor {result['WOZ_2024_euro'].isna().sum()})"
    )
    return result


def main() -> None:
    woz = read_csv(RAW / "85036NED" / "TypedDataSet.csv")
    woz = add_codebook_label(
        woz, "RegioS", RAW / "85036NED" / "codebooks" / "RegioS.csv", "GemeenteNaam"
    )
    woz = add_codebook_label(
        woz, "Eigendom", RAW / "85036NED" / "codebooks" / "Eigendom.csv", "EigendomNaam"
    )
    woz = add_codebook_label(
        woz, "Perioden", RAW / "85036NED" / "codebooks" / "Perioden.csv", "Jaar"
    )
    woz["WOZ_euro"] = to_number(woz["GemiddeldeWOZWaardeVanWoningen_1"]) * 1000
    woz = woz.loc[woz["RegioS"].str.startswith("GM") & woz["EigendomNaam"].eq("Totaal")]
    woz_pivot = woz.pivot_table(
        index=["RegioS", "GemeenteNaam"],
        columns="Jaar",
        values="WOZ_euro",
        aggfunc="first",
    ).reset_index()
    woz_pivot.columns.name = None
    woz_pivot = woz_pivot.rename(
        columns={
            year: f"WOZ_{year}_euro"
            for year in woz_pivot.columns
            if year not in {"RegioS", "GemeenteNaam"}
        }
    )

    facilities = read_csv(RAW / "86270NED" / "TypedDataSet.csv")
    neighborhood_codes = read_csv(
        RAW / "86270NED" / "codebooks" / "WijkenEnBuurten.csv"
    )[["Key", "Municipality"]].rename(columns={"Key": "WijkenEnBuurten"})
    facilities = facilities.loc[facilities["SoortRegio_2"].eq("Buurt")].merge(
        neighborhood_codes,
        on="WijkenEnBuurten",
        how="left",
        validate="many_to_one",
    )
    facilities = facilities.loc[facilities["Municipality"].str.startswith("GM")].copy()
    for column in FACILITY_COLUMNS:
        facilities[column] = to_number(facilities[column])

    municipality_facilities = (
        facilities.groupby("Municipality")[FACILITY_COLUMNS]
        .mean()
        .reset_index()
        .rename(
            columns={
                "Municipality": "RegioS",
                **{column: f"Gemiddelde_{column}" for column in FACILITY_COLUMNS},
            }
        )
    )
    result = municipality_facilities.merge(
        woz_pivot,
        on="RegioS",
        how="left",
        validate="one_to_one",
    )
    core = read_csv(RAW / "86358NED" / "TypedDataSet.csv")
    municipality_context = core.loc[
        core["SoortRegio_2"].eq("Gemeente"),
        ["Codering_3", "Bevolkingsdichtheid_35", "Omgevingsadressendichtheid_122"],
    ].rename(
        columns={
            "Codering_3": "RegioS",
            "Bevolkingsdichtheid_35": "Bevolkingsdichtheid_2026",
            "Omgevingsadressendichtheid_122": "Omgevingsadressendichtheid_2026",
        }
    )
    for column in ["Bevolkingsdichtheid_2026", "Omgevingsadressendichtheid_2026"]:
        municipality_context[column] = to_number(municipality_context[column])
    result = result.merge(
        municipality_context,
        on="RegioS",
        how="left",
        validate="one_to_one",
    )
    centroids = read_csv(RAW / "geography" / "municipality_centroids.csv")
    result = result.merge(centroids, on="RegioS", how="left", validate="one_to_one")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
    print(f"Opgeslagen: {OUTPUT.relative_to(ROOT)} ({len(result)} gemeenten)")
    print(f"WOZ 2025 ontbreekt voor: {result['WOZ_2025_euro'].isna().sum()} gemeenten")
    prepare_neighborhood_data()


if __name__ == "__main__":
    main()