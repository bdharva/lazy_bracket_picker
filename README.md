# Lazy Bracket Picker
_Don't know/care about college basketball, but feel socially obligated to join friends/family/co-workers in a March Madness bracket pool? This is for you._

## Quick Start

### Web UI (recommended)

```bash
python -m venv venv
source venv/bin/activate
pip install flask
python app.py
```

Open http://localhost:5050. Set your pool size, optionally tag homer teams that people in your pool are fans of, and hit Generate. The tool produces dozens of optimized brackets across a spectrum of strategies, plotted on an interactive scatter chart. Click any dot to see the full bracket.

![Web UI](assets/web-ui.png?raw=true)

### CLI

```bash
# Expected-value optimal bracket (maximizes points)
python optimize.py

# Contrarian bracket (for large pools)
python optimize.py contrarian

# Random simulation (original mode)
python simulate.py [seed|team|hybrid] [# of simulations] [true|false for decay]
```

## How It Works

### Optimizer (`optimize.py` / `app.py`)

Uses Bart Torvik's adjusted efficiency margins (AdjOE - AdjDE) to compute pairwise win probabilities via logistic regression:

```
P(A beats B) = 1 / (1 + 10^(-EM_diff / 11))
```

Then runs dynamic programming over the bracket tree to find the picks that maximize expected score given the pool's scoring system (10/20/40/80/160/320 points by round).

The web UI generates brackets across a multi-dimensional grid of strategies:

| Dimension | What it does |
| --- | --- |
| **Contrarian weight** | Favors picks the public under-selects (scaled by pool size) |
| **Seed blend** | Mixes Torvik efficiency with historical seed performance data |
| **Defense floor** | Penalizes teams with poor defensive efficiency in later rounds |
| **Upset boost** | Nudges first-round outcomes toward historical upset rates (5v12, 6v11, etc.) |

Five featured brackets are highlighted:

| Label | Selection criteria |
| --- | --- |
| **Safest** | Highest total expected value |
| **Historic** | Closest to the historical average of ~12.7 upsets per tournament |
| **Balanced** | Highest EV among brackets with above-median uniqueness |
| **Sleeper** | Highest late-round EV (Sweet 16 through Championship) |
| **Riskiest** | Most picks divergent from the chalk bracket |

### Simulator (`simulate.py`)

The original random simulation mode. Accepts a strategy (`seed`, `team`, or `hybrid`), a number of simulations per game, and a decay flag. Higher simulation counts follow the odds more closely; lower counts introduce more randomness. 10-20 simulations per game generally yields upset distributions in line with historical norms:

| Round | Average | Least | Most |
| --- | --- | --- | --- |
| First Round | 6.1 | 2 (2007) | 10 (2016) |
| Second Round | 3.7 | 0 (3 occasions) | 8 (2000) |
| Sweet 16 | 1.7 | 0 (5 occasions) | 4 (1990) |
| Elite Eight | 0.5 | 0 (10 occasions) | 2 (2 occasions) |
| Final Four | 0.2 | 0 (23 occasions) | 2 (2014) |
| **Total Upsets** | **12.7** | **4 (2007)** | **19 (2014)** |

## Data Sources

| File | Source |
| --- | --- |
| `data/teams.csv` | 2026 NCAA tournament bracket (64 teams, seeds, regions) |
| `data/team_odds.csv` | Round-by-round advancement probabilities derived from sportsbook odds |
| `data/torvik.csv` | Bart Torvik T-Rank adjusted efficiency data (AdjOE, AdjDE) |
| `data/seed_odds.csv` | Historical seed advancement rates (1985-present) |
| `data/matchups.csv` | Bracket structure (63 matchups) |
| `data/scoring.csv` | Points per correct pick by round |

## Project Structure

```
simulate.py          # CLI: random bracket simulation
optimize.py          # CLI: expected-value bracket optimizer
app.py               # Web UI (Flask + Plotly.js)
bulk_simulate.py     # Batch: generate thousands of simulations
bulk_score.py        # Score simulations against actual results
analysis.py          # Find optimal parameter combinations
modules/
  classes.py         # Team, Matchup, Simulation classes
  functions.py       # run_simulation(), write_results()
data/                # Teams, odds, matchups, scoring
exports/             # Generated bracket outputs
```
