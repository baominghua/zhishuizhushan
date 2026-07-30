# Administrative Division Reference Data

`cn-administrative-divisions-2023.json` packages the 2023 public statistical
division snapshot for province, prefecture, county, and township selection.

- Public snapshot cutoff: 2023-06-30
- Packaging project: `modood/Administrative-divisions-of-China`, release 2.7.0
- Resource SHA-256:
  `eaec154ce55f9683fbae09a21cea7d8523e4074f323602cf92b6840611139c5b`
- County-and-above code basis: GB/T 2260-2007
- Township code basis: GB/T 10114-2003 and the NBS statistical-division rules
- NBS coding rules:
  https://www.stats.gov.cn/sj/tjbz/gjtjbz/202302/t20230213_1902741.html
- Original 2023 public index:
  https://www.stats.gov.cn/sj/tjbz/tjyqhdmhcxhfdm/2023/index.html

The NBS stopped publishing specific statistical division codes in October
2024. Township records are therefore explicitly identified in the API as a
historical public snapshot rather than current live codes. Project-area village
records remain curated separately in the application dictionary.
