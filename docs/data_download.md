# Download the public SBA data

Open the [SBA 7(a) and 504 FOIA dataset](https://data.sba.gov/dataset/7a-504-foia). Download **FOIA – 7(a) (FY2010–FY2019) as of September 30, 2026** and the **7(a) and 504 FOIA Data Dictionary**. The catalog refreshes quarterly. If it lists a later snapshot, locate the September 30, 2026 version before reproducing the published results.

From the project root, create `data/raw/` and save the files under these names. Keep both files local because the CSV includes borrower names and addresses.

- `data/raw/FOIA_7a_FY2010_FY2019_asof_260930.csv`
- `data/raw/7a_504_foia_data_dictionary.xlsx`

Check their SHA-256 digests in PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 data/raw/FOIA_7a_FY2010_FY2019_asof_260930.csv
Get-FileHash -Algorithm SHA256 data/raw/7a_504_foia_data_dictionary.xlsx
```

- **CSV** `39aa32b71fb5dbb4bfb178c9b3d597c92bb6903622027c2f8360d13e57d0abb2`
- **Dictionary** `777ba97a6f92e325f79905610816cb59d41f1971cd964c54dc30ef02730a3941`

The CSV hash identifies the exact release used in the reports. A refreshed dictionary may have a different digest. The pipeline checks its 7(a) field definitions against the CSV header and records the supplied checksum. The workbook’s 504 sheet is outside this study.
