# Third-party software

This repository includes copies of the following software. Each keeps its own licence.

| Component | Where | Licence |
|---|---|---|
| [Potree 1.8](https://github.com/potree/potree) | `potree_viewer/build`, `potree_viewer/libs` | BSD 2-Clause — `potree_viewer/POTREE_LICENSE.txt` |
| Libraries bundled with Potree (three.js, jQuery, jQuery UI, d3, OpenLayers, proj4, i18next, jstree, spectrum, tween.js, plasio, Cesium, …) | `potree_viewer/libs` | their own licences, as shipped with Potree (mostly MIT / BSD / Apache-2.0) |
| [thinking-orbs](https://www.npmjs.com/package/thinking-orbs) 0.3.2 (canvas engine only) | `lidar_agent/vendor/thinking-orbs` | MIT — `lidar_agent/vendor/thinking-orbs/LICENSE` |

Not included (installed separately):

- [PotreeConverter](https://github.com/potree/PotreeConverter) — BSD 2-Clause
- Python packages in `requirements.txt` (laspy, lazrs, numpy, scipy, openpyxl, matplotlib) — installed with pip
