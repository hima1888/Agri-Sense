# Analytics & reports (Phase 16)

`/analytics` in the app; saved reports open at `/reports/{id}` (print → "Save as PDF") and download as CSV.
Everything is computed from records already in AGRI-SENSE. Code: `backend/app/services/analytics.py`,
`backend/app/api/v1/endpoints/reports.py`.

## What a period covers

Pick a date range (presets: last 7, 30 or 90 days; at most 400 days). Dates are the **farm's** local calendar
days. The same metrics are computed for the previous period of equal length, for comparison.

| Section | Metrics | Source |
|---|---|---|
| Water | completed irrigation events, litres, mm (litres ÷ area), by zone; rain, effective rain and ET₀; share of measured hours each zone was below its stress threshold | irrigation events; stored Open-Meteo hourly data; soil-moisture readings vs the Phase 8 threshold (FC − p·(FC − WP)) |
| Fertilizer | applications, product kg, organic kg, N / P₂O₅ / K₂O kg and kg/ha | fertilizer logs (grade × quantity) |
| Pesticides | applications, per ha, by type, quantity by unit, share linked to a disease check | pesticide logs |
| Crop health & harvests | disease checks by outcome, possible diseases; harvested cycles and kg/ha | disease checks; crop cycles |
| Advice & alerts | recommendations by status and category, uptake (accepted + applied ÷ decided); alerts by severity, resolved, median hours to resolve | recommendations; alerts |
| Data quality | readings, share flagged not-good, share simulated, zones without an area | sensor readings; zones |

**Sustainability indicators** compared with the previous period: irrigation water per ha; N, P₂O₅ and K₂O
per ha; pesticide applications per ha; share of sprays linked to a disease check; advice uptake. A change % is
shown only when both periods have a non-zero value.

## Reports

`POST /farms/{id}/reports` with `report_type` `farm_summary` (everything) or `sustainability` (indicators and
notes), and a period. The report is stored as a **snapshot** in `reports.content`: editing records later does
not change it. `GET /reports/{id}/csv` flattens it to `section,metric,value` rows. The printable page hides the
app chrome and prints black on white. There is no server-side PDF; the browser's print dialog makes one.

## Endpoints

| | |
|---|---|
| `GET /farms/{id}/analytics?start&end` | live analytics (default: the farm's last 30 days) |
| `POST` / `GET /farms/{id}/reports` | save / list reports |
| `GET` / `DELETE /reports/{id}` | read / delete a report |
| `GET /reports/{id}/csv` | CSV download |

## Limitations

- Only what is logged in AGRI-SENSE is counted. A spray or irrigation recorded elsewhere is missing, and a
  period with nothing logged shows 0, which may mean "not recorded".
- Rain and ET₀ cover only the days the app fetched weather (shown as "over N day(s)").
- Water-stress hours apply each zone's **current** soil and crop parameters to the whole period.
- Per-hectare figures use zones that have an area. Zones without one are listed.
- Pesticide amounts are product quantities, not active ingredient.
