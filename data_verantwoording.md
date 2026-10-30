# Data-verantwoording

Case 7. richting B. De voorzieningen komen uit CBS StatLine 86270NED (bronjaar 2025); de gemiddelde buurt-WOZ uit CBS StatLine 85984NED (bronjaar 2024). Kaartgeometrie komt uit de CBS/PDOK Wijk- en Buurtkaart 2025. De waarden en geometrie worden vooraf opgehaald met `fetch_cbs_data.py`; het dashboard leest alleen lokale bestanden.

De CBS-codevelden zijn met `strip()` opgeschoond. Voor 85984NED is het codeboek `WijkenEnBuurten` toegepast om BU-codes aan buurt- en gemeentecodes te koppelen. Daarna zijn de buurtbestanden op BU-code samengevoegd met `validate="one_to_one"`. De WOZ-kolom in 85984NED is al breed aangeleverd; er is voor de buurtanalyse geen kunstmatige pivot uitgevoerd. De gemeentelijke alternatieve bron 85036NED is wel lang: daarin past `prepare_cbs_data.py` de codeboeken RegioS. Eigendom en Perioden toe en pivoteert jaren naar kolommen.

Van 14.729 voorzieningenbuurten matchen 12.708 BU-codes met een gepubliceerde WOZ-waarde; 235 codes komen niet in de WOZ-tabel voor en bij 1.786 gematchte codes ontbreekt de WOZ-waarde. Voor 12.708 complete buurten is ook een kaartpunt beschikbaar. De overige waarden zijn niet ingevuld of geschat en vallen uit de analyse. De bestanden behouden hun volledige bronomvang in `data/raw/`; de verwerkte buurt- en gemeentetabellen staan in `data/processed/`.

Belangrijke beperking: voorzieningen zijn uit 2025 en WOZ uit 2024. De uitkomst is een associatie tussen afstand en gemiddelde buurt-WOZ; ze bewijst geen causaal effect. Een negatief modelresidu betekent lager dan de lineaire verwachting. niet automatisch betaalbaar.
