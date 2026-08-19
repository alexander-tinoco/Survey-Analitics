# Vendored third-party assets

Committed to the repository rather than pulled from a CDN, so the application
renders with no external requests: the dashboard works offline, in a locked-down
network, and cannot break because someone else's CDN changed a file.

| File | Version | License |
| --- | --- | --- |
| `chart.umd.js` | Chart.js 4.4.7 | MIT — © Chart.js Contributors |

Chart.js is distributed under the MIT License. Full text:
<https://github.com/chartjs/Chart.js/blob/master/LICENSE.md>

To upgrade, replace the file with the matching `dist/chart.umd.js` build and
update the version above in the same commit.
